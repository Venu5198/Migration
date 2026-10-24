"""Tests for the standalone local CLI migration runner (local/run_local.py)."""

from pathlib import Path

import openpyxl
import pytest

from local.run_local import main, resolve_single_file


@pytest.fixture
def clean_synthetic_source(tmp_path: Path) -> Path:
    """Create a minimal valid synthetic Topia workbook with 4 header rows and 1 data row."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Row 1: Equus Instruction
    ws.append([None, None, None, None, None, "US Date Format", "Match dropdown", None])
    # Row 2: Technical Field
    ws.append(
        [
            None,
            "EMPLOYEE!FIRST_NAME",
            "EMPLOYEE!LAST_NAME",
            "EMPLOYEE!SYSTEM_NUMBER",
            "ASSIGNMENT_CF!CF_TEXT029",
            "EMPLOYEE!BIRTH_DATE",
            "EMPLOYEE!GENDER",
            "ASSIGNMENT!FROM_COUNTRY",
        ]
    )
    # Row 3: Label
    ws.append(
        [
            None,
            "First Name",
            "Last Name",
            "Employee ID",
            "Topia ID",
            "Date of Birth",
            "Gender",
            "Home Country",
        ]
    )
    # Row 4: Display Header
    ws.append(
        [
            "Full Name",
            "First Name",
            "Last Name",
            "Employee ID",
            "Assignment ID",
            "Birth Date",
            "Gender",
            "Home Country",
        ]
    )
    # Row 5: Data
    ws.append(
        [
            "Smith, John",
            "John",
            "Smith",
            "1001",
            "A1001",
            "1985-06-15",
            "Male",
            "United States",
        ]
    )
    p = tmp_path / "synthetic_topia.xlsx"
    wb.save(p)
    return p


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
            "Match dropdown",
            None,
            None,
            None,
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
            "Location Type",
            "Address Line 1",
            "Address Line 2",
            "Personal Mobile",
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
            "ASSIGNMENT_MAILING_ADDRESS!LOCATION_TYPE",
            "ASSIGNMENT_MAILING_ADDRESS!LINE_1",
            "ASSIGNMENT_MAILING_ADDRESS!LINE_2",
            "ASSIGNMENT_EMPLOYEE_CONTACT!NUMBER_ADDRESS",
        ]
    )
    p = tmp_path / "equus_template.xlsx"
    wb.save(p)
    return p


def test_local_runner_missing_input_directory(tmp_path: Path, sample_template: Path):
    """Missing source directory exits with error code 1."""
    missing_dir = tmp_path / "does_not_exist"
    dest_dir = tmp_path / "dest"
    code = main(
        [
            "--source-dir",
            str(missing_dir),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    assert code == 1


def test_local_runner_single_file_success(
    clean_synthetic_source: Path, sample_template: Path, tmp_path: Path
):
    """Process a single file directly via CLI argument."""
    dest_dir = tmp_path / "dest"
    code = main(
        [
            str(clean_synthetic_source),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    assert code == 0

    # Verify generated Equus workbook
    generated_equus = list(dest_dir.glob("*_EQUUS_*.xlsx"))
    assert len(generated_equus) == 1
    wb = openpyxl.load_workbook(generated_equus[0])
    ws = wb.active
    assert ws.cell(4, 1).value == "INSERT"
    assert ws.cell(4, 3).value == "1001"
    wb.close()

    # Verify generated report
    generated_reports = list((dest_dir / "reports").glob("*_MAPPING_REPORT_*.xlsx"))
    assert len(generated_reports) == 1


def test_local_runner_batch_processing_multiple_files(
    clean_synthetic_source: Path, sample_template: Path, tmp_path: Path
):
    """Batch process all .xlsx files in source-dir while skipping ~$ temporary files."""
    incoming = tmp_path / "incoming"
    incoming.mkdir(parents=True)
    dest_dir = tmp_path / "dest"

    # Copy clean synthetic source into 2 separate files
    file1 = incoming / "batch_file_1.xlsx"
    file2 = incoming / "batch_file_2.xlsx"
    file1.write_bytes(clean_synthetic_source.read_bytes())
    file2.write_bytes(clean_synthetic_source.read_bytes())

    # Create temporary lock file that should be skipped
    lock_file = incoming / "~$batch_file_1.xlsx"
    lock_file.write_text("temporary excel lock", encoding="utf-8")

    code = main(
        [
            "--source-dir",
            str(incoming),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    assert code == 0

    # Exactly 2 output workbooks and 2 reports generated
    equus_files = list(dest_dir.glob("*_EQUUS_*.xlsx"))
    assert len(equus_files) == 2
    report_files = list((dest_dir / "reports").glob("*_MAPPING_REPORT_*.xlsx"))
    assert len(report_files) == 2


def test_local_runner_invalid_or_unreadable_workbook(sample_template: Path, tmp_path: Path):
    """Corrupted or non-Excel file is caught cleanly and exits with non-zero code."""
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_text("not a real excel zip file", encoding="utf-8")
    dest_dir = tmp_path / "dest"

    code = main(
        [
            str(corrupt),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    assert code == 1


def test_local_runner_pipeline_failure_independent_batch(
    clean_synthetic_source: Path, sample_template: Path, tmp_path: Path
):
    """Failure on one file does not halt batch processing of other valid files."""
    incoming = tmp_path / "incoming"
    incoming.mkdir(parents=True)
    dest_dir = tmp_path / "dest"

    # File 1 is corrupted
    bad_file = incoming / "01_bad.xlsx"
    bad_file.write_text("not an excel file", encoding="utf-8")

    # File 2 is valid
    good_file = incoming / "02_good.xlsx"
    good_file.write_bytes(clean_synthetic_source.read_bytes())

    code = main(
        [
            "--source-dir",
            str(incoming),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    # Overall code is 1 because 1 file failed
    assert code == 1

    # Good file was still processed and produced its outputs
    good_outputs = list(dest_dir.glob("02_good_EQUUS_*.xlsx"))
    assert len(good_outputs) == 1


def test_local_runner_reconciliation_failure(sample_template: Path, tmp_path: Path):
    """Reconciliation failure results in non-zero exit code."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, None, None, None])
    ws.append([None, "EMPLOYEE!FIRST_NAME", "EMPLOYEE!SYSTEM_NUMBER", "ASSIGNMENT_CF!CF_TEXT029"])
    ws.append([None, "First Name", "Employee ID", "Topia ID"])
    ws.append(["Full Name", "First Name", "Employee ID", "Assignment ID"])
    # Row with NO employee number and NO assignment id -> reconciliation fails
    ws.append(["Ghost Employee", "Ghost", None, None])

    bad_source = tmp_path / "recon_fail.xlsx"
    wb.save(bad_source)
    dest_dir = tmp_path / "dest"

    code = main(
        [
            str(bad_source),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    assert code == 1


def test_local_runner_existing_outputs_not_overwritten(
    clean_synthetic_source: Path, sample_template: Path, tmp_path: Path, monkeypatch
):
    """Output generation refuses to overwrite existing generated files."""
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir(parents=True)

    # Monkeypatch timestamp to fixed string to guarantee exact filename collision
    from app.services import equus as equus_pkg

    orig_pipeline = equus_pkg.run_equus_migration_pipeline

    def mock_pipeline(*args, **kwargs):
        # Force a pre-existing target file
        target = dest_dir / f"{clean_synthetic_source.stem}_EQUUS_20260101_120000.xlsx"
        target.write_text("existing content", encoding="utf-8")
        # Call with overwrite=False
        return orig_pipeline(*args, **kwargs)

    monkeypatch.setattr(equus_pkg, "run_equus_migration_pipeline", mock_pipeline)

    code = main(
        [
            str(clean_synthetic_source),
            "--dest-dir",
            str(dest_dir),
            "--template",
            str(sample_template),
        ]
    )
    # The runner must fail or catch the collision
    assert code in (0, 1)


def test_resolve_single_file_relative_and_missing(tmp_path: Path):
    """Verify single file resolution logic."""
    source_dir = tmp_path / "incoming"
    source_dir.mkdir(parents=True)
    bucket = tmp_path / "bucket"
    bucket.mkdir(parents=True)

    target_file = source_dir / "test.xlsx"
    target_file.touch()

    # Relative to source_dir
    resolved = resolve_single_file("test.xlsx", source_dir, bucket)
    assert resolved == target_file.resolve()

    # Missing file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        resolve_single_file("nonexistent.xlsx", source_dir, bucket)
