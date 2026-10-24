"""Equus transformation engine: converts parsed Topia rows into Equus INSERT and UPDATE records."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.equus.mapping_config import (
    ADDRESS_COLUMNS,
    CONTACT_COLUMNS,
    DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
    DEPENDENT_FIELD_MAP,
    DROPDOWN_MAPS,
    FIELD_OVERRIDES,
    KEY_ALIASES,
    STRATEGY_EMPLOYEE_NUMBER,
    STRATEGY_TOPIA_ID_WITH_FALLBACK,
    clean_not_provided,
    convert_country_to_iso3,
    convert_dropdown,
    convert_us_date,
    normalize_identifier,
    split_multiline_address,
)
from app.services.equus.parser import ColumnMetadata, ParsedSheet, parse_three_row_workbook


@dataclass
class ColumnMapping:
    eq_col_idx: int
    eq_header: str | None
    eq_label: str | None
    eq_rule: str | None
    src_col_idx: int | None = None
    src_tech_field: str | None = None
    src_field_name: str | None = None
    src_display_name: str | None = None
    mapping_kind: str = "direct"  # direct, rule, exception, unmapped


@dataclass
class TransformationResult:
    insert_records: list[dict[int, Any]] = field(default_factory=list)
    update_records: list[dict[int, Any]] = field(default_factory=list)
    all_output_records: list[dict[int, Any]] = field(default_factory=list)
    mappings: list[ColumnMapping] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    dropdown_translations: list[dict[str, Any]] = field(default_factory=list)
    total_evaluated_rows: int = 0
    mapped_columns_count: int = 0
    unmapped_columns_count: int = 0
    coverage_percentage: float = 0.0
    strategy: str = STRATEGY_EMPLOYEE_NUMBER


def build_equus_column_mappings(
    source_sheet: ParsedSheet, template_sheet: ParsedSheet
) -> list[ColumnMapping]:
    """Map source columns to Equus columns based on technical field, label, aliases, and rules."""
    src_lookup: dict[str, ColumnMetadata] = {}
    for col in source_sheet.columns:
        # 1. Raw technical field and aliased technical field
        raw_tech = (col.technical_field or "").strip().upper()
        if raw_tech:
            src_lookup[raw_tech] = col
            aliased = raw_tech
            for pat, repl in KEY_ALIASES:
                aliased = re.sub(pat, repl, aliased)
            if aliased != raw_tech:
                src_lookup[aliased] = col

        # 2. Raw field name / UI label
        fn = (col.field_name or "").strip().upper()
        if fn:
            src_lookup[fn] = col

        # 3. Normalized display label and overrides
        lbl = (col.display_name or "").strip()
        if lbl:
            src_lookup[lbl.upper()] = col
            norm_lbl = " ".join(lbl.lower().split())
            if norm_lbl in FIELD_OVERRIDES:
                overridden_target = FIELD_OVERRIDES[norm_lbl]
                if overridden_target:
                    src_lookup[overridden_target.upper()] = col

    # Find key columns in source
    src_col_topia_id = None
    src_col_emp_id = None
    for col in source_sheet.columns:
        names = [
            (col.technical_field or "").upper(),
            (col.field_name or "").upper(),
            (col.display_name or "").upper(),
        ]
        norm_label = " ".join((col.display_name or "").lower().split())
        if src_col_topia_id is None and (
            norm_label == "assignment id"
            or any(
                n in {"ASSIGNMENT ID", "TOPIA ID", "ASSIGNMENT IDENTIFIER", "TOPIA FILE NUMBER"}
                for n in names
            )
        ):
            src_col_topia_id = col.col_index
        if src_col_emp_id is None and any(
            n in {"EMPLOYEE ID", "TALENT LINK ID", "EMPLOYEE NUMBER", "EMPLOYEE!SYSTEM_NUMBER"}
            for n in names
        ):
            src_col_emp_id = col.col_index

    # Fallbacks if not found by name
    if src_col_emp_id is None and len(source_sheet.columns) >= 5:
        src_col_emp_id = 5
    if src_col_topia_id is None and len(source_sheet.columns) >= 24:
        src_col_topia_id = 24

    mappings: list[ColumnMapping] = []

    for eq_col in template_sheet.columns:
        c_idx = eq_col.col_index
        # In template: Row 3 is technical header, Row 2 is human label
        eq_tech = (eq_col.field_name or "").strip()
        eq_lbl = (eq_col.technical_field or "").strip()
        eq_rule = eq_col.rule

        mapping = ColumnMapping(
            eq_col_idx=c_idx,
            eq_header=eq_tech or eq_lbl,
            eq_label=eq_lbl,
            eq_rule=eq_rule,
        )

        # Explicit Exceptions for key columns
        if c_idx == 1:  # A (Command)
            mapping.mapping_kind = "system_command"
        elif c_idx == 2:  # Assignment Command
            mapping.mapping_kind = "system_command"
        elif c_idx == 3:  # Employee Number
            mapping.src_col_idx = src_col_emp_id
            mapping.mapping_kind = "exception"
        elif c_idx == 4:  # Assignment Number
            mapping.mapping_kind = "system_constant"  # NEW
        elif c_idx == 5:  # Assignment Identifier (Topia ID)
            mapping.src_col_idx = src_col_topia_id
            mapping.mapping_kind = "exception"
        elif eq_tech.upper() == "ASSIGNMENT_CF!CF_TEXT029":  # Topia File Number
            mapping.src_col_idx = src_col_topia_id
            mapping.mapping_kind = "exception"
        else:
            # Match against source lookup: try technical header first, then label
            matched_src: ColumnMetadata | None = None
            if eq_tech and eq_tech.upper() in src_lookup:
                matched_src = src_lookup[eq_tech.upper()]
                mapping.mapping_kind = "direct_technical"
            elif eq_lbl and eq_lbl.upper() in src_lookup:
                matched_src = src_lookup[eq_lbl.upper()]
                mapping.mapping_kind = "label_match"

            if matched_src:
                mapping.src_col_idx = matched_src.col_index
                mapping.src_tech_field = matched_src.technical_field
                mapping.src_field_name = matched_src.field_name
                mapping.src_display_name = matched_src.display_name
            else:
                mapping.mapping_kind = "unmapped"

        mappings.append(mapping)

    return mappings


def apply_field_transformation(
    raw_val: Any, eq_rule: str | None, eq_header: str | None
) -> tuple[Any, str | None, str | None]:
    """Apply rule conversion based on Equus column instructions.

    Returns: (converted_value, warning_code, dropdown_translation_log)
    """
    clean_val = clean_not_provided(raw_val)
    if clean_val is None:
        return None, None, None

    rule_str = (eq_rule or "").lower()
    header_str = (eq_header or "").upper()

    # 1. Date transformation: match 'US Date' or explicit '_DATE' in header (not 'updates')
    is_date_rule = (
        "date format" in rule_str or "us date" in rule_str or header_str.endswith("_DATE")
    )
    if is_date_rule:
        formatted_date, warn = convert_us_date(clean_val)
        return formatted_date, warn, None

    # 2. ISO-3 Country transformation
    if (
        "country" in rule_str
        or "country_code" in header_str.lower()
        or "citizenship" in header_str.lower()
    ):
        iso3, warn = convert_country_to_iso3(clean_val)
        return iso3, warn, None

    # 3. Dropdown transformations
    if "yesno" in rule_str or "yes/no" in rule_str:
        mapped_val, warn = convert_dropdown("YES_NO", clean_val)
        return mapped_val if mapped_val is not None else clean_val, warn, None

    if "dropdown" in rule_str:
        category = None
        if "GENDER" in header_str:
            category = "GENDER"
        elif "EMPLOYMENT_STATUS" in header_str:
            category = "EMPLOYMENT_STATUS"
        elif "TYPE" in header_str and "EMPLOYEE" in header_str:
            category = "PERSON_STATUS"
        elif "MARITAL_STATUS" in header_str:
            category = "MARITAL_STATUS"
        elif "SPOUSE" in header_str and "RELATIONSHIP" in header_str:
            category = "SPOUSE_RELATIONSHIP"
        elif "SPOUSE" in header_str and "STATUS" in header_str:
            category = "SPOUSE_STATUS"

        if category:
            mapped_val, warn = convert_dropdown(category, clean_val)
            log = None
            if mapped_val and str(mapped_val) != str(clean_val):
                log = f"{category}: '{clean_val}' -> '{mapped_val}'"
            return mapped_val if mapped_val is not None else clean_val, warn, log

        return clean_val, None, None

    return clean_val, None, None


def transform_topia_to_equus(
    source_sheet: ParsedSheet,
    template_path: Path | str,
    strategy: str = DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
    dependent_records: list[dict[str, Any]] | None = None,
) -> TransformationResult:
    """Transform parsed Topia source rows into Equus INSERT and UPDATE records.

    Packs Child 0 onto the parent INSERT row and leaves Col 3 (Employee Number)
    strictly blank on child UPDATE rows.
    """
    template_sheet = parse_three_row_workbook(Path(template_path))
    mappings = build_equus_column_mappings(source_sheet, template_sheet)

    insert_records: list[dict[int, Any]] = []
    update_records: list[dict[int, Any]] = []
    all_records: list[dict[int, Any]] = []
    warnings: list[dict[str, Any]] = []
    dropdown_translations: list[dict[str, Any]] = []

    # Map for easy lookup by eq_col_idx
    col_map = {m.eq_col_idx: m for m in mappings}

    def _find_eq_col(header_name: str) -> int | None:
        for idx, m in col_map.items():
            if m.eq_header and m.eq_header.upper() == header_name.upper():
                return idx
        return None

    # Discover key column indices in target template
    eq_addr_primary_col = _find_eq_col("ASSIGNMENT_MAILING_ADDRESS!PRIMARY_ADDRESS")
    eq_addr_loc_col = _find_eq_col("ASSIGNMENT_MAILING_ADDRESS!LOCATION_TYPE")
    eq_addr_l1_col = _find_eq_col("ASSIGNMENT_MAILING_ADDRESS!LINE_1")
    eq_addr_l2_col = _find_eq_col("ASSIGNMENT_MAILING_ADDRESS!LINE_2")
    eq_addr_l3_col = _find_eq_col("ASSIGNMENT_MAILING_ADDRESS!LINE_3")

    eq_contact_loc_col = _find_eq_col("ASSIGNMENT_EMPLOYEE_CONTACT!LOCATION_TYPE")
    eq_contact_type_col = _find_eq_col("ASSIGNMENT_EMPLOYEE_CONTACT!CONTACT_TYPE")
    eq_contact_num_col = _find_eq_col("ASSIGNMENT_EMPLOYEE_CONTACT!NUMBER_ADDRESS")
    eq_contact_primary_col = _find_eq_col("ASSIGNMENT_EMPLOYEE_CONTACT!PRIMARY_CONTACT")

    eq_phase_col = _find_eq_col("ASSIGNMENT!PHASE")
    eq_intl_col = _find_eq_col("ASSIGNMENT!INTERNATIONAL_RELO")
    eq_from_c_col = _find_eq_col("ASSIGNMENT!FROM_COUNTRY")
    eq_to_c_col = _find_eq_col("ASSIGNMENT!TO_COUNTRY")

    eq_dep_fname_col = _find_eq_col("ASSIGNMENT_DEPENDENT!FIRST_NAME")
    eq_dep_lname_col = _find_eq_col("ASSIGNMENT_DEPENDENT!LAST_NAME")
    eq_dep_mname_col = _find_eq_col("ASSIGNMENT_DEPENDENT!MIDDLE_NAME")
    eq_dep_rel_col = _find_eq_col("ASSIGNMENT_DEPENDENT!RELATIONSHIP")
    eq_dep_gender_col = _find_eq_col("ASSIGNMENT_DEPENDENT!GENDER")
    eq_dep_dob_col = _find_eq_col("ASSIGNMENT_DEPENDENT!BIRTH_DATE")
    eq_dep_status_col = _find_eq_col("ASSIGNMENT_DEPENDENT!STATUS")

    # Discover address, contact, dependent, and cancellation columns in source sheet
    src_address_cols: list[tuple[ColumnMetadata, str]] = []
    src_contact_cols: list[tuple[ColumnMetadata, tuple[str, str]]] = []
    src_dependent_cols: list[tuple[ColumnMetadata, str]] = []
    cancel_col_idx: int | None = None
    src_col_topia_id: int | None = None
    src_col_emp_id: int | None = None

    for col in source_sheet.columns:
        lbl_norm = " ".join((col.display_name or "").lower().split())
        tech_norm = (col.technical_field or "").upper()
        fn_norm = (col.field_name or "").upper()

        if lbl_norm == "cancellation reason":
            cancel_col_idx = col.col_index

        if src_col_topia_id is None and (
            lbl_norm == "assignment id"
            or any(
                n in {"ASSIGNMENT ID", "TOPIA ID", "ASSIGNMENT IDENTIFIER", "TOPIA FILE NUMBER"}
                for n in [tech_norm, fn_norm, col.display_name or ""]
            )
        ):
            src_col_topia_id = col.col_index

        if src_col_emp_id is None and (
            tech_norm == "EMPLOYEE!SYSTEM_NUMBER"
            or any(
                n in {"EMPLOYEE ID", "TALENT LINK ID", "EMPLOYEE NUMBER"}
                for n in [tech_norm, fn_norm, col.display_name or ""]
            )
        ):
            src_col_emp_id = col.col_index

        # Address detection
        if lbl_norm in ADDRESS_COLUMNS:
            src_address_cols.append((col, ADDRESS_COLUMNS[lbl_norm]))
        elif "ASSIGNMENT_MAILING_ADDRESS" in tech_norm:
            loc = ADDRESS_COLUMNS.get(lbl_norm, "Destination Residence")
            src_address_cols.append((col, loc))
        elif "address" in lbl_norm and any(
            k in lbl_norm for k in ["host", "home", "residence", "office"]
        ):
            loc = (
                "Departure Residence"
                if ("home" in lbl_norm or "departure" in lbl_norm)
                else "Destination Residence"
            )
            if "office" in lbl_norm or "work" in lbl_norm:
                loc = (
                    "Destination Office"
                    if ("host" in lbl_norm or "destination" in lbl_norm)
                    else "Departure Office"
                )
            src_address_cols.append((col, loc))

        # Contact detection
        if lbl_norm in CONTACT_COLUMNS:
            src_contact_cols.append((col, CONTACT_COLUMNS[lbl_norm]))
        elif "ASSIGNMENT_EMPLOYEE_CONTACT" in tech_norm:
            ctype = "Telephone"
            loc = "Personal Mobile"
            src_contact_cols.append((col, (loc, ctype)))
        elif "phone" in lbl_norm or "mobile" in lbl_norm:
            ctype = "Telephone"
            loc = "Personal Mobile" if "mobile" in lbl_norm else "Work"
            src_contact_cols.append((col, (loc, ctype)))
        elif "email" in lbl_norm:
            src_contact_cols.append((col, ("Employee Preferred", "Email")))

        # Dependent detection
        if lbl_norm in DEPENDENT_FIELD_MAP:
            src_dependent_cols.append((col, DEPENDENT_FIELD_MAP[lbl_norm]))
        elif "ASSIGNMENT_DEPENDENT" in tech_norm:
            src_dependent_cols.append((col, tech_norm))

    # Fallback column indices if not found by name
    if src_col_emp_id is None and len(source_sheet.columns) >= 5:
        src_col_emp_id = 5
    if src_col_topia_id is None and len(source_sheet.columns) >= 24:
        src_col_topia_id = 24

    dep_cols_map = {
        "fname": eq_dep_fname_col,
        "lname": eq_dep_lname_col,
        "mname": eq_dep_mname_col,
        "rel": eq_dep_rel_col,
        "gender": eq_dep_gender_col,
        "dob": eq_dep_dob_col,
        "status": eq_dep_status_col,
    }

    def _dict_to_dep_row(dep: dict[str, Any]) -> dict[int, Any]:
        row: dict[int, Any] = {}
        fname = clean_not_provided(
            dep.get("first_name")
            or dep.get("FIRST_NAME")
            or dep.get("dependent_first_name")
            or dep.get("fname")
        )
        lname = clean_not_provided(
            dep.get("last_name")
            or dep.get("LAST_NAME")
            or dep.get("dependent_last_name")
            or dep.get("lname")
        )
        mname = clean_not_provided(
            dep.get("middle_name")
            or dep.get("MIDDLE_NAME")
            or dep.get("dependent_middle_name")
        )
        rel = clean_not_provided(
            dep.get("relationship")
            or dep.get("RELATIONSHIP")
            or dep.get("dependent_relationship")
        )
        gender = clean_not_provided(
            dep.get("gender")
            or dep.get("GENDER")
            or dep.get("dependent_gender")
        )
        dob = clean_not_provided(
            dep.get("birth_date")
            or dep.get("BIRTH_DATE")
            or dep.get("dob")
            or dep.get("DOB")
            or dep.get("dependent_dob")
        )
        status = clean_not_provided(
            dep.get("status")
            or dep.get("STATUS")
            or dep.get("dependent_status")
            or dep.get("at_host")
        )

        if fname and dep_cols_map["fname"]:
            row[dep_cols_map["fname"]] = str(fname).strip()
        if lname and dep_cols_map["lname"]:
            row[dep_cols_map["lname"]] = str(lname).strip()
        if mname and dep_cols_map["mname"]:
            row[dep_cols_map["mname"]] = str(mname).strip()
        if rel and dep_cols_map["rel"]:
            row[dep_cols_map["rel"]] = str(rel).strip()
        if gender and dep_cols_map["gender"]:
            g_conv, _ = convert_dropdown("GENDER", gender)
            row[dep_cols_map["gender"]] = g_conv or str(gender).strip()
        if dob and dep_cols_map["dob"]:
            d_conv, _ = convert_us_date(dob)
            row[dep_cols_map["dob"]] = d_conv or str(dob).strip()
        if status and dep_cols_map["status"]:
            row[dep_cols_map["status"]] = str(status).strip()
        return row

    # Pre-pass: sequence assignments per employee and synthesize unique identifiers
    emp_counts: dict[str, int] = defaultdict(int)
    row_meta: list[dict[str, Any]] = []
    emp_to_asg_ids: dict[str, list[str]] = defaultdict(list)
    asg_id_to_row_idx: dict[str, int] = {}
    topia_to_asg_id: dict[str, str] = {}

    for row_idx, src_row in enumerate(source_sheet.data_rows, start=1):
        raw_emp = src_row.get(src_col_emp_id) if src_col_emp_id else None
        raw_topia = src_row.get(src_col_topia_id) if src_col_topia_id else None

        emp_no = normalize_identifier(raw_emp)
        raw_topia_id = normalize_identifier(raw_topia)

        emp_key = emp_no or f"__ROW_{row_idx}__"
        emp_counts[emp_key] += 1
        asg_seq = emp_counts[emp_key]

        # Assignment Identifier Strategy Resolution
        if strategy == STRATEGY_EMPLOYEE_NUMBER:
            asg_id = emp_no if asg_seq == 1 else f"{emp_no}-{asg_seq}"
        elif strategy == STRATEGY_TOPIA_ID_WITH_FALLBACK:
            if raw_topia_id:
                asg_id = raw_topia_id
            else:
                asg_id = emp_no if asg_seq == 1 else f"{emp_no}-{asg_seq}"
                if emp_no:
                    warnings.append(
                        {
                            "code": "IDENTIFIER_FALLBACK",
                            "source_row": row_idx,
                            "equus_column": 5,
                            "equus_header": "Assignment Identifier",
                            "warning": (
                                f"Missing Topia Assignment ID on source row {row_idx}; "
                                f"fell back to Employee Number '{asg_id}'"
                            ),
                        }
                    )
        else:
            asg_id = raw_topia_id or (emp_no if asg_seq == 1 else f"{emp_no}-{asg_seq}")

        if emp_no and asg_id:
            emp_to_asg_ids[emp_no].append(asg_id)
        if raw_topia_id and asg_id:
            topia_to_asg_id[raw_topia_id] = asg_id
        if asg_id:
            asg_id_to_row_idx[asg_id] = row_idx

        row_meta.append(
            {
                "row_idx": row_idx,
                "src_row": src_row,
                "emp_no": emp_no,
                "raw_topia_id": raw_topia_id,
                "asg_seq": asg_seq,
                "asg_id": asg_id,
            }
        )

    # Route secondary dependent records to assignments
    asg_secondary_deps: dict[str, list[dict[int, Any]]] = defaultdict(list)
    if dependent_records:
        for dep_idx, dep in enumerate(dependent_records, start=1):
            dep_emp = normalize_identifier(
                dep.get("employee_id")
                or dep.get("employee_number")
                or dep.get("emp_no")
                or dep.get("Talent Link Id")
            )
            dep_asg = normalize_identifier(
                dep.get("assignment_id")
                or dep.get("assignment_identifier")
                or dep.get("topia_id")
                or dep.get("asg_id")
            )
            dep_name = (
                f"{dep.get('first_name') or dep.get('FIRST_NAME') or ''} {dep.get('last_name') or dep.get('LAST_NAME') or ''}".strip()
                or f"Record #{dep_idx}"
            )

            target_asg_id: str | None = None

            if dep_asg:
                if dep_asg in asg_id_to_row_idx:
                    target_asg_id = dep_asg
                elif dep_asg in topia_to_asg_id:
                    target_asg_id = topia_to_asg_id[dep_asg]
                elif dep_emp and dep_emp in emp_to_asg_ids and len(emp_to_asg_ids[dep_emp]) == 1:
                    target_asg_id = emp_to_asg_ids[dep_emp][0]
                    warnings.append(
                        {
                            "code": "ASSIGNMENT_LINKAGE_FALLBACK",
                            "source_row": None,
                            "warning": (
                                f"Dependent '{dep_name}' specified unknown assignment_id '{dep_asg}'; "
                                f"fell back to employee '{dep_emp}' primary assignment '{target_asg_id}'"
                            ),
                        }
                    )
                else:
                    warnings.append(
                        {
                            "code": "UNLINKED_DEPENDENT_RECORD",
                            "source_row": None,
                            "warning": f"Dependent '{dep_name}' references unknown assignment '{dep_asg}'; record omitted",
                        }
                    )
                    continue
            elif dep_emp:
                if dep_emp in emp_to_asg_ids:
                    matched_asgs = emp_to_asg_ids[dep_emp]
                    if len(matched_asgs) == 1:
                        target_asg_id = matched_asgs[0]
                    else:
                        target_asg_id = matched_asgs[0]
                        warnings.append(
                            {
                                "code": "AMBIGUOUS_DEPENDENT_LINKAGE",
                                "source_row": None,
                                "warning": (
                                    f"Dependent '{dep_name}' references employee '{dep_emp}' who has "
                                    f"{len(matched_asgs)} assignments; linked to primary assignment '{target_asg_id}'"
                                ),
                            }
                        )
                else:
                    warnings.append(
                        {
                            "code": "ORPHAN_DEPENDENT_RECORD",
                            "source_row": None,
                            "warning": f"Dependent '{dep_name}' references non-existent employee '{dep_emp}'; record omitted",
                        }
                    )
                    continue
            else:
                warnings.append(
                    {
                        "code": "UNLINKED_DEPENDENT_RECORD",
                        "source_row": None,
                        "warning": f"Dependent '{dep_name}' is missing both employee and assignment identifiers; record omitted",
                    }
                )
                continue

            dep_row = _dict_to_dep_row(dep)
            if dep_row and target_asg_id:
                asg_secondary_deps[target_asg_id].append(dep_row)

    seen_employees: set[str] = set()

    for item in row_meta:
        row_idx = item["row_idx"]
        src_row = item["src_row"]
        emp_no = item["emp_no"]
        raw_topia_id = item["raw_topia_id"]
        asg_seq = item["asg_seq"]
        asg_id = item["asg_id"]

        # 1. Build Address child records for this source row
        addr_recs: list[dict[int, Any]] = []
        for col_meta, loc_type in src_address_cols:
            val = src_row.get(col_meta.col_index)
            clean_addr = clean_not_provided(val)
            if clean_addr:
                l1, l2, l3 = split_multiline_address(clean_addr)
                rec: dict[int, Any] = {}
                if eq_addr_primary_col:
                    rec[eq_addr_primary_col] = "Yes"
                if eq_addr_loc_col:
                    rec[eq_addr_loc_col] = loc_type
                if eq_addr_l1_col and l1:
                    rec[eq_addr_l1_col] = l1
                if eq_addr_l2_col and l2:
                    rec[eq_addr_l2_col] = l2
                if eq_addr_l3_col and l3:
                    rec[eq_addr_l3_col] = l3
                if rec:
                    addr_recs.append(rec)

        # 2. Build Contact child records for this source row
        contact_recs: list[dict[int, Any]] = []
        for col_meta, (loc_type, ctype) in src_contact_cols:
            val = src_row.get(col_meta.col_index)
            clean_contact = clean_not_provided(val)
            if clean_contact:
                norm_contact = normalize_identifier(clean_contact) or str(clean_contact).strip()
                rec = {}
                if eq_contact_loc_col:
                    rec[eq_contact_loc_col] = loc_type
                if eq_contact_type_col:
                    rec[eq_contact_type_col] = ctype
                if eq_contact_num_col:
                    rec[eq_contact_num_col] = norm_contact
                if eq_contact_primary_col:
                    rec[eq_contact_primary_col] = "Yes"
                if rec:
                    contact_recs.append(rec)

        # 3. Build Dependent child records (embedded from source row + secondary passed records)
        dep_recs: list[dict[int, Any]] = []
        embedded_dep_data: dict[str, Any] = {}
        for col_meta, target_field in src_dependent_cols:
            val = src_row.get(col_meta.col_index)
            clean_v = clean_not_provided(val)
            if clean_v:
                if "FIRST_NAME" in target_field:
                    embedded_dep_data["first_name"] = clean_v
                elif "LAST_NAME" in target_field:
                    embedded_dep_data["last_name"] = clean_v
                elif "MIDDLE_NAME" in target_field:
                    embedded_dep_data["middle_name"] = clean_v
                elif "RELATIONSHIP" in target_field:
                    embedded_dep_data["relationship"] = clean_v
                elif "GENDER" in target_field:
                    embedded_dep_data["gender"] = clean_v
                elif "BIRTH_DATE" in target_field:
                    embedded_dep_data["birth_date"] = clean_v
                elif "STATUS" in target_field:
                    embedded_dep_data["status"] = clean_v

        if embedded_dep_data:
            emb_row = _dict_to_dep_row(embedded_dep_data)
            if emb_row:
                dep_recs.append(emb_row)

        if asg_id and asg_id in asg_secondary_deps:
            dep_recs.extend(asg_secondary_deps[asg_id])

        # Total output rows for this assignment
        n_rows = max(1, len(addr_recs), len(contact_recs), len(dep_recs))

        for i in range(n_rows):
            if i == 0:
                # Row 0: Primary INSERT record
                insert_row: dict[int, Any] = {}
                is_repeat_emp = (asg_seq > 1) or (emp_no in seen_employees if emp_no else False)
                insert_row[1] = "IGNORE" if is_repeat_emp else "INSERT"
                insert_row[2] = "INSERT"
                insert_row[3] = emp_no
                insert_row[4] = "NEW"
                insert_row[5] = asg_id

                # Populate all primary mapped columns
                for eq_idx in range(1, len(mappings) + 1):
                    m = col_map.get(eq_idx)
                    if not m:
                        continue
                    if eq_idx in (1, 2, 3, 4, 5):
                        continue  # control columns already set

                    header = m.eq_header or ""
                    # Skip child entity columns on primary row; packed via Child 0
                    if any(
                        p in header
                        for p in [
                            "ASSIGNMENT_MAILING_ADDRESS",
                            "ASSIGNMENT_EMPLOYEE_CONTACT",
                            "ASSIGNMENT_DEPENDENT",
                        ]
                    ):
                        continue

                    # Legacy Topia File Number column
                    if header.upper() == "ASSIGNMENT_CF!CF_TEXT029":
                        if raw_topia_id:
                            insert_row[eq_idx] = raw_topia_id
                        elif asg_id:
                            insert_row[eq_idx] = asg_id
                        continue

                    if m.mapping_kind == "system_constant":
                        insert_row[eq_idx] = "NEW"
                    elif m.src_col_idx and m.src_col_idx in src_row:
                        raw_val = src_row[m.src_col_idx]
                        if "NUMBER" in header or "ID" in header or "SYSTEM_NUMBER" in header:
                            norm_id = normalize_identifier(raw_val)
                            if norm_id is not None:
                                insert_row[eq_idx] = norm_id
                                continue

                        converted_val, warn, trans_log = apply_field_transformation(
                            raw_val, m.eq_rule, m.eq_header
                        )
                        if converted_val is not None:
                            insert_row[eq_idx] = converted_val

                        if warn:
                            warnings.append(
                                {
                                    "code": "FIELD_TRANSFORMATION_WARNING",
                                    "source_row": row_idx,
                                    "equus_column": eq_idx,
                                    "equus_header": m.eq_header,
                                    "warning": warn,
                                }
                            )
                        if trans_log:
                            dropdown_translations.append(
                                {
                                    "source_row": row_idx,
                                    "field": m.eq_header,
                                    "translation": trans_log,
                                }
                            )

                # Business Rule 1: Cancellation Reason
                if cancel_col_idx and src_row.get(cancel_col_idx):
                    if eq_phase_col:
                        insert_row[eq_phase_col] = "Cancelled"

                # Business Rule 2: International Relocation Default
                if eq_intl_col and eq_intl_col not in insert_row:
                    from_c = insert_row.get(eq_from_c_col) if eq_from_c_col else None
                    to_c = insert_row.get(eq_to_c_col) if eq_to_c_col else None
                    if from_c and to_c:
                        insert_row[eq_intl_col] = "Yes" if from_c != to_c else "No"
                    else:
                        insert_row[eq_intl_col] = "Yes"

                # Pack Child 0 onto the INSERT row
                if addr_recs:
                    insert_row.update(addr_recs[0])
                if contact_recs:
                    insert_row.update(contact_recs[0])
                if dep_recs:
                    insert_row.update(dep_recs[0])

                insert_records.append(insert_row)
                all_records.append(insert_row)
                if emp_no:
                    seen_employees.add(emp_no)

            else:
                # Rows 1..N-1: UPDATE records for subsequent child entities
                update_row: dict[int, Any] = {}
                update_row[1] = "IGNORE"
                update_row[2] = "UPDATE"
                # Col 3 (Employee Number) and Col 4 (Assignment Number) strictly omitted (None)
                update_row[5] = asg_id

                # Pack Child i onto this UPDATE row
                if i < len(addr_recs):
                    update_row.update(addr_recs[i])
                if i < len(contact_recs):
                    update_row.update(contact_recs[i])
                if i < len(dep_recs):
                    update_row.update(dep_recs[i])

                update_records.append(update_row)
                all_records.append(update_row)

    mapped_count = sum(1 for m in mappings if m.mapping_kind != "unmapped")
    total_template_cols = len(mappings)
    coverage = (
        round((mapped_count / total_template_cols) * 100, 2) if total_template_cols > 0 else 0.0
    )

    return TransformationResult(
        insert_records=insert_records,
        update_records=update_records,
        all_output_records=all_records,
        mappings=mappings,
        warnings=warnings,
        dropdown_translations=dropdown_translations,
        total_evaluated_rows=len(source_sheet.data_rows),
        mapped_columns_count=mapped_count,
        unmapped_columns_count=total_template_cols - mapped_count,
        coverage_percentage=coverage,
        strategy=strategy,
    )

