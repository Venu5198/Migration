"""Reconciliation and validation engine for Topia to Equus transformations."""

from typing import Any

from app.services.equus.transformer import TransformationResult


def reconcile_equus_transformation(result: TransformationResult) -> dict[str, Any]:
    """Validate relational integrity, required keys, duplicate keys, and 1:N expansion."""
    errors: list[str] = []

    # 1. Required Keys Validation on INSERT records

    seen_assignment_ids: set[str] = set()
    seen_employee_numbers: set[str] = set()
    valid_insert_asg_ids: set[str] = set()

    for idx, rec in enumerate(result.insert_records, start=1):
        emp_no = rec.get(3)
        asg_no = rec.get(4)
        asg_id = rec.get(5)

        if not emp_no:
            errors.append(f"INSERT record #{idx} is missing required Employee Number (Col 3)")
        if not asg_no:
            errors.append(f"INSERT record #{idx} is missing required Assignment Number (Col 4)")
        if not asg_id:
            errors.append(f"INSERT record #{idx} is missing required Assignment Identifier (Col 5)")

        if asg_id:
            asg_key = str(asg_id).strip()
            if asg_key in seen_assignment_ids:
                errors.append(f"Duplicate Assignment Identifier detected: '{asg_key}'")
            seen_assignment_ids.add(asg_key)
            valid_insert_asg_ids.add(asg_key)

        if emp_no:
            seen_employee_numbers.add(str(emp_no).strip())

    # 2. Relational Integrity on UPDATE records
    for idx, rec in enumerate(result.update_records, start=1):
        asg_id = rec.get(5)
        emp_no = rec.get(3)
        if not asg_id or str(asg_id).strip() not in valid_insert_asg_ids:
            errors.append(
                f"UPDATE record #{idx} references unparented Assignment Identifier: '{asg_id}'"
            )
        if not emp_no:
            errors.append(f"UPDATE record #{idx} is missing Employee Number reference")

    # 3. 1:N Relationship Expansion Accounting
    source_count = result.total_evaluated_rows
    insert_count = len(result.insert_records)
    update_count = len(result.update_records)
    total_output = len(result.all_output_records)

    expansion_ratio = round(total_output / insert_count, 2) if insert_count > 0 else 1.0

    # Determine overall migration verification status
    if errors:
        status = "FAILED"
    elif result.warnings:
        status = "COMPLETED_WITH_WARNINGS"
    else:
        status = "VERIFIED_PASS"

    return {
        "status": status,
        "is_valid": len(errors) == 0,
        "source_rows_evaluated": source_count,
        "insert_records_count": insert_count,
        "update_records_count": update_count,
        "total_output_records": total_output,
        "expansion_ratio": expansion_ratio,
        "mapped_columns": result.mapped_columns_count,
        "unmapped_columns": result.unmapped_columns_count,
        "coverage_percentage": result.coverage_percentage,
        "errors": errors,
        "warnings": [w["warning"] for w in result.warnings if "warning" in w],
        "validation_errors_count": len(errors),
        "transformation_warnings_count": len(result.warnings),
    }
