"""End-to-End Migration Audit and Openpyxl Verification Suite.

Validates the complete migration lifecycle against synthetic fixtures,
reopens and inspects generated workbooks with openpyxl at the cell level,
and verifies defensive edge cases and failure semantics.
"""

import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
import pytest
from openpyxl.utils.exceptions import InvalidFileException

from app.services.equus import (
    STRATEGY_EMPLOYEE_NUMBER,
    run_equus_migration_pipeline,
)
from app.services.equus.parser import parse_three_row_workbook

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAMBDA_SRC = PROJECT_ROOT / "lambda" / "src"
if str(LAMBDA_SRC) not in sys.path:
    sys.path.insert(0, str(LAMBDA_SRC))

import handler  # noqa: E402

FIXTURES_DIR = PROJECT_ROOT / "topia_equus_test_workbooks"
BASIC_FIXTURE = FIXTURES_DIR / "01_valid_basic.xlsx"
NUMERIC_FIXTURE = FIXTURES_DIR / "02_valid_numeric_ids.xlsx"
BLANKS_FIXTURE = FIXTURES_DIR / "03_valid_blank_optional_fields.xlsx"
MANY_ROWS_FIXTURE = FIXTURES_DIR / "05_valid_many_rows.xlsx"


def test_e2e_valid_workflow_openpyxl_deep_inspection(tmp_path: Path):
    """Deep cell-level openpyxl inspection of generated Equus import and report workbooks."""
    res = run_equus_migration_pipeline(
        source_path=BASIC_FIXTURE,
        output_dir=tmp_path,
        strategy=STRATEGY_EMPLOYEE_NUMBER,
        overwrite=True,
    )

    import_path = Path(res["import_file"])
    report_path = Path(res["report_file"])

    assert import_path.exists(), f"Import workbook missing: {import_path}"
    assert report_path.exists(), f"Report workbook missing: {report_path}"

    # =========================================================================
    # 1. Inspect Equus Import Workbook at Cell Level
    # =========================================================================
    wb_import = openpyxl.load_workbook(import_path, data_only=True)
    assert "Sheet1" in wb_import.sheetnames
    ws_import = wb_import["Sheet1"]

    # Verify column count and template headers
    assert ws_import.max_column == 146
    assert ws_import.max_row >= 4

    # Row 1: Rule header instruction text
    r1_col1 = ws_import.cell(row=1, column=1).value
    assert r1_col1 and "Instructions" in str(r1_col1)

    # Row 2: UI label / tech name
    r2_col1 = ws_import.cell(row=2, column=1).value
    assert r2_col1 and "Field Name" in str(r2_col1)

    # Row 3: Technical Import Header keys
    assert ws_import.cell(row=3, column=1).value == "A"
    assert ws_import.cell(row=3, column=2).value == "Assignment Command"
    assert ws_import.cell(row=3, column=3).value == "Employee Number"
    assert ws_import.cell(row=3, column=5).value == "Assignment Identifier"

    # Row 4+: Data Records Inspection
    # Row 4 must be the primary assignment INSERT row
    row4_col1 = ws_import.cell(row=4, column=1).value
    row4_col2 = ws_import.cell(row=4, column=2).value
    row4_emp_num = ws_import.cell(row=4, column=3).value
    row4_assign_id = ws_import.cell(row=4, column=5).value

    assert row4_col1 == "INSERT"
    assert row4_col2 == "INSERT"
    assert row4_emp_num is not None
    assert row4_assign_id is not None

    # Inspect date and country format on row 4 if populated
    for col_idx in range(1, 147):
        header_key = ws_import.cell(row=3, column=col_idx).value or ""
        cell_val = ws_import.cell(row=4, column=col_idx).value
        if cell_val is None:
            continue
        # Verify date fields follow YYYY-MM-DD
        rule_val = ws_import.cell(row=1, column=col_idx).value or ""
        if "US Date Format" in str(rule_val) or str(header_key).endswith("_DATE"):
            assert len(str(cell_val)) == 10
            # Accept either US Date Format (MM/DD/YYYY) or ISO format (YYYY-MM-DD)
            assert (str(cell_val)[2] == "/" and str(cell_val)[5] == "/") or (
                str(cell_val)[4] == "-" and str(cell_val)[7] == "-"
            )
        # Verify country fields are ISO-3 alpha (3 letters)
        if "Match Country Code" in str(rule_val) or (
            "COUNTRY" in str(header_key).upper() and "CODE" in str(header_key).upper()
        ):
            assert len(str(cell_val)) == 3
            assert str(cell_val).isupper()

    # Check child UPDATE rows if present
    if ws_import.max_row > 4:
        for r_idx in range(5, ws_import.max_row + 1):
            cmd = ws_import.cell(row=r_idx, column=2).value
            if cmd == "UPDATE":
                # Col 1 must be IGNORE
                assert ws_import.cell(row=r_idx, column=1).value == "IGNORE"
                # Col 3 (Employee Number) must be strictly blank on UPDATE rows
                assert ws_import.cell(row=r_idx, column=3).value is None
                # Col 5 (Assignment Identifier) must be populated referencing parent
                parent_id = ws_import.cell(row=r_idx, column=5).value
                assert parent_id is not None
                assert str(parent_id) == str(row4_assign_id)

    wb_import.close()

    # =========================================================================
    # 2. Inspect Mapping Results Report at Cell Level
    # =========================================================================
    wb_report = openpyxl.load_workbook(report_path, data_only=True)
    expected_tabs = [
        "Executive Summary",
        "Column Mappings",
        "Translations Applied",
        "Warnings & Issues",
    ]
    assert wb_report.sheetnames == expected_tabs

    # Tab 1: Executive Summary verification
    ws_summary = wb_report["Executive Summary"]
    summary_text = [
        str(ws_summary.cell(row=r, column=1).value)
        for r in range(1, ws_summary.max_row + 1)
        if ws_summary.cell(row=r, column=1).value is not None
    ]
    summary_blob = " ".join(summary_text)
    assert "Equus Migration & Reconciliation Summary" in summary_blob
    assert "Field Coverage" in summary_blob

    # Tab 2: Column Mappings verification
    ws_mappings = wb_report["Column Mappings"]
    assert ws_mappings.max_row >= 2
    assert ws_mappings.cell(row=1, column=1).value == "Equus Col #"

    # Tab 3: Translations Applied verification
    ws_translations = wb_report["Translations Applied"]
    assert ws_translations.cell(row=1, column=1).value == "Source Row #"

    # Tab 4: Warnings & Issues verification
    ws_warnings = wb_report["Warnings & Issues"]
    assert ws_warnings.cell(row=1, column=1).value == "Code"

    wb_report.close()


