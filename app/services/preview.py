from pathlib import Path

from openpyxl import load_workbook

from app.schemas import MappingStatus, MappingType
from app.services.transform import required_issue, transform_value


def preview_direct_mappings(path: Path, mappings: list[dict]) -> dict:
    """Produce deterministic proposed records for approved direct mappings only."""
    approved = [item for item in mappings if item["status"] == MappingStatus.APPROVED]
    unresolved = [item for item in mappings if item["status"] != MappingStatus.APPROVED]
    unsupported = [
        item
        for item in approved
        if item["mapping_type"] not in {MappingType.DIRECT, MappingType.TRANSFORMED}
    ]
    usable = [
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
    total_evaluated = 0
    structural_empty_rows = 0
    for worksheet in workbook.worksheets:
        sheet_mappings = [item for item in usable if item["source_sheet"] == worksheet.title]
        if not sheet_mappings:
            continue
        rows = worksheet.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers:
            continue
        columns = {
            str(value).strip(): index for index, value in enumerate(headers) if value is not None
        }
        for row_number, row in enumerate(rows, start=2):
            total_evaluated += 1
            if not any(value not in (None, "") for value in row):
                structural_empty_rows += 1
                continue
            proposed: dict[str, object] = {}
            for mapping in sheet_mappings:
                position = columns.get(mapping["source_field"])
                if position is None:
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
        "structural_empty_rows": structural_empty_rows,
        "records": records,
        "warnings": warnings,
        "issues": issues,
        "rejected_records": len({(item["sheet"], item["row"]) for item in issues}),
        "equus_writes": False,
    }
