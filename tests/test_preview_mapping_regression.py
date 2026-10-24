from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.errors import DomainError
from app.main import app
from app.schemas import MappingStatus, MappingType
from app.services.preview import preview_direct_mappings
from app.services.profiling import profile_workbook
from app.services.reconciliation import reconcile_preview
from app.services.transform import (
    is_blank_or_ambiguous_header,
    is_country_identifier,
    is_date_identifier,
    validate_mapping_compatibility,
)
from app.services.workbooks import detect_sheet_layout, inspect_workbook
from app.workers.worker import process_once

NEG_FIXTURE = Path("topia_equus_test_workbooks/04_negative_missing_employee_id.xlsx")
VALID_FIXTURE = Path("topia_equus_test_workbooks/01_valid_basic.xlsx")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_source_workbook_structure_inspection():
    """Task 1 & 2: Inspect actual source workbook sheet names, headers, rules, and data rows."""
    assert NEG_FIXTURE.exists()
    schemas = inspect_workbook(NEG_FIXTURE)
    assert len(schemas) == 1
    sheet = schemas[0]
    assert sheet.name == "Sheet1"
    assert sheet.max_row == 6
    assert sheet.max_column == 8

    # Assert multi-row header detection: 4 header rows, data starts at row 5
    assert sheet.header_rows_count == 4
    assert sheet.data_start_row == 5

    # Canonical headers must be the meaningful human display headers, NOT row 1 rules or synthetic blanks
    expected_headers = [
        "Full Name",
        "First Name",
        "Last Name",
        "Employee ID",
        "Assignment ID",
        "Birth Date",
        "Gender",
        "Home Country",
    ]
    assert sheet.headers == expected_headers

    # Row 1 rules and blanks must NOT be present as column names
    assert "__blank_1" not in sheet.headers
    assert "US Date Format" not in sheet.headers
    assert "Match dropdown" not in sheet.headers

    # Technical headers must be correctly detected on row 2
    assert sheet.technical_headers[1] == "EMPLOYEE!FIRST_NAME"
    assert sheet.technical_headers[2] == "EMPLOYEE!LAST_NAME"
    assert sheet.technical_headers[3] == "EMPLOYEE!SYSTEM_NUMBER"
    assert sheet.technical_headers[4] == "ASSIGNMENT_CF!CF_TEXT029"
    assert sheet.technical_headers[5] == "EMPLOYEE!BIRTH_DATE"
    assert sheet.technical_headers[6] == "EMPLOYEE!GENDER"
    assert sheet.technical_headers[7] == "ASSIGNMENT!FROM_COUNTRY"

    # Data type sampling must sample from row 5 onwards, not header strings
    assert sheet.inferred_types["Birth Date"] in {"date", "string"}


def test_preview_pipeline_excludes_header_rows_and_counts_data_rows():
    """Task 2 & 7: Header rows 1-4 must never be evaluated as employee data records."""
    assert NEG_FIXTURE.exists()
    mappings = [
        {
            "mapping_id": "m-first-name",
            "source_id": "src-1",
            "source_sheet": "Sheet1",
            "source_field": "First Name",
            "target_entity": "employee",
            "target_field": "first_name",
            "mapping_type": MappingType.DIRECT,
            "status": MappingStatus.APPROVED,
        },
        {
            "mapping_id": "m-birth-date",
            "source_id": "src-1",
            "source_sheet": "Sheet1",
            "source_field": "Birth Date",
            "target_entity": "employee",
            "target_field": "birth_date",
            "mapping_type": MappingType.DIRECT,
            "status": MappingStatus.APPROVED,
        },
        {
            "mapping_id": "m-tech-country",
            "source_id": "src-1",
            "source_sheet": "Sheet1",
            "source_field": "ASSIGNMENT!FROM_COUNTRY",
            "target_entity": "employee",
            "target_field": "home_country",
            "mapping_type": MappingType.DIRECT,
            "status": MappingStatus.APPROVED,
        },
    ]

    result = preview_direct_mappings(NEG_FIXTURE, mappings)

    # Preview counts must distinguish source data rows from header rows
    assert result["records_evaluated"] == 2  # Exactly 2 data rows (rows 5 and 6)
    assert result["header_rows_count"] == 4  # 4 header/metadata rows
    assert result["data_start_row"] == 5
    assert result["eligible_records"] == 2

    # Verify that header rows were not evaluated as employee records
    records = result["records"]
    assert len(records) == 2

    # Row 5 (Alex Morgan)
    rec1 = records[0]
    assert rec1["row"] == 5
    assert rec1["proposed"]["first_name"] == "Alex"
    assert rec1["proposed"]["birth_date"] == "1987-03-09"
    assert rec1["proposed"]["home_country"] == "Australia"

    # Row 6 (Sam Patel)
    rec2 = records[1]
    assert rec2["row"] == 6
    assert rec2["proposed"]["first_name"] == "Sam"
    assert rec2["proposed"]["birth_date"] == "1991-11-21"
    assert rec2["proposed"]["home_country"] == "India"

    # Header strings must NEVER appear in proposed values
    all_values = [
        str(v)
        for r in records
        for v in r["proposed"].values()
    ]
    for forbidden in ["EMPLOYEE!BIRTH_DATE", "Date of Birth", "Birth Date", "US Date Format", "Match dropdown"]:
        assert forbidden not in all_values


