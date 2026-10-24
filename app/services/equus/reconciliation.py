"""Reconciliation and validation engine for Topia to Equus transformations."""

from typing import Any

from app.services.equus.transformer import TransformationResult


def reconcile_equus_transformation(result: TransformationResult) -> dict[str, Any]:
    """Validate relational integrity, required keys, duplicate keys, and 1:N expansion."""
    errors: list[str] = []

    # 1. Required Keys Validation on INSERT records

    seen_assignment_ids: set[str] = set()
    seen_employee_numbers: set[str] = set()
    seen_insert_emp_numbers: set[str] = set()
    valid_insert_asg_ids: set[str] = set()

    for idx, rec in enumerate(result.insert_records, start=1):
        emp_no = rec.get(3)
        asg_no = rec.get(4)
        asg_id = rec.get(5)
        cmd_a = rec.get(1)
        cmd_b = rec.get(2)

        if not emp_no:
            errors.append(f"INSERT record #{idx} is missing required Employee Number (Col 3)")
        if not asg_no:
            errors.append(f"INSERT record #{idx} is missing required Assignment Number (Col 4)")
        if not asg_id:
            errors.append(f"INSERT record #{idx} is missing required Assignment Identifier (Col 5)")

        if cmd_b and cmd_b != "INSERT":
            errors.append(
                f"INSERT record #{idx} has invalid Assignment Command '{cmd_b}'; expected 'INSERT'"
            )
        if cmd_a and cmd_a not in ("INSERT", "IGNORE"):
            errors.append(
                f"INSERT record #{idx} has invalid Col 1 '{cmd_a}'; expected 'INSERT' or 'IGNORE'"
            )

        if asg_id:
            asg_key = str(asg_id).strip()
            if asg_key in seen_assignment_ids:
                errors.append(f"Duplicate Assignment Identifier detected: '{asg_key}'")
            seen_assignment_ids.add(asg_key)
            valid_insert_asg_ids.add(asg_key)

        if emp_no:
            emp_key = str(emp_no).strip()
            if cmd_a == "INSERT":
                if emp_key in seen_insert_emp_numbers:
                    errors.append(
                        f"INSERT record #{idx} specifies Col 1='INSERT' for employee '{emp_key}', "
                        "but employee demographics were already inserted; subsequent assignments for the same "
                        "employee must specify Col 1='IGNORE'"
                    )
                seen_insert_emp_numbers.add(emp_key)
            elif cmd_a == "IGNORE":
                if emp_key not in seen_insert_emp_numbers:
                    errors.append(
                        f"INSERT record #{idx} specifies Col 1='IGNORE' for employee '{emp_key}', "
                        "but no preceding INSERT record exists for this employee"
                    )
            seen_employee_numbers.add(emp_key)

    # 2. Relational Integrity on UPDATE records
    for idx, rec in enumerate(result.update_records, start=1):
        asg_id = rec.get(5)
        emp_no = rec.get(3)
        asg_no = rec.get(4)
        cmd_a = rec.get(1)
        cmd_b = rec.get(2)

        # Assignment Identifier is required and must reference a valid parent INSERT record
        if not asg_id:
            errors.append(f"UPDATE record #{idx} is missing required Assignment Identifier (Col 5)")
        elif str(asg_id).strip() not in valid_insert_asg_ids:
            errors.append(
                f"UPDATE record #{idx} references unparented Assignment Identifier: '{asg_id}'"
            )

        # In Equus EAFH, child UPDATE rows must leave Employee Number and Assignment Number blank
        if emp_no is not None:
            errors.append(
                f"UPDATE record #{idx} contains unexpected Employee Number '{emp_no}'; "
                "child update rows must leave Col 3 blank"
            )
        if asg_no is not None:
            errors.append(
                f"UPDATE record #{idx} contains unexpected Assignment Number '{asg_no}'; "
                "child update rows must leave Col 4 blank"
            )

        # Col 1 must be IGNORE and Col 2 must be UPDATE
        if cmd_a != "IGNORE":
            errors.append(
                f"UPDATE record #{idx} has invalid Col 1 '{cmd_a}'; "
                "child update rows must specify 'IGNORE'"
            )
        if cmd_b != "UPDATE":
            errors.append(
                f"UPDATE record #{idx} has invalid Assignment Command '{cmd_b}'; expected 'UPDATE'"
            )

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

    # Record Accounting Semantics:
    # - source_rows_evaluated / source_rows: Source assignment records extracted from Topia export
    # - total_output_records / output_records: Total generated Equus rows (INSERT + UPDATE)
    # - insert_records_count / insert_records: Primary assignment rows (1:1 with source rows)
    # - update_records_count / update_records: Child / secondary entity rows (tax, entities, etc.)
    # - attempted_records: Total generated records submitted to reconciliation
    # - accepted_records: Records approved for downstream Equus import (total_output if valid, 0 if failed)
    # - rejected_records: Records blocked from import due to constraint violations (total_output if failed, 0 if valid)
    is_valid = len(errors) == 0
    accepted_records = total_output if is_valid else 0
    rejected_records = total_output if not is_valid else 0

    return {
        "status": status,
        "is_valid": is_valid,
        "source_rows_evaluated": source_count,
        "source_rows": source_count,
        "insert_records_count": insert_count,
        "insert_records": insert_count,
        "update_records_count": update_count,
        "update_records": update_count,
        "total_output_records": total_output,
        "output_records": total_output,
        "attempted_records": total_output,
        "accepted_records": accepted_records,
        "rejected_records": rejected_records,
        "expansion_ratio": expansion_ratio,
        "mapped_columns": result.mapped_columns_count,
        "unmapped_columns": result.unmapped_columns_count,
        "coverage_percentage": result.coverage_percentage,
        "assignment_id_strategy": getattr(result, "strategy", "EMPLOYEE_NUMBER"),
        "errors": errors,
        "warnings": [w["warning"] for w in result.warnings if "warning" in w],
        "validation_errors_count": len(errors),
        "transformation_warnings_count": len(result.warnings),
    }

