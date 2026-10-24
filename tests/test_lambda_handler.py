"""Unit tests for AWS Lambda S3 integration handler.

Validates event parsing, trigger guards, URL decoding, transformation execution,
and error propagation without requiring real AWS resources or credentials.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure lambda/src is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAMBDA_SRC = PROJECT_ROOT / "lambda" / "src"
if str(LAMBDA_SRC) not in sys.path:
    sys.path.insert(0, str(LAMBDA_SRC))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import handler  # noqa: E402

FIXTURE_PATH = PROJECT_ROOT / "topia_equus_test_workbooks" / "01_valid_basic.xlsx"


@pytest.fixture
def sample_xlsx_bytes() -> bytes:
    assert FIXTURE_PATH.exists(), f"Test fixture not found: {FIXTURE_PATH}"
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def mock_s3_env(monkeypatch):
    """Provide isolated environment variables for Lambda execution."""
    monkeypatch.setenv("DEST_BUCKET", "test-dest-bucket")
    monkeypatch.setenv("DEST_PREFIX", "equus/")
    monkeypatch.setenv("SOURCE_PREFIX", "topia/incoming/")
    monkeypatch.setenv("SOURCE_SUFFIX", ".xlsx")
    monkeypatch.setenv("MAX_SOURCE_BYTES", "52428800")


def test_valid_s3_event_success(mock_s3_env, sample_xlsx_bytes, monkeypatch):
    """Test full processing lifecycle from valid S3 event through to dual workbook uploads."""
    mock_s3 = MagicMock()
    # Mock download: return real workbook bytes
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_xlsx_bytes)}
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    "object": {
                        "key": "topia/incoming/01_valid_basic.xlsx",
                        "size": len(sample_xlsx_bytes),
                    },
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]

    assert res["status"] == "COMPLETED"
    assert res["source"] == "s3://source-bucket/topia/incoming/01_valid_basic.xlsx"
    assert "_EQUUS_" in res["output"]
    assert "_MAPPING_REPORT_" in res["report"]
    assert res["output"].startswith("s3://test-dest-bucket/equus/01_valid_basic_EQUUS_")
    assert res["report"].startswith(
        "s3://test-dest-bucket/equus/reports/01_valid_basic_MAPPING_REPORT_"
    )

    # Assert S3 download was called with correct parameters
    mock_s3.get_object.assert_called_once_with(
        Bucket="source-bucket", Key="topia/incoming/01_valid_basic.xlsx"
    )

    # Assert S3 uploads occurred (two files: import and report)
    assert mock_s3.put_object.call_count == 2
    calls = mock_s3.put_object.call_args_list

    # First call: Equus import workbook
    import_call = calls[0].kwargs
    assert import_call["Bucket"] == "test-dest-bucket"
    assert import_call["Key"].startswith("equus/01_valid_basic_EQUUS_")
    assert import_call["ContentType"] == handler.XLSX_CONTENT_TYPE
    assert import_call["Metadata"]["source-bucket"] == "source-bucket"

    # Second call: Mapping report workbook
    report_call = calls[1].kwargs
    assert report_call["Bucket"] == "test-dest-bucket"
    assert report_call["Key"].startswith("equus/reports/01_valid_basic_MAPPING_REPORT_")
    assert report_call["ContentType"] == handler.XLSX_CONTENT_TYPE


def test_wrong_prefix_skipped(mock_s3_env, monkeypatch):
    """Test that objects dropped outside the required prefix are safely skipped."""
    mock_s3 = MagicMock()
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    "object": {"key": "unrelated/folder/file.xlsx", "size": 100},
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "SKIPPED"
    assert "outside required prefix" in res["reason"]
    mock_s3.get_object.assert_not_called()
    mock_s3.put_object.assert_not_called()


def test_wrong_extension_skipped(mock_s3_env, monkeypatch):
    """Test that non-.xlsx files are dropped by the trigger guard."""
    mock_s3 = MagicMock()
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    "object": {"key": "topia/incoming/notes.csv", "size": 100},
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "SKIPPED"
    assert "does not end with required suffix" in res["reason"]
    mock_s3.get_object.assert_not_called()


def test_temporary_excel_file_skipped(mock_s3_env, monkeypatch):
    """Test that Excel lock files (~$filename.xlsx) are safely ignored."""
    mock_s3 = MagicMock()
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    "object": {"key": "topia/incoming/~$01_valid_basic.xlsx", "size": 165},
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "SKIPPED"
    assert "Excel lock/temporary file" in res["reason"]
    mock_s3.get_object.assert_not_called()


def test_url_encoded_keys_decoded(mock_s3_env, sample_xlsx_bytes, monkeypatch):
    """Test that S3 URL-encoded characters (+ and %20) are safely decoded."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_xlsx_bytes)}
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    # URL-encoded string for "Topia + Export 2026.xlsx"
                    "object": {
                        "key": "topia/incoming/Topia%20%2B%20Export%202026.xlsx",
                        "size": len(sample_xlsx_bytes),
                    },
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "COMPLETED"

    # Verify get_object was called with decoded key
    mock_s3.get_object.assert_called_once_with(
        Bucket="source-bucket", Key="topia/incoming/Topia + Export 2026.xlsx"
    )
    assert "Topia + Export 2026_EQUUS_" in res["output"]


