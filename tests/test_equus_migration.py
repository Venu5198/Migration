"""Tests for the Topia to Equus Migration Engine."""

from pathlib import Path

import openpyxl
import pytest

from app.repositories import MemoryRepository
from app.schemas import JobStatus
from app.services.equus import (
    parse_three_row_workbook,
    reconcile_equus_transformation,
    run_equus_migration_pipeline,
    transform_topia_to_equus,
)
from app.services.equus.mapping_config import (
    clean_not_provided,
    convert_country_to_iso3,
    convert_dropdown,
    convert_us_date,
)
from app.workers.worker import process_once


@pytest.fixture
def sample_template(tmp_path: Path) -> Path:
    """Create a minimal 3-row Equus template for fast unit testing."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # Row 1: Instructions
    ws.append(
        [
            "Instructions --->>>",
            None,
            None,
            None,
            None,
            "Match dropdown",
            "US Date Format",
            "Match Country Code",
        ]
    )
    # Row 2: Field Name / Label
    ws.append(
        [
            "Field Name --->>>",
            None,
            "Talent Link Id",
            None,
            "Topia Id",
            "Gender",
            "Birth Date",
            "Home Country",
        ]
    )
    # Row 3: Technical Header
    ws.append(
        [
            "A",
            "Assignment Command",
            "Employee Number",
            "Assignment Number",
            "Assignment Identifier",
            "EMPLOYEE!GENDER",
            "EMPLOYEE!BIRTH_DATE",
            "ASSIGNMENT!FROM_COUNTRY",
        ]
    )
    # Sample row 4
    ws.append(["INSERT", "INSERT", "E001", "NEW", "T001", "Male", "01/01/1980", "USA"])
    p = tmp_path / "test_template.xlsx"
    wb.save(p)
    return p


@pytest.fixture
def synthetic_source(tmp_path: Path) -> Path:
    """Create a synthetic Topia 4-row header source workbook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # Row 1: Rules
    ws.append(
        [
            None,
            None,
            None,
            None,
            None,
            "Match dropdown",
            "US Date Format",
            "Match Country Code",
            None,
            None,
        ]
    )
    # Row 2: Technical Field
    ws.append(
        [
            None,
            None,
            "EMPLOYEE!SYSTEM_NUMBER",
            None,
            "ASSIGNMENT_CF!CF_TEXT029",
            "EMPLOYEE!GENDER",
            "EMPLOYEE!BIRTH_DATE",
            "ASSIGNMENT!FROM_COUNTRY",
            "ASSIGNMENT_MAILING_ADDRESS!LOCATION_TYPE",
            "ASSIGNMENT_EMPLOYEE_CONTACT!NUMBER_ADDRESS",
        ]
    )
    # Row 3: Label
    ws.append(
        [
            None,
            None,
            "Talent Link ID",
            None,
            "Topia ID",
            "Gender",
            "Date of Birth",
            "Home Country",
            "Host Residence Address",
            "Personal Phone",
        ]
    )
    # Row 4: Display Header
    ws.append(
        [
            "Full Name",
            "First Name",
            "Employee ID",
            None,
            "Assignment ID",
            "Gender",
            "Birth Date",
            "Home Country",
            "Host Address",
            "Phone Number",
        ]
    )
    # Row 5: Data 1 (Clean)
    ws.append(
        [
            "Smith, John",
            "John",
            "1001",
            None,
            "A1001",
            "Male",
            "1985-06-15",
            "United States",
            "Host Address Line",
            "555-0100",
        ]
    )
    # Row 6: Data 2 (With 'Not Provided' and ISO-3)
    ws.append(
        [
            "Doe, Jane",
            "Jane",
            "1002",
            None,
            "A1002",
            "Female",
            "07/20/1990",
            "India",
            "Not Provided",
            None,
        ]
    )
    p = tmp_path / "test_source.xlsx"
    wb.save(p)
    return p


def test_clean_not_provided():
    assert clean_not_provided("Not Provided") is None
    assert clean_not_provided("N/A") is None
    assert clean_not_provided("na") is None
    assert clean_not_provided("-") is None
    assert clean_not_provided("") is None
    assert clean_not_provided("Valid Value") == "Valid Value"


def test_date_conversion():
    d1, err1 = convert_us_date("1985-06-15")
    assert err1 is None
    assert d1 == "06/15/1985"

    d2, err2 = convert_us_date("15/06/1985")
    assert err2 is None
    assert d2 == "06/15/1985"

    d3, err3 = convert_us_date("invalid_date")
    assert d3 is None
    assert "could not be parsed" in err3


