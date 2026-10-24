"""Regression tests for approved client migration decisions.

Covers:
- One employee with multiple assignments (Option B sequential ID synthesis without key collisions).
- Multiple employees with distinct identifiers.
- Dependents linked to the correct parent (embedded & secondary records).
- Missing or ambiguous linkage (orphan, ambiguous multi-assignment, unkeyed).
- INSERT and UPDATE generation and reconciliation (EAFH row rules, Excel file verification).
- Append-only application logging audit verification.
"""

from pathlib import Path
from typing import Any

import openpyxl
import pytest

from app.services.equus import (
    DEFAULT_TEMPLATE_PATH,
    parse_three_row_workbook,
    reconcile_equus_transformation,
    run_equus_migration_pipeline,
    transform_topia_to_equus,
)
from app.services.equus.generator import generate_equus_import_file
from app.services.equus.mapping_config import (
    STRATEGY_EMPLOYEE_NUMBER,
    STRATEGY_TOPIA_ID_WITH_FALLBACK,
)
from app.services.equus.parser import ColumnMetadata, ParsedSheet
from app.services.equus.transformer import TransformationResult


def _create_synthetic_source_file(
    path: Path,
    rows: list[list[Any]],
    headers: list[tuple[str, str, str, str]] | None = None,
) -> Path:
    """Helper to generate a synthetic Topia 4-row header workbook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    if headers is None:
        # Default standard 4-row headers matching Topia format
        # (Row 1: Empty/Note, Row 2: Tech Field, Row 3: Field Name, Row 4: Display Label)
        headers = [
            ("", "EMPLOYEE!SYSTEM_NUMBER", "Talent Link Id", "Employee ID"),
            ("", "ASSIGNMENT!PHASE", "Status Category", "Status Category"),
            ("", "ASSIGNMENT_CF!CF_TEXT029", "Assignment Id", "Assignment Id"),
            ("", "EMPLOYEE!GENDER", "Gender", "Gender"),
            ("", "EMPLOYEE!BIRTH_DATE", "Birth Date", "Birth Date"),
            ("", "ASSIGNMENT!FROM_COUNTRY", "Home Country", "Home Country"),
            ("", "ASSIGNMENT!TO_COUNTRY", "Host Country", "Host Country"),
            (
                "",
                "ASSIGNMENT_MAILING_ADDRESS!LOCATION_TYPE",
                "Destination Residence",
                "Personal Host Address With Effective Date",
            ),
            (
                "",
                "ASSIGNMENT_MAILING_ADDRESS!LOCATION_TYPE",
                "Departure Residence",
                "Personal Home Address With Effective Date",
            ),
            (
                "",
                "ASSIGNMENT_EMPLOYEE_CONTACT!NUMBER_ADDRESS",
                "Personal Mobile",
                "Mobile Phone Number",
            ),
            (
                "",
                "ASSIGNMENT_EMPLOYEE_CONTACT!NUMBER_ADDRESS",
                "Employee Preferred",
                "Personal Email",
            ),
            ("", "ASSIGNMENT_DEPENDENT!FIRST_NAME", "Dependent First Name", "Dependent First Name"),
            ("", "ASSIGNMENT_DEPENDENT!LAST_NAME", "Dependent Last Name", "Dependent Last Name"),
            (
                "",
                "ASSIGNMENT_DEPENDENT!RELATIONSHIP",
                "Dependent Relationship",
                "Dependent Relationship",
            ),
            ("", "ASSIGNMENT_DEPENDENT!GENDER", "Dependent Gender", "Dependent Gender"),
            (
                "",
                "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
                "Dependent Date of Birth",
                "Dependent Date of Birth",
            ),
        ]

    for r_idx in range(4):
        ws.append([h[r_idx] for h in headers])

    for row in rows:
        ws.append(row)

    wb.save(path)
    wb.close()
    return path


# ==============================================================================
# 1. ONE EMPLOYEE WITH MULTIPLE ASSIGNMENTS
# ==============================================================================


def test_regression_one_employee_multiple_assignments_sequential_ids(tmp_path: Path):
    """Option B: Sequential ID synthesis prevents duplicate key errors for repeat assignments."""
    src_path = tmp_path / "one_emp_multi_asg.xlsx"
    rows = [
        # Assignment 1 for E9001
        [
            "E9001",
            "Initiated",
            "T-1001",
            "Male",
            "1985-05-15",
            "United States",
            "United Kingdom",
            "100 Host Road, London",
            None,
            "1234567890",
            "e9001@example.com",
            None,
            None,
            None,
            None,
            None,
        ],
        # Assignment 2 for E9001
        [
            "E9001",
            "Initiated",
            "T-1002",
            "Male",
            "1985-05-15",
            "United States",
            "Germany",
            "200 Berlin Way, Berlin",
            None,
            "1234567890",
            "e9001@example.com",
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    # Strategy: STRATEGY_EMPLOYEE_NUMBER (Option B sequential synthesis)
    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        strategy=STRATEGY_EMPLOYEE_NUMBER,
    )

    # Must produce 2 primary INSERT records (one for each assignment)
    assert len(res.insert_records) == 2
    asg1 = res.insert_records[0]
    asg2 = res.insert_records[1]

    # Assignment 1: 1st time employee is seen -> Col 1 = "INSERT", Col 2 = "INSERT"
    assert asg1[1] == "INSERT"
    assert asg1[2] == "INSERT"
    assert asg1[3] == "E9001"
    assert asg1[4] == "NEW"
    assert asg1[5] == "E9001"

    # Assignment 2: repeat assignment for same employee -> Col 1 = "IGNORE", Col 2 = "INSERT"
    assert asg2[1] == "IGNORE"
    assert asg2[2] == "INSERT"
    assert asg2[3] == "E9001"
    assert asg2[4] == "NEW"
    assert asg2[5] == "E9001-2"  # Option B synthesized sequence prevents key collision!

    # Child UPDATE records must reference their respective parent assignment ID
    assert len(res.update_records) >= 2
    for upd in res.update_records:
        assert upd[1] == "IGNORE"
        assert upd[2] == "UPDATE"
        assert upd.get(3) is None  # Col 3 strictly blank
        assert upd.get(4) is None  # Col 4 strictly blank
        assert upd[5] in ("E9001", "E9001-2")

    # Reconciliation must verify relational integrity with zero duplicate key errors
    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True
    assert recon["status"] == "VERIFIED_PASS"
    assert len(recon["errors"]) == 0
    assert recon["insert_records_count"] == 2


def test_regression_one_employee_multiple_assignments_distinct_topia_ids(tmp_path: Path):
    """Under Topia ID strategy, distinct Topia assignment IDs are used directly."""
    src_path = tmp_path / "multi_asg_topia_ids.xlsx"
    rows = [
        ["E9001", "Initiated", "TOP-001", "Female", "1990-01-01", "USA", "UK", None, None, None, None, None, None, None, None, None],
        ["E9001", "Initiated", "TOP-002", "Female", "1990-01-01", "USA", "FRA", None, None, None, None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        strategy=STRATEGY_TOPIA_ID_WITH_FALLBACK,
    )

    assert len(res.insert_records) == 2
    assert res.insert_records[0][1] == "INSERT"
    assert res.insert_records[0][2] == "INSERT"
    assert res.insert_records[0][5] == "TOP-001"

    assert res.insert_records[1][1] == "IGNORE"
    assert res.insert_records[1][2] == "INSERT"
    assert res.insert_records[1][5] == "TOP-002"

    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True
    assert len(recon["errors"]) == 0


# ==============================================================================
# 2. MULTIPLE EMPLOYEES WITH DISTINCT IDENTIFIERS
# ==============================================================================


def test_regression_multiple_employees_distinct_identifiers(tmp_path: Path):
    """Multiple employees with distinct identifiers generate clean INSERT rows without collision."""
    src_path = tmp_path / "multiple_distinct_employees.xlsx"
    rows = [
        ["EMP001", "Initiated", "T1", "Male", "1980-01-01", "USA", "CAN", None, None, "111-222", None, None, None, None, None, None],
        ["EMP002", "Initiated", "T2", "Female", "1985-02-02", "USA", "MEX", None, None, "333-444", None, None, None, None, None, None],
        ["EMP003", "Initiated", "T3", "Non-Binary", "1990-03-03", "USA", "DEU", None, None, "555-666", None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    res = transform_topia_to_equus(parsed, DEFAULT_TEMPLATE_PATH)

    assert len(res.insert_records) == 3
    for idx, emp_id in enumerate(["EMP001", "EMP002", "EMP003"]):
        rec = res.insert_records[idx]
        assert rec[1] == "INSERT"
        assert rec[2] == "INSERT"
        assert rec[3] == emp_id
        assert rec[4] == "NEW"
        assert rec[5] == emp_id

    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True
    assert recon["insert_records_count"] == 3
    assert recon["status"] == "VERIFIED_PASS"
    assert len(recon["errors"]) == 0


# ==============================================================================
# 3. DEPENDENTS LINKED TO THE CORRECT PARENT
# ==============================================================================


def test_regression_dependents_embedded_in_source_row(tmp_path: Path):
    """Embedded dependent fields on source row populate target Equus columns 137..143."""
    src_path = tmp_path / "embedded_dependent.xlsx"
    rows = [
        [
            "EMP100",
            "Initiated",
            "T-100",
            "Female",
            "1982-08-20",
            "USA",
            "UK",
            None,
            None,
            None,
            None,
            "Alice",
            "Smith",
            "Child",
            "Female",
            "2015-06-10",
        ]
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    res = transform_topia_to_equus(parsed, DEFAULT_TEMPLATE_PATH)

    assert len(res.insert_records) == 1
    asg = res.insert_records[0]
    # In equus_template.xlsx:
    # 137: BIRTH_DATE, 138: LAST_NAME, 139: FIRST_NAME, 141: RELATIONSHIP, 142: GENDER
    assert asg.get(139) == "Alice"
    assert asg.get(138) == "Smith"
    assert asg.get(141) == "Child"
    assert asg.get(142) == "Female"
    assert asg.get(137) == "06/10/2015"

    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True


def test_regression_dependents_secondary_records_multi_children(tmp_path: Path):
    """Secondary dependent records for an employee: Child 0 packs on Row 0, Child 1 on Row 1 (UPDATE)."""
    src_path = tmp_path / "secondary_dependents.xlsx"
    rows = [
        ["EMP200", "Initiated", "T-200", "Male", "1975-04-12", "USA", "FRA", None, None, None, None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    secondary_deps = [
        {
            "employee_id": "EMP200",
            "first_name": "Sarah",
            "last_name": "Connor",
            "relationship": "Spouse",
            "gender": "Female",
            "birth_date": "1977-03-15",
            "status": "Accompanied",
        },
        {
            "employee_id": "EMP200",
            "first_name": "John",
            "last_name": "Connor",
            "relationship": "Child",
            "gender": "Male",
            "birth_date": "2005-02-28",
            "status": "Accompanied",
        },
    ]

    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        dependent_records=secondary_deps,
    )

    # 1 INSERT record + 1 UPDATE record (for 2nd dependent)
    assert len(res.insert_records) == 1
    assert len(res.update_records) == 1
    assert len(res.all_output_records) == 2

    # Row 0 (INSERT): packs 1st dependent (Sarah)
    r0 = res.insert_records[0]
    assert r0[1] == "INSERT"
    assert r0[2] == "INSERT"
    assert r0[3] == "EMP200"
    assert r0[5] == "EMP200"
    assert r0.get(139) == "Sarah"
    assert r0.get(138) == "Connor"
    assert r0.get(141) == "Spouse"

    # Row 1 (UPDATE): packs 2nd dependent (John)
    r1 = res.update_records[0]
    assert r1[1] == "IGNORE"
    assert r1[2] == "UPDATE"
    assert r1.get(3) is None
    assert r1.get(4) is None
    assert r1[5] == "EMP200"  # links to parent assignment ID
    assert r1.get(139) == "John"
    assert r1.get(138) == "Connor"
    assert r1.get(141) == "Child"

    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True
    assert recon["update_records_count"] == 1


def test_regression_dependents_explicit_assignment_id_linkage(tmp_path: Path):
    """Dependent with explicit assignment_id links specifically to that assignment."""
    src_path = tmp_path / "dep_explicit_asg.xlsx"
    rows = [
        ["EMP300", "Initiated", "T-301", "Male", "1980-01-01", "USA", "SGP", None, None, None, None, None, None, None, None, None],
        ["EMP300", "Initiated", "T-302", "Male", "1980-01-01", "USA", "JPN", None, None, None, None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    # Secondary dependent explicitly targeted at 2nd assignment ("EMP300-2")
    secondary_deps = [
        {
            "employee_id": "EMP300",
            "assignment_id": "EMP300-2",
            "first_name": "Ken",
            "last_name": "Watanabe",
            "relationship": "Child",
            "gender": "Male",
        }
    ]

    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        strategy=STRATEGY_EMPLOYEE_NUMBER,
        dependent_records=secondary_deps,
    )

    asg1 = res.insert_records[0]
    asg2 = res.insert_records[1]

    # Asg 1 has no dependent
    assert asg1.get(139) is None

    # Asg 2 received Ken Watanabe
    assert asg2.get(139) == "Ken"
    assert asg2.get(138) == "Watanabe"
    assert asg2[5] == "EMP300-2"

    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True


# ==============================================================================
# 4. MISSING OR AMBIGUOUS LINKAGE
# ==============================================================================


def test_regression_orphan_dependent_unlinked_warning(tmp_path: Path):
    """Dependent referencing non-existent employee generates ORPHAN_DEPENDENT_RECORD warning."""
    src_path = tmp_path / "valid_parent.xlsx"
    rows = [
        ["EMP400", "Initiated", "T-400", "Female", "1992-11-05", "USA", "AUS", None, None, None, None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    secondary_deps = [
        {
            "employee_id": "NON_EXISTENT_EMP_999",
            "first_name": "Ghost",
            "last_name": "Child",
            "relationship": "Child",
        }
    ]

    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        dependent_records=secondary_deps,
    )

    # Ghost child must be omitted from output
    assert len(res.update_records) == 0
    assert res.insert_records[0].get(139) is None

    # Warning must be emitted with code ORPHAN_DEPENDENT_RECORD
    orphan_warns = [w for w in res.warnings if w.get("code") == "ORPHAN_DEPENDENT_RECORD"]
    assert len(orphan_warns) == 1
    assert "NON_EXISTENT_EMP_999" in orphan_warns[0]["warning"]

    # Transformation still reconciles with COMPLETED_WITH_WARNINGS
    recon = reconcile_equus_transformation(res)
    assert recon["status"] == "COMPLETED_WITH_WARNINGS"
    assert recon["is_valid"] is True


def test_regression_ambiguous_dependent_multi_assignment_warning(tmp_path: Path):
    """Dependent referencing multi-assignment employee without assignment_id triggers AMBIGUOUS warning."""
    src_path = tmp_path / "ambiguous_dep.xlsx"
    rows = [
        ["EMP500", "Initiated", "T-501", "Male", "1983-04-18", "USA", "BRA", None, None, None, None, None, None, None, None, None],
        ["EMP500", "Initiated", "T-502", "Male", "1983-04-18", "USA", "ARG", None, None, None, None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    # Dependent has employee_id but no assignment_id
    secondary_deps = [
        {
            "employee_id": "EMP500",
            "first_name": "Ambiguous",
            "last_name": "Child",
            "relationship": "Child",
        }
    ]

    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        strategy=STRATEGY_EMPLOYEE_NUMBER,
        dependent_records=secondary_deps,
    )

    # Linked to primary assignment
    assert res.insert_records[0].get(139) == "Ambiguous"

    # Actionable warning emitted
    ambig_warns = [w for w in res.warnings if w.get("code") == "AMBIGUOUS_DEPENDENT_LINKAGE"]
    assert len(ambig_warns) == 1
    assert "Ambiguous Child" in ambig_warns[0]["warning"]
    assert "EMP500" in ambig_warns[0]["warning"]


def test_regression_unlinked_dependent_missing_all_keys(tmp_path: Path):
    """Dependent missing both employee_id and assignment_id triggers UNLINKED warning."""
    src_path = tmp_path / "unlinked_keys.xlsx"
    rows = [
        ["EMP600", "Initiated", "T-600", "Female", "1988-09-09", "USA", "ESP", None, None, None, None, None, None, None, None, None],
    ]
    _create_synthetic_source_file(src_path, rows)
    parsed = parse_three_row_workbook(src_path)

    secondary_deps = [
        {
            "first_name": "Unlinked",
            "last_name": "Record",
            "relationship": "Other",
        }
    ]

    res = transform_topia_to_equus(
        parsed,
        DEFAULT_TEMPLATE_PATH,
        dependent_records=secondary_deps,
    )

    unlinked_warns = [w for w in res.warnings if w.get("code") == "UNLINKED_DEPENDENT_RECORD"]
    assert len(unlinked_warns) == 1
    assert "missing both employee and assignment identifiers" in unlinked_warns[0]["warning"]


# ==============================================================================
# 5. INSERT AND UPDATE GENERATION AND RECONCILIATION
# ==============================================================================


def test_regression_insert_and_update_excel_artifact_generation(tmp_path: Path):
    """Verify generated Excel workbook cell-by-cell for EAFH INSERT and UPDATE rows."""
    src_path = tmp_path / "full_pipeline_source.xlsx"
    rows = [
        [
            "EMP700",
            "Initiated",
            "T-700",
            "Female",
            "1986-07-25",
            "United States",
            "United Kingdom",
            "10 Piccadilly, London",
            "20 Main St, Boston",
            "555-0199",
            "emp700@corp.com",
            None,
            None,
            None,
            None,
            None,
        ]
    ]
    _create_synthetic_source_file(src_path, rows)

    out_file = tmp_path / "output_equus.xlsx"
    parsed = parse_three_row_workbook(src_path)
    res = transform_topia_to_equus(parsed, DEFAULT_TEMPLATE_PATH)

    # Add a secondary contact to generate UPDATE record
    assert len(res.insert_records) == 1
    assert len(res.update_records) >= 1  # 2 addresses + 2 contacts -> UPDATE rows created

    generate_equus_import_file(
        DEFAULT_TEMPLATE_PATH,
        res.all_output_records,
        out_file,
    )

    wb = openpyxl.load_workbook(out_file)
    ws = wb.active

    # Row 4: Primary INSERT record
    assert ws.cell(4, 1).value == "INSERT"
    assert ws.cell(4, 2).value == "INSERT"
    assert ws.cell(4, 3).value == "EMP700"
    assert ws.cell(4, 4).value == "NEW"
    assert ws.cell(4, 5).value == "EMP700"

    # Row 5+: Child UPDATE records
    for r_idx in range(5, ws.max_row + 1):
        assert ws.cell(r_idx, 1).value == "IGNORE"
        assert ws.cell(r_idx, 2).value == "UPDATE"
        assert ws.cell(r_idx, 3).value is None  # Must remain empty
        assert ws.cell(r_idx, 4).value is None  # Must remain empty
        assert ws.cell(r_idx, 5).value == "EMP700"  # Must match parent

    wb.close()

    # Reconcile result
    recon = reconcile_equus_transformation(res)
    assert recon["is_valid"] is True
    assert recon["status"] == "VERIFIED_PASS"
    assert recon["insert_records_count"] == 1
    assert recon["update_records_count"] == len(res.update_records)
    assert recon["total_output_records"] == 1 + len(res.update_records)
    assert recon["expansion_ratio"] > 1.0


def test_regression_reconciliation_catches_tampered_records():
    """Reconciliation validation strictly catches malformed INSERT and UPDATE records."""
    # 1. UPDATE record having Col 3 populated (violates blank Col 3 rule)
    res_bad_col3 = TransformationResult(
        insert_records=[{1: "INSERT", 2: "INSERT", 3: "E1", 4: "NEW", 5: "E1"}],
        update_records=[{1: "IGNORE", 2: "UPDATE", 3: "E1", 4: None, 5: "E1"}],
        all_output_records=[
            {1: "INSERT", 2: "INSERT", 3: "E1", 4: "NEW", 5: "E1"},
            {1: "IGNORE", 2: "UPDATE", 3: "E1", 4: None, 5: "E1"},
        ],
        total_evaluated_rows=1,
    )
    recon = reconcile_equus_transformation(res_bad_col3)
    assert recon["is_valid"] is False
    assert any("contains unexpected Employee Number" in e for e in recon["errors"])

    # 2. Duplicate Assignment Identifier across INSERT records
    res_dup_id = TransformationResult(
        insert_records=[
            {1: "INSERT", 2: "INSERT", 3: "E1", 4: "NEW", 5: "COLLISION"},
            {1: "IGNORE", 2: "INSERT", 3: "E1", 4: "NEW", 5: "COLLISION"},
        ],
        update_records=[],
        all_output_records=[],
        total_evaluated_rows=2,
    )
    recon_dup = reconcile_equus_transformation(res_dup_id)
    assert recon_dup["is_valid"] is False
    assert any("Duplicate Assignment Identifier detected: 'COLLISION'" in e for e in recon_dup["errors"])

    # 3. Repeat assignment with Col 1='INSERT' (attempting to re-insert demographic record)
    res_repeat_insert = TransformationResult(
        insert_records=[
            {1: "INSERT", 2: "INSERT", 3: "E1", 4: "NEW", 5: "E1"},
            {1: "INSERT", 2: "INSERT", 3: "E1", 4: "NEW", 5: "E1-2"},
        ],
        update_records=[],
        all_output_records=[],
        total_evaluated_rows=2,
    )
    recon_repeat = reconcile_equus_transformation(res_repeat_insert)
    assert recon_repeat["is_valid"] is False
    assert any("employee demographics were already inserted" in e for e in recon_repeat["errors"])


# ==============================================================================
# 6. AUDIT HISTORY APPEND-ONLY APPLICATION LOGGING DESCRIPTION
# ==============================================================================


def test_regression_audit_history_described_as_append_only_logging():
    """Verify audit history is described strictly as append-only application logging, not WORM."""
    audit_page = Path("frontend/src/pages/AuditPage.tsx").read_text(encoding="utf-8")
    assert "Append-only application event log" in audit_page
    assert "immutable audit log" not in audit_page.lower()
    assert "worm" not in audit_page.lower()