def test_missing_and_malformed_event_fields(mock_s3_env):
    """Test that malformed or empty payloads raise clear ValueError exceptions."""
    with pytest.raises(ValueError, match="expected dictionary"):
        handler.lambda_handler(["not-a-dict"])  # type: ignore

    with pytest.raises(ValueError, match="empty or invalid 'Records' list"):
        handler.lambda_handler({"Records": []})

    with pytest.raises(ValueError, match="missing 's3' container"):
        handler.lambda_handler({"Records": [{"eventName": "ObjectCreated:Put"}]})

    with pytest.raises(ValueError, match="bucket name or object key is missing"):
        handler.lambda_handler(
            {
                "Records": [
                    {
                        "eventName": "ObjectCreated:Put",
                        "s3": {"bucket": {}, "object": {}},
                    }
                ]
            }
        )

    with pytest.raises(ValueError, match="Unrecognized event structure"):
        handler.lambda_handler({"unknown_event": True})


def test_direct_invocation_payload(mock_s3_env, sample_xlsx_bytes, monkeypatch):
    """Test that direct invocation {source_bucket, source_key} is fully supported."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_xlsx_bytes)}
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "source_bucket": "direct-source-bucket",
        "source_key": "topia/incoming/01_valid_basic.xlsx",
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "COMPLETED"
    assert res["source"] == "s3://direct-source-bucket/topia/incoming/01_valid_basic.xlsx"


def test_transformation_exception_propagates(mock_s3_env, sample_xlsx_bytes, monkeypatch):
    """Test that pipeline exceptions are logged and propagated to trigger SQS DLQ."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_xlsx_bytes)}
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    def failing_pipeline(*args, **kwargs):
        raise RuntimeError("Simulated internal transformation failure")

    monkeypatch.setattr(handler, "run_equus_migration_pipeline", failing_pipeline)

    event = {
        "source_bucket": "source-bucket",
        "source_key": "topia/incoming/01_valid_basic.xlsx",
    }

    with pytest.raises(RuntimeError, match="Simulated internal transformation failure"):
        handler.lambda_handler(event)


def test_upload_failure_propagates(mock_s3_env, sample_xlsx_bytes, monkeypatch):
    """Test that S3 upload exceptions are propagated to trigger SQS DLQ."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: sample_xlsx_bytes)}
    mock_s3.put_object.side_effect = ConnectionResetError("S3 PutObject network drop")
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "source_bucket": "source-bucket",
        "source_key": "topia/incoming/01_valid_basic.xlsx",
    }

    with pytest.raises(ConnectionResetError, match="S3 PutObject network drop"):
        handler.lambda_handler(event)


def test_oversized_payload_skipped(mock_s3_env, monkeypatch):
    """Test that objects exceeding MAX_SOURCE_BYTES are skipped with a warning."""
    mock_s3 = MagicMock()
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "source-bucket"},
                    "object": {"key": "topia/incoming/huge.xlsx", "size": 60 * 1024 * 1024},
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "SKIPPED"
    assert "exceeds maximum allowable threshold" in res["reason"]
    mock_s3.get_object.assert_not_called()


def test_anti_loop_guard(mock_s3_env, monkeypatch):
    """Objects dropped in destination prefix are skipped to prevent infinite retriggering."""
    mock_s3 = MagicMock()
    monkeypatch.setattr(handler, "get_s3_client", lambda: mock_s3)

    # Pretend source bucket is the same as dest bucket and key starts with equus/
    monkeypatch.setenv("SOURCE_PREFIX", "equus/")

    event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "test-dest-bucket"},
                    "object": {
                        "key": "equus/01_valid_basic_EQUUS_20261024T000000Z.xlsx",
                        "size": 1000,
                    },
                },
            }
        ]
    }

    result = handler.lambda_handler(event)
    assert len(result["results"]) == 1
    res = result["results"][0]
    assert res["status"] == "SKIPPED"
    assert "anti-loop protection" in res["reason"]
    mock_s3.get_object.assert_not_called()
