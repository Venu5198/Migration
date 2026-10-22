import hashlib
import re
import uuid
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

from app.core.errors import DomainError
from app.schemas import IssueSeverity, SheetSchema, ValidationIssue

ALLOWED_SUFFIXES = {".xlsx", ".xlsm"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str) -> str:
    candidate = _SAFE_NAME.sub("_", Path(filename).name).strip("._")
    if not candidate:
        raise DomainError("INVALID_FILENAME", "The filename is not usable.")
    return candidate[:180]


def validate_excel_upload(
    filename: str, stream: BinaryIO, *, max_bytes: int, allow_xlsm: bool
) -> tuple[str, bytes]:
    cleaned = safe_filename(filename)
    suffix = Path(cleaned).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES or (suffix == ".xlsm" and not allow_xlsm):
        raise DomainError(
            "UNSUPPORTED_FILE_TYPE", "Only .xlsx files are accepted by current policy."
        )
    payload = stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise DomainError(
            "UPLOAD_TOO_LARGE", "The workbook exceeds the configured upload limit.", 413
        )
    if not payload.startswith(b"PK\x03\x04"):
        raise DomainError("INVALID_WORKBOOK", "The uploaded file is not an OOXML workbook.")
    return cleaned, payload


def save_workbook(payload: bytes, filename: str, upload_dir: Path) -> tuple[str, Path, str]:
    source_id = str(uuid.uuid4())
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".xlsx"
    target_path = (upload_dir / f"{source_id}{suffix}").resolve()
    resolved_dir = upload_dir.resolve()
    if not target_path.is_relative_to(resolved_dir):
        raise DomainError("PATH_TRAVERSAL_DETECTED", "Unsafe storage destination.")
    target_path.write_bytes(payload)
    return source_id, target_path, hashlib.sha256(payload).hexdigest()


def _type_name(value: object) -> str:
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (datetime, date)):
        return "date"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def inspect_workbook(path: Path) -> list[SheetSchema]:
    try:
        workbook = load_workbook(
            path, read_only=True, data_only=False, keep_vba=path.suffix == ".xlsm"
        )
    except Exception as exc:
        raise DomainError("UNREADABLE_WORKBOOK", "The workbook could not be read.") from exc
    schemas: list[SheetSchema] = []
    for ws in workbook.worksheets:
        rows = ws.iter_rows(values_only=True)
        first = next(rows, None)
        issues: list[ValidationIssue] = []
        if first is None or not any(value not in (None, "") for value in first):
            issues.append(
                ValidationIssue(
                    code="EMPTY_WORKSHEET",
                    severity=IssueSeverity.WARNING,
                    message="Worksheet has no detectable header.",
                    sheet=ws.title,
                )
            )
            schemas.append(
                SheetSchema(
                    name=ws.title,
                    max_row=ws.max_row or 0,
                    max_column=ws.max_column or 0,
                    issues=issues,
                )
            )
            continue
        headers = [
            str(value).strip() if value not in (None, "") else f"__blank_{index + 1}"
            for index, value in enumerate(first)
        ]
        duplicates = [header for header, count in Counter(headers).items() if count > 1]
        for header in duplicates:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_COLUMN",
                    severity=IssueSeverity.WARNING,
                    message="Duplicate column name requires mapping review.",
                    sheet=ws.title,
                    field=header,
                )
            )
        for header in [item for item in headers if item.startswith("__blank_")]:
            issues.append(
                ValidationIssue(
                    code="MISSING_HEADER",
                    severity=IssueSeverity.WARNING,
                    message="Blank header is preserved with a synthetic label.",
                    sheet=ws.title,
                    field=header,
                )
            )
        samples: dict[str, set[str]] = {header: set() for header in headers}
        for row_index, row in enumerate(rows, start=2):
            if row_index > 202:
                break
            for index, value in enumerate(row[: len(headers)]):
                samples[headers[index]].add(_type_name(value))
        inferred = {
            header: next(iter(values)) if len(values) == 1 else "mixed"
            for header, values in samples.items()
        }
        schemas.append(
            SheetSchema(
                name=ws.title,
                max_row=ws.max_row or 0,
                max_column=ws.max_column or 0,
                headers=headers,
                inferred_types=inferred,
                issues=issues,
            )
        )
    workbook.close()
    return schemas