def test_e2e_multiple_employees_and_assignments(tmp_path: Path):
    """Verify that multiple employees and assignments generate distinct keys without collision."""
    res = run_equus_migration_pipeline(
        source_path=MANY_ROWS_FIXTURE,
        output_dir=tmp_path,
        strategy=STRATEGY_EMPLOYEE_NUMBER,
        overwrite=True,
    )

    wb = openpyxl.load_workbook(Path(res["import_file"]), data_only=True)
    ws = wb.active

    # Collect all INSERT rows
    insert_rows = []
    for r in range(4, ws.max_row + 1):
        if ws.cell(row=r, column=2).value == "INSERT":
            emp_num = str(ws.cell(row=r, column=3).value)
            assign_id = str(ws.cell(row=r, column=5).value)
            insert_rows.append((emp_num, assign_id))

    wb.close()

    assert len(insert_rows) >= 2
    # Verify all generated assignment identifiers on INSERT rows are unique
    all_assign_ids = [assign_id for _, assign_id in insert_rows]
    assert len(all_assign_ids) == len(set(all_assign_ids)), (
        "Assignment identifiers must not collide"
    )


def test_e2e_missing_optional_fields_remain_clean_blanks(tmp_path: Path):
    """Verify missing optional source values become clean None cells, not 'null'."""
    res = run_equus_migration_pipeline(
        source_path=BLANKS_FIXTURE,
        output_dir=tmp_path,
        overwrite=True,
    )

    wb = openpyxl.load_workbook(Path(res["import_file"]), data_only=True)
    ws = wb.active

    for r in range(4, ws.max_row + 1):
        for c in range(1, 147):
            val = ws.cell(row=r, column=c).value
            if val is not None:
                assert str(val).lower() != "not provided"
                assert str(val).lower() != "null"
                assert str(val).lower() != "undefined"

    wb.close()


def test_e2e_corrupt_and_invalid_workbooks(tmp_path: Path):
    """Verify defensive handling when provided with corrupt or non-XLSX files."""
    # 1. Non-existent file
    with pytest.raises(FileNotFoundError):
        parse_three_row_workbook(tmp_path / "does_not_exist.xlsx")

    # 2. Corrupt file content
    corrupt_file = tmp_path / "corrupt.xlsx"
    corrupt_file.write_bytes(b"This is completely corrupt non-zip text data")
    with pytest.raises((InvalidFileException, zipfile.BadZipFile)):
        parse_three_row_workbook(corrupt_file)


def test_e2e_lambda_missing_source_object_fails(tmp_path: Path, monkeypatch):
    """Verify that if S3 get_object fails (404), Lambda handler propagates error to SQS DLQ."""
    mock_s3 = MagicMock()
    mock_s3.get_object.side_effect = Exception("NoSuchKey: The specified key does not exist.")
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)
    monkeypatch.setenv("DEST_BUCKET", "test-bucket")

    event = {
        "source_bucket": "test-source-bucket",
        "source_key": "topia/incoming/nonexistent.xlsx",
    }

    with pytest.raises(Exception, match="NoSuchKey"):
        handler.lambda_handler(event)


def test_e2e_lambda_partial_upload_failure_does_not_claim_success(tmp_path: Path, monkeypatch):
    """Verify that if report upload fails after import succeeds, invocation raises and fails."""
    sample_bytes = BASIC_FIXTURE.read_bytes()
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_bytes)}

    # First put_object (import file) succeeds; second put_object (report file) raises exception
    mock_s3.put_object.side_effect = [
        {"ETag": "fake-etag"},
        RuntimeError("Network timeout uploading mapping report"),
    ]
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)
    monkeypatch.setenv("DEST_BUCKET", "test-bucket")

    event = {
        "source_bucket": "test-source-bucket",
        "source_key": "topia/incoming/01_valid_basic.xlsx",
    }

    # Must raise exception rather than returning success
    with pytest.raises(RuntimeError, match="Network timeout uploading mapping report"):
        handler.lambda_handler(event)
