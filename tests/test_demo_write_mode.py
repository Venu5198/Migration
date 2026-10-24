"""Automated test suite for isolated demo-write mode and destination verification.

Verifies:
1. Mock-target write isolation and fail-closed security.
2. Prevention of production Equus target access.
3. Demonstration of INSERT (new synthetic record).
4. Demonstration of UPDATE (updating existing synthetic record).
5. Multiple assignments without conflicting identifiers.
6. Dependent linkage: rejection of orphans, flagging of ambiguous dependents.
7. Retry, idempotency, and duplicate handling on repeat runs.
8. Partial failures and discrepancy reporting.
9. Destination read-back verification.
10. Deliverable workbooks structure and representative cell values.
"""

from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.equus import (
    MockEquusDestination,
    run_equus_migration_pipeline,
)
from tests.test_client_decisions_regression import _create_synthetic_source_file


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_dest():
    dest = MockEquusDestination()
    dest.reset()
    return dest


# ==============================================================================
# 1. MOCK-TARGET WRITE ISOLATION & FAIL-CLOSED SECURITY
# ==============================================================================


def test_production_target_access_strictly_prevented():
    """Live Equus target writes must fail closed with PermissionError."""
    # Attempting to configure target 'live' while equus_writes_disabled=True
    with pytest.raises(PermissionError) as exc_info:
        settings.validate_equus_destination(target="live", demo_writes=False)
    assert "strictly disabled by policy" in str(exc_info.value)


def test_demo_writes_fail_closed_if_target_not_mock():
    """Demo writes must fail closed if target is not explicitly 'mock'."""
    with pytest.raises(ValueError) as exc_info:
        settings.validate_equus_destination(target="production_db", demo_writes=True)
    assert "Demo writes can ONLY execute against isolated target 'mock'" in str(exc_info.value)


