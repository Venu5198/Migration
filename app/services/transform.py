from typing import Any

from app.schemas import IssueSeverity, ValidationIssue

SUPPORTED_OPERATIONS = {"trim", "upper", "lower", "us_date", "date_format", "iso3", "country_code"}

DATE_FIELDS = {
    "birth_date",
    "birthdate",
    "dob",
    "date_of_birth",
    "birth date",
    "start_date",
    "end_date",
    "effective_date",
    "assignment_start",
    "assignment_end",
    "us date format",
}

COUNTRY_FIELDS = {
    "country_code",
    "country",
    "from_country",
    "to_country",
    "home_country",
    "host_country",
    "citizenship",
    "nationality",
    "iso3",
    "home country",
    "host country",
}


def is_blank_or_ambiguous_header(name: str | None) -> bool:
    if not name or not str(name).strip():
        return True
    clean = str(name).strip().lower()
    return clean.startswith("__blank_") or clean.startswith("_blank_") or clean == "unnamed" or clean.startswith("unnamed:")


def is_date_identifier(name: str | None) -> bool:
    if not name:
        return False
    clean = str(name).strip().lower()
    if clean.endswith("_date") or clean.startswith("date_") or clean in DATE_FIELDS:
        return True
    return any(k in clean for k in ["birth_date", "date of birth", "!birth_date", "us date format"])


def is_country_identifier(name: str | None) -> bool:
    if not name:
        return False
    clean = str(name).strip().lower()
    if clean.endswith("_country") or clean.startswith("country_") or clean in COUNTRY_FIELDS:
        return True
    return any(k in clean for k in ["country_code", "home country", "host country", "!from_country", "!to_country", "from_country", "to_country", "citizenship"])


def validate_mapping_compatibility(
    source_field: str,
    target_field: str,
    transformation: dict[str, Any] | None = None,
    mapping_type: str = "direct",
) -> None:
    """Validate source-to-target field compatibility, rejecting invalid date/country pairings and blank headers."""
    if mapping_type in {"unresolved", "excluded"}:
        return

    # Task 5: Blank headers cannot be mapped to target fields
    if is_blank_or_ambiguous_header(source_field):
        raise ValueError(
            f"Ambiguous or empty source header '{source_field}' cannot be mapped to target field '{target_field}'. Review and label the column first."
        )

    # Check for date transformation
    trans_op = ""
    if transformation:
        trans_op = str(transformation.get("op", "")).lower()

    is_date_trans = any(k in trans_op for k in ["date", "us_date", "date_format"]) or (
        transformation and any("date" in str(k).lower() or "date" in str(v).lower() for k, v in transformation.items())
    )

    # Task 4 & 6: Date transformation or date source cannot be applied to a country field
    if is_country_identifier(target_field):
        if is_date_trans:
            raise ValueError(
                f"Cannot apply date-format transformation to country code field '{target_field}'. Valid country transformation required."
            )
        if is_date_identifier(source_field):
            raise ValueError(
                f"Incompatible mapping: cannot map date source field '{source_field}' to country code field '{target_field}'."
            )

    # Country transformation or country source cannot be applied to a date field
    is_country_trans = any(k in trans_op for k in ["country", "iso3"]) or (
        transformation and any("country" in str(k).lower() or "iso3" in str(v).lower() for k, v in transformation.items())
    )
    if is_date_identifier(target_field):
        if is_country_trans:
            raise ValueError(
                f"Cannot apply country transformation to date field '{target_field}'. Valid date transformation required."
            )
        if is_country_identifier(source_field):
            raise ValueError(
                f"Incompatible mapping: cannot map country source field '{source_field}' to date field '{target_field}'."
            )


def validate_transformation(specification: dict[str, Any] | None) -> None:
    if specification is None:
        return
    operation = specification.get("op")
    if operation not in SUPPORTED_OPERATIONS:
        raise ValueError("Unsupported transformation operation")


def transform_value(value: object, specification: dict[str, Any] | None) -> object:
    if specification is None or value is None:
        return value
    operation = specification.get("op")
    if operation in {"trim", "upper", "lower"}:
        if not isinstance(value, str):
            return value
        return {"trim": value.strip, "upper": value.upper, "lower": value.lower}[operation]()
    if operation in {"us_date", "date_format"}:
        from app.services.equus.mapping_config import convert_us_date
        converted, _ = convert_us_date(value)
        return converted if converted is not None else value
    if operation in {"iso3", "country_code"}:
        from app.services.equus.mapping_config import convert_country_to_iso3
        converted, _ = convert_country_to_iso3(value)
        return converted if converted is not None else value
    return value


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