def test_profiling_excludes_header_rows():
    """Task 7: Profiling must count only populated data rows, excluding multi-row headers."""
    profile = profile_workbook(NEG_FIXTURE)
    assert len(profile["sheets"]) == 1
    sheet = profile["sheets"][0]
    assert sheet["header_rows_count"] == 4
    assert sheet["populated_rows"] == 2  # Rows 5 and 6 only
    assert sheet["duplicate_rows"] == 0


def test_cannot_map_date_transformation_or_date_source_to_country_code():
    """Task 4: A date-format transformation cannot be applied to a country-code field."""
    # 1. Date transform on country target
    with pytest.raises(ValueError, match="Cannot apply date-format transformation to country code field"):
        validate_mapping_compatibility(
            source_field="Country",
            target_field="country_code",
            transformation={"op": "date_format"},
            mapping_type="transformed",
        )

    # 2. Date source field on country target
    with pytest.raises(ValueError, match="cannot map date source field 'US Date Format' to country code field"):
        validate_mapping_compatibility(
            source_field="US Date Format",
            target_field="country_code",
            transformation=None,
            mapping_type="direct",
        )

    with pytest.raises(ValueError, match="cannot map date source field 'EMPLOYEE!BIRTH_DATE' to country code field"):
        validate_mapping_compatibility(
            source_field="EMPLOYEE!BIRTH_DATE",
            target_field="country_code",
            transformation=None,
            mapping_type="direct",
        )

    with pytest.raises(ValueError, match="cannot map date source field 'Birth Date' to country code field"):
        validate_mapping_compatibility(
            source_field="Birth Date",
            target_field="country_code",
            transformation=None,
            mapping_type="direct",
        )


def test_cannot_map_blank_headers_to_meaningful_fields():
    """Task 5: Blank headers cannot be mapped to target fields without review."""
    with pytest.raises(ValueError, match="Ambiguous or empty source header '__blank_1'"):
        validate_mapping_compatibility(
            source_field="__blank_1",
            target_field="first_name",
            transformation=None,
            mapping_type="direct",
        )

    with pytest.raises(ValueError, match="Ambiguous or empty source header '_blank_1'"):
        validate_mapping_compatibility(
            source_field="_blank_1",
            target_field="country_code",
            transformation=None,
            mapping_type="direct",
        )