def test_api_rejects_live_target_writes(client: TestClient):
    """API endpoint returns 403 when live target write is requested."""
    res = client.post(
        "/api/v1/sources/dummy-source-id/equus-migration",
        json={"strategy": "EMPLOYEE_NUMBER", "target": "live", "demo_writes_enabled": True},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "LIVE_WRITES_DISABLED"


def test_api_rejects_invalid_demo_target(client: TestClient):
    """API endpoint returns 422 when demo write target is invalid."""
    res = client.post(
        "/api/v1/sources/dummy-source-id/equus-migration",
        json={
            "strategy": "EMPLOYEE_NUMBER",
            "target": "untrusted_host",
            "demo_writes_enabled": True,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INVALID_DEMO_TARGET"


# ==============================================================================
# 2. DEMONSTRATION OF INSERT (NEW RECORD)
# ==============================================================================


def test_demonstrate_insert_new_employee_and_assignment(
    tmp_path: Path, mock_dest: MockEquusDestination
):
    """Demonstrate clean INSERT of a new synthetic employee and assignment."""
    src_path = tmp_path / "insert_demo.xlsx"
    rows = [
        [
            "SYNTH_EMP_101",
            "Initiated",
            "T-101",
            "Female",
            "1988-04-12",
            "United States",
            "United Kingdom",
            "10 London Way, London",
            None,
            "555-0101",
            "synth101@corp.test",
            None,
            None,
            None,
            None,
            None,
        ]
    ]
    _create_synthetic_source_file(src_path, rows)

    res = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )

    exec_summary = res["execution_summary"]
    assert exec_summary["demo_writes_enabled"] is True
    assert exec_summary["target"] == "mock-equus-local"
    assert exec_summary["attempted"] >= 1
    assert exec_summary["successful"] >= 1
    assert exec_summary["inserted"] >= 2  # 1 employee + 1 assignment

    # Read back from mock destination to verify actual persistence
    emp = mock_dest.read_back_employee("SYNTH_EMP_101")
    assert emp is not None
    assert emp["employee_number"] == "SYNTH_EMP_101"

    asg = mock_dest.read_back_assignment("SYNTH_EMP_101")
    assert asg is not None
    assert asg["employee_number"] == "SYNTH_EMP_101"
    assert len(asg["contacts"]) >= 1
    assert exec_summary["verification_status"] == "VERIFIED_MATCH"


# ==============================================================================
# 3. DEMONSTRATION OF UPDATE (MODIFYING PRE-EXISTING RECORD)
# ==============================================================================


def test_demonstrate_update_existing_record(tmp_path: Path, mock_dest: MockEquusDestination):
    """Demonstrate UPDATE modifying fields on an existing synthetic record."""
    # Pre-seed destination with baseline record
    mock_dest.reset(
        seed_data={
            "employees": [
                {
                    "employee_number": "EMP_UPD_001",
                    "gender": "Male",
                    "birth_date": "1980-01-01",
                    "status": "Old Baseline",
                }
            ],
            "assignments": [
                {
                    "assignment_identifier": "EMP_UPD_001",
                    "employee_number": "EMP_UPD_001",
                    "phase": "Draft",
                }
            ],
            "contacts": [
                {
                    "assignment_identifier": "EMP_UPD_001",
                    "location_type": "Personal Mobile",
                    "number_address": "999-OLD-NUM",
                }
            ],
        }
    )

    src_path = tmp_path / "update_demo.xlsx"
    rows = [
        [
            "EMP_UPD_001",
            "Initiated",  # Updated status
            "T-UPD-001",
            "Male",
            "1980-01-01",
            "United States",
            "Canada",
            None,
            None,
            "123-NEW-NUM",  # Updated mobile number
            "emp001@updated.test",
            None,
            None,
            None,
            None,
            None,
        ]
    ]
    _create_synthetic_source_file(src_path, rows)

    res = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )

    exec_summary = res["execution_summary"]
    assert exec_summary["successful"] >= 1

    # Read back from destination and verify updated values
    asg = mock_dest.read_back_assignment("EMP_UPD_001")
    assert asg is not None
    # Verify contact was updated with new number
    matching_contact = next(
        (c for c in asg["contacts"] if c.get("location_type") == "Personal Mobile"), None
    )
    assert matching_contact is not None
    assert matching_contact["number_address"] == "123-NEW-NUM"


# ==============================================================================
# 4. MULTIPLE ASSIGNMENTS WITHOUT CONFLICTING IDENTIFIERS
# ==============================================================================


def test_multiple_assignments_persist_cleanly_without_collision(
    tmp_path: Path, mock_dest: MockEquusDestination
):
    """Multiple assignments for same employee persist with distinct sequential identifiers."""
    src_path = tmp_path / "multi_asg_demo.xlsx"
    rows = [
        [
            "EMP_M200",
            "Initiated",
            "T-M1",
            "Male",
            "1985-05-15",
            "USA",
            "UK",
            None,
            None,
            "111",
            None,
            None,
            None,
            None,
            None,
            None,
        ],
        [
            "EMP_M200",
            "Initiated",
            "T-M2",
            "Male",
            "1985-05-15",
            "USA",
            "DEU",
            None,
            None,
            "222",
            None,
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    _create_synthetic_source_file(src_path, rows)

    res = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )

    assert res["reconciliation"]["is_valid"] is True
    # Verify both assignments exist in destination
    asg1 = mock_dest.read_back_assignment("EMP_M200")
    asg2 = mock_dest.read_back_assignment("EMP_M200-2")
    assert asg1 is not None
    assert asg2 is not None
    assert asg1["employee_number"] == "EMP_M200"
    assert asg2["employee_number"] == "EMP_M200"
    assert asg1["assignment_identifier"] != asg2["assignment_identifier"]


# ==============================================================================
# 5. DEPENDENT LINKAGE & REJECTION OF ORPHANS
# ==============================================================================


def test_orphan_dependents_rejected_from_destination(
    tmp_path: Path, mock_dest: MockEquusDestination
):
    """Orphan dependent referencing non-existent employee is rejected from destination."""
    src_path = tmp_path / "parent_exists.xlsx"
    rows = [
        [
            "EMP_VALID_300",
            "Initiated",
            "T-300",
            "Female",
            "1990-01-01",
            "USA",
            "FRA",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    _create_synthetic_source_file(src_path, rows)

    secondary_deps = [
        {
            "employee_id": "NON_EXISTENT_PARENT",
            "first_name": "Ghost",
            "last_name": "Dependent",
            "relationship": "Child",
        }
    ]

    res = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        dependent_records=secondary_deps,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )

    # Ghost dependent must NOT exist in destination
    assert len(mock_dest.dependents) == 0
    # Must be recorded in warnings
    assert any("NON_EXISTENT_PARENT" in w for w in res["reconciliation"]["warnings"])


# ==============================================================================
# 6. RETRY, IDEMPOTENCY, AND DUPLICATE HANDLING
# ==============================================================================


def test_migration_rerun_is_strictly_idempotent(tmp_path: Path, mock_dest: MockEquusDestination):
    """Rerunning identical migration marks records as skipped and creates no duplicates."""
    src_path = tmp_path / "idempotent_source.xlsx"
    rows = [
        [
            "EMP_IDEM_400",
            "Initiated",
            "T-400",
            "Male",
            "1982-08-20",
            "USA",
            "SGP",
            None,
            None,
            "555-400",
            "idem@test.com",
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    _create_synthetic_source_file(src_path, rows)

    # Run 1: Initial insertion
    res1 = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )
    snap1 = mock_dest.snapshot()
    assert snap1["counts"]["assignments"] == 1
    assert res1["execution_summary"]["inserted"] >= 1

    # Run 2: Exact rerun
    res2 = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )
    snap2 = mock_dest.snapshot()

    # Destination counts must remain exactly the same (no duplicates)
    assert snap2["counts"]["assignments"] == snap1["counts"]["assignments"]
    assert snap2["counts"]["employees"] == snap1["counts"]["employees"]
    # Run 2 marks assignment as skipped / idempotent
    assert res2["execution_summary"]["skipped"] >= 1
    assert res2["execution_summary"]["verification_status"] == "VERIFIED_MATCH"


# ==============================================================================
# 7. PARTIAL FAILURES AND DISCREPANCY DETECTION
# ==============================================================================


def test_partial_failure_detection_and_discrepancy_reporting(mock_dest: MockEquusDestination):
    """Unparented UPDATE records fail explicitly and report verification discrepancies."""
    records = [
        # Valid INSERT
        {1: "INSERT", 2: "INSERT", 3: "EMP_OK", 4: "NEW", 5: "ASG_OK"},
        # Malformed UPDATE referencing non-existent parent
        {1: "IGNORE", 2: "UPDATE", 3: None, 4: None, 5: "NON_EXISTENT_ASG_ID", 10: "Phone"},
    ]

    summary = mock_dest.execute_records(
        records,
        target="mock",
        demo_writes_enabled=True,
    )

    assert summary.successful == 1
    assert summary.failed == 1
    assert len(summary.errors) == 1
    assert "references non-existent assignment" in summary.errors[0]["error"]
    assert summary.verification_status == "DISCREPANCIES_FOUND"


# ==============================================================================
# 8. DELIVERABLE WORKBOOKS STRUCTURE & VALUES
# ==============================================================================


def test_mapping_report_reflects_destination_metrics(
    tmp_path: Path, mock_dest: MockEquusDestination
):
    """Migration Results includes execution-level demo metrics in Executive Summary and Tab 4."""
    src_path = tmp_path / "workbook_metrics_source.xlsx"
    rows = [
        [
            "EMP_DELIV_500",
            "Initiated",
            "T-500",
            "Female",
            "1991-03-22",
            "USA",
            "AUS",
            None,
            None,
            "555-500",
            None,
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    _create_synthetic_source_file(src_path, rows)

    res = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        target="mock",
        demo_writes_enabled=True,
        destination_instance=mock_dest,
        overwrite=True,
    )

    report_path = Path(res["report_file"])
    wb = openpyxl.load_workbook(report_path)

    # Verify Tab 1 (Executive Summary)
    ws_sum = wb["Executive Summary"]
    summary_text = [str(ws_sum.cell(r, 1).value) for r in range(1, ws_sum.max_row + 1)]
    assert any("Demo Target Destination" in t for t in summary_text)
    assert any("Records Inserted" in t for t in summary_text)
    assert any("Destination Read-Back Verification" in t for t in summary_text)

    # Verify Tab 4 (Warnings & Issues exists)
    assert "Warnings & Issues" in wb.sheetnames
    wb.close()


def test_safe_mode_preserves_planned_only_reporting(tmp_path: Path):
    """When demo writes are disabled, mapping report explicitly states PLANNED ONLY."""
    src_path = tmp_path / "safe_mode_source.xlsx"
    rows = [
        [
            "EMP_SAFE_600",
            "Initiated",
            "T-600",
            "Male",
            "1984-12-12",
            "USA",
            "JPN",
            None,
            None,
            "555-600",
            None,
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    _create_synthetic_source_file(src_path, rows)

    res = run_equus_migration_pipeline(
        src_path,
        output_dir=tmp_path,
        demo_writes_enabled=False,
        overwrite=True,
    )

    report_path = Path(res["report_file"])
    wb = openpyxl.load_workbook(report_path)
    ws_sum = wb["Executive Summary"]

    values_col2 = [str(ws_sum.cell(r, 2).value) for r in range(1, ws_sum.max_row + 1)]
    assert any("PLANNED ONLY" in v for v in values_col2)
    wb.close()
