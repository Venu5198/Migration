"""Equus transformation engine: converts parsed Topia rows into Equus INSERT and UPDATE records."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.equus.mapping_config import (
    clean_not_provided,
    convert_country_to_iso3,
    convert_dropdown,
    convert_us_date,
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


def build_equus_column_mappings(
    source_sheet: ParsedSheet, template_sheet: ParsedSheet
) -> list[ColumnMapping]:
    """Map source columns to Equus template columns based on technical field, label, and rules."""
    # Build comprehensive lookup for source columns
    src_lookup: dict[str, ColumnMetadata] = {}
    for col in source_sheet.columns:
        for val in [col.technical_field, col.field_name, col.display_name]:
            if val:
                key = str(val).strip().upper()
                if key not in src_lookup:
                    src_lookup[key] = col

    # Find key columns in source
    src_col_topia_id = None
    src_col_emp_id = None
    for col in source_sheet.columns:
        names = [
            (col.technical_field or "").upper(),
            (col.field_name or "").upper(),
            (col.display_name or "").upper(),
        ]
        if src_col_topia_id is None and any(
            n in {"ASSIGNMENT ID", "TOPIA ID", "ASSIGNMENT IDENTIFIER", "TOPIA FILE NUMBER"}
            for n in names
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

        # General free-text dropdown: pass through cleaned string
        return clean_val, None, None

    # Pass through cleaned value
    return clean_val, None, None


def transform_topia_to_equus(
    source_sheet: ParsedSheet, template_path: Path | str
) -> TransformationResult:
    """Transform parsed Topia source rows into Equus INSERT and UPDATE records."""
    template_sheet = parse_three_row_workbook(Path(template_path))
    mappings = build_equus_column_mappings(source_sheet, template_sheet)

    insert_records: list[dict[int, Any]] = []
    update_records: list[dict[int, Any]] = []
    warnings: list[dict[str, Any]] = []
    dropdown_translations: list[dict[str, Any]] = []

    # Map for easy lookup by eq_col_idx
    col_map = {m.eq_col_idx: m for m in mappings}

    # Find secondary address and contact columns in source for child UPDATE records
    src_cols_secondary_addresses: list[tuple[str, int]] = []
    src_cols_secondary_contacts: list[tuple[str, int]] = []
    for col in source_sheet.columns:
        lbl = (col.display_name or "").lower()
        if "host address" in lbl and "personal" in lbl:
            src_cols_secondary_addresses.append(("Host Residence Address", col.col_index))
        elif "work host address" in lbl:
            src_cols_secondary_addresses.append(("Work Host Address", col.col_index))
        elif "phone number" in lbl:
            src_cols_secondary_contacts.append(("Phone", col.col_index))
        elif "mobile phone" in lbl:
            src_cols_secondary_contacts.append(("Mobile", col.col_index))

    # Equus columns for Child records
    eq_addr_loc_col = next(
        (
            m.eq_col_idx
            for m in mappings
            if m.eq_header == "ASSIGNMENT_MAILING_ADDRESS!LOCATION_TYPE"
        ),
        None,
    )
    eq_contact_num_col = next(
        (
            m.eq_col_idx
            for m in mappings
            if m.eq_header == "ASSIGNMENT_EMPLOYEE_CONTACT!NUMBER_ADDRESS"
        ),
        None,
    )
    eq_contact_type_col = next(
        (
            m.eq_col_idx
            for m in mappings
            if m.eq_header == "ASSIGNMENT_EMPLOYEE_CONTACT!CONTACT_TYPE"
        ),
        None,
    )

    for row_idx, src_row in enumerate(source_sheet.data_rows, start=1):
        # 1. Main INSERT Record
        insert_row: dict[int, Any] = {}
        insert_row[1] = "INSERT"  # Col 1: A
        insert_row[2] = "INSERT"  # Col 2: Assignment Command
        insert_row[4] = "NEW"  # Col 4: Assignment Number

        emp_no = None
        asg_id = None

        for eq_idx in range(1, len(mappings) + 1):
            m = col_map.get(eq_idx)
            if not m:
                continue

            # Skip child entity columns on the parent INSERT row (unless primary/spouse)
            header = m.eq_header or ""
            if any(
                p in header
                for p in [
                    "ASSIGNMENT_MAILING_ADDRESS",
                    "ASSIGNMENT_EMPLOYEE_CONTACT",
                    "ASSIGNMENT_DEPENDENT",
                ]
            ):
                continue

            if m.mapping_kind == "system_command":
                continue  # already set
            elif m.mapping_kind == "system_constant":
                insert_row[eq_idx] = "NEW"
            elif m.src_col_idx and m.src_col_idx in src_row:
                raw_val = src_row[m.src_col_idx]
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

                if eq_idx == 3:
                    emp_no = converted_val
                elif eq_idx == 5:
                    asg_id = converted_val

        # Fallback for keys if not in row dict
        if not emp_no and 3 in insert_row:
            emp_no = insert_row[3]
        if not asg_id and 5 in insert_row:
            asg_id = insert_row[5]

        # Default International Relo to 'Yes' if unpopulated
        if 24 in col_map and 24 not in insert_row:
            insert_row[24] = "Yes"

        insert_records.append(insert_row)

        # 2. Child UPDATE records for secondary addresses
        for addr_label, src_c in src_cols_secondary_addresses:
            addr_val = src_row.get(src_c)
            clean_addr = clean_not_provided(addr_val)
            if clean_addr:
                update_addr: dict[int, Any] = {
                    1: "UPDATE",
                    2: "UPDATE",
                    3: emp_no,
                    4: "NEW",
                    5: asg_id,
                }
                if eq_addr_loc_col:
                    update_addr[eq_addr_loc_col] = addr_label
                update_records.append(update_addr)

        # 3. Child UPDATE records for secondary contacts
        for contact_type, src_c in src_cols_secondary_contacts:
            contact_val = src_row.get(src_c)
            clean_contact = clean_not_provided(contact_val)
            if clean_contact:
                update_contact: dict[int, Any] = {
                    1: "UPDATE",
                    2: "UPDATE",
                    3: emp_no,
                    4: "NEW",
                    5: asg_id,
                }
                if eq_contact_num_col:
                    update_contact[eq_contact_num_col] = str(clean_contact)
                if eq_contact_type_col:
                    update_contact[eq_contact_type_col] = contact_type
                update_records.append(update_contact)

    all_records = insert_records + update_records
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
    )