def test_incompatible_mappings_rejected_by_api_endpoints(client: TestClient):
    """Task 6 & 8: API rejects creating and approving incompatible or blank mappings."""
    with open(NEG_FIXTURE, "rb") as f:
        upload_resp = client.post(
            "/api/v1/sources/upload",
            files={"file": ("04_negative_missing_employee_id.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert upload_resp.status_code == 201
    source = upload_resp.json()
    source_id = source["source_id"]

    # 1. Attempting to map blank header directly must fail
    res_blank = client.post(
        "/api/v1/mappings",
        json={
            "source_id": source_id,
            "source_entity": "employee",
            "source_sheet": "Sheet1",
            "source_field": "__blank_1",
            "target_entity": "employee",
            "target_field": "first_name",
            "mapping_type": "direct",
        },
    )
    assert res_blank.status_code in {400, 422}
    assert "AMBIGUOUS_SOURCE_HEADER" in res_blank.text or "INCOMPATIBLE_FIELD_MAPPING" in res_blank.text or "SOURCE_FIELD_NOT_FOUND" in res_blank.text

    # 2. Attempting to map date field to country_code must fail
    res_date_to_country = client.post(
        "/api/v1/mappings",
        json={
            "source_id": source_id,
            "source_entity": "employee",
            "source_sheet": "Sheet1",
            "source_field": "Birth Date",
            "target_entity": "employee",
            "target_field": "country_code",
            "mapping_type": "direct",
        },
    )
    assert res_date_to_country.status_code == 400
    assert "INCOMPATIBLE_FIELD_MAPPING" in res_date_to_country.text

    # 3. Valid mapping can be created and approved
    res_valid = client.post(
        "/api/v1/mappings",
        json={
            "source_id": source_id,
            "source_entity": "employee",
            "source_sheet": "Sheet1",
            "source_field": "First Name",
            "target_entity": "employee",
            "target_field": "first_name",
            "mapping_type": "direct",
        },
    )
    assert res_valid.status_code == 201
    mapping_id = res_valid.json()["mapping_id"]

    apprv = client.post(f"/api/v1/mappings/{mapping_id}/approve")
    assert apprv.status_code == 200
    assert apprv.json()["status"] == "approved"


def test_preview_with_incompatible_or_blank_mapping_generates_warnings():
    """Task 4, 5, 6: Preview pipeline suppresses incompatible or blank mappings and adds warnings."""
    incompatible_mappings = [
        {
            "mapping_id": "m-bad-date",
            "source_id": "src-1",
            "source_sheet": "Sheet1",
            "source_field": "Birth Date",
            "target_entity": "employee",
            "target_field": "country_code",
            "mapping_type": MappingType.DIRECT,
            "status": MappingStatus.APPROVED,
        },
        {
            "mapping_id": "m-blank",
            "source_id": "src-1",
            "source_sheet": "Sheet1",
            "source_field": "__blank_1",
            "target_entity": "employee",
            "target_field": "first_name",
            "mapping_type": MappingType.DIRECT,
            "status": MappingStatus.APPROVED,
        },
    ]

    result = preview_direct_mappings(NEG_FIXTURE, incompatible_mappings)
    warning_codes = [w["code"] for w in result["warnings"]]
    assert "INCOMPATIBLE_FIELD_MAPPING" in warning_codes
    assert "AMBIGUOUS_SOURCE_HEADER" in warning_codes

    # Neither mapping should have generated proposed fields
    for r in result["records"]:
        assert "country_code" not in r["proposed"]
        assert "first_name" not in r["proposed"]


def test_cross_workbook_mapping_id_isolation(client: TestClient):
    """Task 3: A mapping ID belonging to another workbook cannot be used for preview."""
    with open(NEG_FIXTURE, "rb") as f:
        src1 = client.post(
            "/api/v1/sources/upload",
            files={"file": ("wb1.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        ).json()

    with open(VALID_FIXTURE, "rb") as f:
        src2 = client.post(
            "/api/v1/sources/upload",
            files={"file": ("wb2.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        ).json()

    # Create mapping on src1
    mapping1 = client.post(
        "/api/v1/mappings",
        json={
            "source_id": src1["source_id"],
            "source_entity": "employee",
            "source_sheet": "Sheet1",
            "source_field": "First Name",
            "target_entity": "employee",
            "target_field": "first_name",
            "mapping_type": "direct",
        },
    ).json()

    # Attempt to preview src2 with mapping from src1
    bad_preview = client.post(
        "/api/v1/migrations/preview",
        json={"source_id": src2["source_id"], "mapping_id": mapping1["mapping_id"]},
    )
    assert bad_preview.status_code == 404
    payload = bad_preview.json()
    code = payload.get("detail", {}).get("code") if "detail" in payload else payload.get("error", {}).get("code")
    assert code == "MAPPING_NOT_FOUND"


def test_reconcile_preview_records_counts():
    """Task 7: Reconcile preview preserves source data rows and excludes header rows."""
    preview_output = {
        "records_evaluated": 2,
        "eligible_records": 2,
        "header_rows_count": 4,
        "rejected_records": 0,
        "warnings": [],
        "issues": [],
    }
    reconciliation = reconcile_preview(preview_output)
    assert reconciliation["source_records"] == 2
    assert reconciliation["header_rows_count"] == 4
    assert reconciliation["accepted_records"] == 2
    assert reconciliation["rejected_records"] == 0
    assert reconciliation["warning_count"] == 0
