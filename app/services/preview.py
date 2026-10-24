from pathlib import Path

from openpyxl import load_workbook

from app.schemas import MappingStatus, MappingType
from app.services.transform import (
    is_blank_or_ambiguous_header,
    required_issue,
    transform_value,
    validate_mapping_compatibility,
)
from app.services.workbooks import detect_sheet_layout


def preview_direct_mappings(path: Path, mappings: list[dict]) -> dict:
    """Produce deterministic proposed records for approved direct mappings only.

    Excludes header, instruction, and metadata rows from data evaluation.
    Enforces source-to-target field compatibility and rejects ambiguous or blank headers.
    """
    approved = [item for item in mappings if item["status"] == MappingStatus.APPROVED]
    unresolved = [item for item in mappings if item["status"] != MappingStatus.APPROVED]
    unsupported = [
        item
        for item in approved
        if item["mapping_type"] not in {MappingType.DIRECT, MappingType.TRANSFORMED}
    ]
    usable_candidates = [
        item
        for item in approved
        if item["mapping_type"] in {MappingType.DIRECT, MappingType.TRANSFORMED}
    ]
    workbook = load_workbook(path, read_only=True, data_only=False)
    records: list[dict] = []
    warnings: list[dict] = []
    issues: list[dict] = []

    for mapping in unresolved:
        warnings.append({"code": "UNAPPROVED_MAPPING", "mapping_id": mapping["mapping_id"]})
    for mapping in unsupported:
        warnings.append({"code": "UNSUPPORTED_TRANSFORMATION", "mapping_id": mapping["mapping_id"]})

    # Filter out incompatible mappings and blank headers before previewing
    usable: list[dict] = []
    for mapping in usable_candidates:
        src_field = mapping.get("source_field", "")
        tgt_field = mapping.get("target_field", "")
        m_id = mapping.get("mapping_id", "")

        if is_blank_or_ambiguous_header(src_field):
            warnings.append(
                {
                    "code": "AMBIGUOUS_SOURCE_HEADER",
                    "mapping_id": m_id,
                    "message": (
                        f"Blank or ambiguous source header '{src_field}' cannot be previewed."
                    ),
                }
            )
            continue

        try:
            validate_mapping_compatibility(
                src_field,
                tgt_field,
                mapping.get("transformation"),
                mapping.get("mapping_type", "direct"),
            )
        except ValueError as exc:
            warnings.append(
                {
                    "code": "INCOMPATIBLE_FIELD_MAPPING",
                    "mapping_id": m_id,
                    "message": str(exc),
                }
            )
            continue

        usable.append(mapping)

    total_evaluated = 0
    structural_empty_rows = 0
    overall_header_depth = 1
    overall_data_start = 2

    for worksheet in workbook.worksheets:
        sheet_mappings = [item for item in usable if item["source_sheet"] == worksheet.title]
        layout = detect_sheet_layout(worksheet)
        if layout.kind == "empty":
            continue

        overall_header_depth = max(overall_header_depth, layout.header_rows_count)
        overall_data_start = max(overall_data_start, layout.data_start_row)

        if not sheet_mappings:
            continue

        col_lookup = layout.column_lookup

        rows = worksheet.iter_rows(values_only=True)
        # Fast forward past all header rows
        for _ in range(layout.data_start_row - 1):
            next(rows, None)

        for row_number, row in enumerate(rows, start=layout.data_start_row):
            total_evaluated += 1
            if not any(value not in (None, "") for value in row):
                structural_empty_rows += 1
                continue
            proposed: dict[str, object] = {}
            for mapping in sheet_mappings:
                src_f = mapping["source_field"]
                position = col_lookup.get(src_f) or col_lookup.get(src_f.lower())
                if position is None or position >= len(row):
                    warnings.append(
                        {
                            "code": "SOURCE_FIELD_NOT_FOUND",
                            "mapping_id": mapping["mapping_id"],
                            "sheet": worksheet.title,
                        }
                    )
                    continue
                value = transform_value(row[position], mapping.get("transformation"))
                proposed[mapping["target_field"]] = value
                if mapping.get("required"):
                    issue = required_issue(
                        value, sheet=worksheet.title, row=row_number, field=mapping["target_field"]
                    )
                    if issue:
                        issues.append(issue.model_dump())
            records.append(
                {
                    "sheet": worksheet.title,
                    "row": row_number,
                    "target_entity": sheet_mappings[0]["target_entity"],
                    "proposed": proposed,
                }
            )
    workbook.close()
    return {
        "records_evaluated": total_evaluated,
        "eligible_records": len(records),
        "header_rows_count": overall_header_depth,
        "data_start_row": overall_data_start,
        "structural_empty_rows": structural_empty_rows,
        "records": records,
        "warnings": warnings,
        "issues": issues,
        "rejected_records": len({(item["sheet"], item["row"]) for item in issues}),
        "equus_writes": False,
    }