def test_country_to_iso3():
    c1, err1 = convert_country_to_iso3("India")
    assert err1 is None
    assert c1 == "IND"

    c2, err2 = convert_country_to_iso3("United States")
    assert err2 is None
    assert c2 == "USA"

    c3, err3 = convert_country_to_iso3("JP")
    assert err3 is None
    assert c3 == "JPN"

    c4, err4 = convert_country_to_iso3("Atlantis")
    assert c4 is None
    assert "UNKNOWN_COUNTRY_CODE" in err4


def test_dropdown_conversion():
    v1, err1 = convert_dropdown("EMPLOYMENT_STATUS", "Employed")
    assert err1 is None
    assert v1 == "Active"

    v2, err2 = convert_dropdown("GENDER", "female")
    assert err2 is None
    assert v2 == "Female"

    v3, err3 = convert_dropdown("YES_NO", "true")
    assert err3 is None
    assert v3 == "Yes"

    v4, err4 = convert_dropdown("GENDER", "Alien")
    assert v4 is None
    assert "UNKNOWN_DROPDOWN_VALUE" in err4


def test_parse_three_row_workbook(synthetic_source: Path):
    parsed = parse_three_row_workbook(synthetic_source)
    assert parsed.header_rows_count == 4
    assert len(parsed.data_rows) == 2
    assert parsed.total_rows_evaluated == 2
    assert len(parsed.columns) == 10


def test_transform_topia_to_equus(synthetic_source: Path, sample_template: Path):
    parsed_src = parse_three_row_workbook(synthetic_source)
    res = transform_topia_to_equus(parsed_src, sample_template)

    assert res.total_evaluated_rows == 2
    assert len(res.insert_records) == 2
    # Row 1 has a host address and phone, producing UPDATE records
    assert len(res.update_records) >= 1
    assert len(res.all_output_records) == len(res.insert_records) + len(res.update_records)

    # Check first INSERT row
    r1 = res.insert_records[0]
    assert r1[1] == "INSERT"
    assert r1[2] == "INSERT"
    assert r1[3] == "1001"
    assert r1[4] == "NEW"
    assert r1[5] == "A1001"
    assert r1[6] == "Male"
    assert r1[7] == "06/15/1985"
    assert r1[8] == "USA"


def test_reconciliation_detects_duplicates(synthetic_source: Path, sample_template: Path):
    parsed_src = parse_three_row_workbook(synthetic_source)
    res = transform_topia_to_equus(parsed_src, sample_template)

    # Inject duplicate assignment ID
    res.insert_records[1][5] = res.insert_records[0][5]
    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is False
    assert recon["status"] == "FAILED"
    assert any("Duplicate Assignment Identifier" in err for err in recon["errors"])


def test_full_pipeline_artifacts_and_report(
    synthetic_source: Path, sample_template: Path, tmp_path: Path
):
    out_dir = tmp_path / "artifacts"
    res = run_equus_migration_pipeline(
        source_path=synthetic_source,
        template_path=sample_template,
        output_dir=out_dir,
        source_name="smoke_test",
    )
    assert res["status"] in ("VERIFIED_PASS", "COMPLETED_WITH_WARNINGS")
    assert Path(res["import_file"]).exists()
    assert Path(res["report_file"]).exists()

    # Verify generated Equus import file
    wb_import = openpyxl.load_workbook(res["import_file"])
    ws_import = wb_import.active
    assert ws_import.cell(4, 1).value == "INSERT"
    assert ws_import.cell(4, 3).value == "1001"
    wb_import.close()

    # Verify generated multi-tab report
    wb_report = openpyxl.load_workbook(res["report_file"])
    assert "Executive Summary" in wb_report.sheetnames
    assert "Column Mappings" in wb_report.sheetnames
    assert "Translations Applied" in wb_report.sheetnames
    assert "Warnings & Issues" in wb_report.sheetnames
    wb_report.close()


@pytest.mark.asyncio
async def test_worker_processes_equus_migration_job(synthetic_source: Path, tmp_path: Path):
    repo = MemoryRepository()
    source_id = "src-equus-1"
    await repo.put_source(
        {
            "source_id": source_id,
            "original_filename": "synthetic_source.xlsx",
            "storage_path": str(synthetic_source),
            "sha256": "test-sha",
            "sheets": [],
        }
    )

    from datetime import UTC, datetime

    job_id = "job-equus-1"
    now = datetime.now(UTC)
    await repo.put_job(
        {
            "job_id": job_id,
            "kind": "equus_migration",
            "source_id": source_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "cancellation_requested": False,
        }
    )

    processed = await process_once(repo, "test-worker")
    assert processed is True

    finished_job = await repo.get_job(job_id)
    assert finished_job["status"] in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS)
    assert "import_file" in finished_job["result"]
    assert "report_file" in finished_job["result"]
    assert finished_job["result"]["insert_records"] == 2
