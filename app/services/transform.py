from typing import Any

from app.schemas import IssueSeverity, ValidationIssue

SUPPORTED_OPERATIONS = {"trim", "upper", "lower"}


def validate_transformation(specification: dict[str, Any] | None) -> None:
    if specification is None:
        return
    operation = specification.get("op")
    if operation not in SUPPORTED_OPERATIONS:
        raise ValueError("Unsupported transformation operation")


def transform_value(value: object, specification: dict[str, Any] | None) -> object:
    if specification is None or value is None:
        return value
    operation = specification["op"]
    if not isinstance(value, str):
        return value
    return {"trim": value.strip, "upper": value.upper, "lower": value.lower}[operation]()


def required_issue(value: object, *, sheet: str, row: int, field: str) -> ValidationIssue | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ValidationIssue(
            code="REQUIRED_VALUE_MISSING",
            severity=IssueSeverity.REJECTED,
            message="Required target value is missing.",
            sheet=sheet,
            row=row,
            field=field,
        )
    return None
