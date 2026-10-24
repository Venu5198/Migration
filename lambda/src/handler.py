"""AWS Lambda entry point: Topia workbook in SOURCE bucket -> Equus import
workbook (+ mapping report) in DEST bucket.

Integrates the existing, tested Equus migration pipeline with AWS Lambda and S3.

Triggers:
  * S3 ObjectCreated notification on the source bucket (filtered to
    SOURCE_PREFIX / SOURCE_SUFFIX - see template.yaml).
  * Direct invoke: {"source_bucket": "...", "source_key": "..."}.

Environment Variables:
  DEST_BUCKET          required  destination S3 bucket name
  DEST_PREFIX          optional  key prefix for outputs (default "equus/")
  SOURCE_PREFIX        optional  only process keys under this prefix (default "topia/incoming/")
  SOURCE_SUFFIX        optional  only process keys ending with this (default ".xlsx")
  ASSIGNMENT_STRATEGY  optional  assignment identifier strategy (default: Option B EMPLOYEE_NUMBER)
  MAX_SOURCE_BYTES     optional  max allowable input size (default 50 MB)
"""

from __future__ import annotations

import json
import logging
import os
import posixpath
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

# Ensure project root is in sys.path so app.services.equus is importable
# both in local environments, tests, and deployed Lambda containers
_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent.parent
for _candidate in [_PROJECT_ROOT, _CURRENT_DIR]:
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from app.services.equus import (  # noqa: E402
    DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
    run_equus_migration_pipeline,
)

log = logging.getLogger("equus.migration.lambda")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    log.addHandler(_handler)
log.setLevel(logging.INFO)

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BUNDLED_TEMPLATE = _CURRENT_DIR / "templates" / "equus_eafh_template.xlsx"
DEFAULT_MAX_SOURCE_BYTES = 50 * 1024 * 1024  # 50 MB

_s3_client_instance = None


def get_s3_client():
    """Lazily initialize and return a Boto3 S3 client."""
    global _s3_client_instance
    if _s3_client_instance is None:
        import boto3

        _s3_client_instance = boto3.client("s3")
    return _s3_client_instance


def _read_s3_object(s3_client, bucket: str, key: str) -> bytes:
    """Download an S3 object and return raw bytes."""
    log.info("Fetching s3://%s/%s", bucket, key)
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    if hasattr(body, "read"):
        return body.read()
    return bytes(body)


def _extract_targets(event: dict[str, Any]) -> list[tuple[str, str, int | None]]:
    """Parse and validate incoming S3 event records or direct invoke payloads."""
    if not isinstance(event, dict):
        raise ValueError(f"Invalid event payload: expected dictionary, got {type(event).__name__}")

    # Case 1: Standard S3 Event Notification
    if "Records" in event:
        records = event.get("Records")
        if not isinstance(records, list) or len(records) == 0:
            raise ValueError("Event contains an empty or invalid 'Records' list.")

        targets: list[tuple[str, str, int | None]] = []
        for idx, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise ValueError(f"Record at index {idx} is not a valid dictionary.")

            event_name = rec.get("eventName", "")
            # Skip non-creation notifications (e.g. ObjectRemoved, TestEvent)
            if event_name and not event_name.startswith("ObjectCreated"):
                log.info("Skipping record with non-creation eventName: %s", event_name)
                continue

            s3_data = rec.get("s3")
            if not isinstance(s3_data, dict):
                raise ValueError(f"Malformed S3 record at index {idx}: missing 's3' container.")

            bucket_meta = s3_data.get("bucket", {})
            object_meta = s3_data.get("object", {})

            bucket_name = bucket_meta.get("name")
            raw_key = object_meta.get("key")
            size = object_meta.get("size")

            if not bucket_name or not raw_key:
                raise ValueError(
                    f"Malformed S3 record at index {idx}: bucket name or object key is missing."
                )

            decoded_key = unquote_plus(raw_key)
            targets.append((bucket_name, decoded_key, size))

        return targets

    # Case 2: Direct Invocation payload
    if "source_bucket" in event and "source_key" in event:
        bucket_name = event.get("source_bucket")
        raw_key = event.get("source_key")
        size = event.get("size")

        if not bucket_name or not raw_key:
            raise ValueError(
                "Direct invocation requires non-empty 'source_bucket' and 'source_key'."
            )

        decoded_key = unquote_plus(raw_key)
        return [(str(bucket_name), decoded_key, size)]

    raise ValueError(
        "Unrecognized event structure: expected S3 'Records' list or 'source_bucket'/'source_key'."
    )


def _accept_guard(
    bucket: str,
    key: str,
    size: int | None,
    dest_bucket: str,
    dest_prefix: str,
) -> str | None:
    """Defense-in-depth validation for incoming S3 objects.

    Returns a descriptive reason if the object should be skipped, or None if valid.
    """
    prefix = os.environ.get("SOURCE_PREFIX", "topia/incoming/")
    suffix = os.environ.get("SOURCE_SUFFIX", ".xlsx").lower()
    max_bytes = int(os.environ.get("MAX_SOURCE_BYTES", DEFAULT_MAX_SOURCE_BYTES))
    filename = posixpath.basename(key)

    # 1. Prefix restriction
    if not key.startswith(prefix):
        return f"Key '{key}' is outside required prefix '{prefix}'"

    # 2. Suffix / file type restriction
    if not key.lower().endswith(suffix):
        return f"Key '{key}' does not end with required suffix '{suffix}'"

    # 3. Excel temporary and lock files
    if filename.startswith("~$") or filename.startswith(".~"):
        return f"Skipping Excel lock/temporary file: '{filename}'"

    # 4. Anti-loop safeguard (prevent re-triggering on own output)
    clean_dest_prefix = dest_prefix if dest_prefix.endswith("/") else f"{dest_prefix}/"
    if bucket == dest_bucket and key.startswith(clean_dest_prefix):
        return (
            f"Key '{key}' is inside destination prefix '{clean_dest_prefix}' (anti-loop protection)"
        )

    # 5. Payload size upper bound
    if size is not None and size > max_bytes:
        return f"Object size ({size} bytes) exceeds maximum allowable threshold ({max_bytes} bytes)"

    return None


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entry point for Topia to Equus Migration.

    Downloads source workbook, executes transformation engine, and uploads
    both the Equus import file and the mapping results report to S3.
    """
    dest_bucket = os.environ.get("DEST_BUCKET")
    if not dest_bucket:
        raise ValueError("Configuration error: DEST_BUCKET environment variable must be set.")

    dest_prefix = os.environ.get("DEST_PREFIX", "equus/")
    if not dest_prefix.endswith("/"):
        dest_prefix += "/"

    strategy = os.environ.get("ASSIGNMENT_STRATEGY", DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY)
    s3 = get_s3_client()

    targets = _extract_targets(event)
    results: list[dict[str, Any]] = []

    for bucket, key, size in targets:
        skip_reason = _accept_guard(bucket, key, size, dest_bucket, dest_prefix)
        if skip_reason:
            log.info("Skipping s3://%s/%s: %s", bucket, key, skip_reason)
            results.append(
                {
                    "source": f"s3://{bucket}/{key}",
                    "status": "SKIPPED",
                    "reason": skip_reason,
                }
            )
            continue

        log.info("Processing migration for s3://%s/%s", bucket, key)

        try:
            source_bytes = _read_s3_object(s3, bucket, key)
        except Exception as exc:
            log.error("Failed to download s3://%s/%s: %s", bucket, key, exc, exc_info=True)
            raise

        # Write to isolated temporary workspace for pipeline execution
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            stem = posixpath.splitext(posixpath.basename(key))[0]
            src_file_path = tmp_path / posixpath.basename(key)
            src_file_path.write_bytes(source_bytes)

            out_dir = tmp_path / "output"
            out_dir.mkdir(parents=True, exist_ok=True)

            tpl_path = BUNDLED_TEMPLATE if BUNDLED_TEMPLATE.exists() else None

            try:
                pipeline_result = run_equus_migration_pipeline(
                    source_path=src_file_path,
                    template_path=tpl_path,
                    output_dir=out_dir,
                    source_name=stem,
                    strategy=strategy,
                    overwrite=True,
                )
            except Exception as exc:
                log.error(
                    "Transformation pipeline failed for s3://%s/%s: %s",
                    bucket,
                    key,
                    exc,
                    exc_info=True,
                )
                raise

            generated_import = Path(pipeline_result["import_file"])
            generated_report = Path(pipeline_result["report_file"])

            if not generated_import.exists():
                raise FileNotFoundError(
                    f"Pipeline did not generate expected import file: {generated_import}"
                )
            if not generated_report.exists():
                raise FileNotFoundError(
                    f"Pipeline did not generate expected report file: {generated_report}"
                )

            # Prepare timestamped destination keys matching client specifications
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out_key = f"{dest_prefix}{stem}_EQUUS_{timestamp}.xlsx"
            report_key = f"{dest_prefix}reports/{stem}_MAPPING_REPORT_{timestamp}.xlsx"
            s3_metadata = {
                "source-bucket": bucket,
                "source-key": key[:1024],
                "migration-status": pipeline_result.get("status", "SUCCESS"),
            }

            try:
                log.info("Uploading Equus import to s3://%s/%s", dest_bucket, out_key)
                s3.put_object(
                    Bucket=dest_bucket,
                    Key=out_key,
                    Body=generated_import.read_bytes(),
                    ContentType=XLSX_CONTENT_TYPE,
                    Metadata=s3_metadata,
                )

                log.info("Uploading mapping report to s3://%s/%s", dest_bucket, report_key)
                s3.put_object(
                    Bucket=dest_bucket,
                    Key=report_key,
                    Body=generated_report.read_bytes(),
                    ContentType=XLSX_CONTENT_TYPE,
                    Metadata=s3_metadata,
                )
            except Exception as exc:
                log.error(
                    "Failed to upload destination outputs for s3://%s/%s: %s",
                    bucket,
                    key,
                    exc,
                    exc_info=True,
                )
                raise

            summary = {
                "source": f"s3://{bucket}/{key}",
                "output": f"s3://{dest_bucket}/{out_key}",
                "report": f"s3://{dest_bucket}/{report_key}",
                "status": "COMPLETED",
                "coverage_percentage": pipeline_result.get("coverage_percentage", 0.0),
                "total_source_rows": pipeline_result.get("total_source_rows", 0),
                "total_output_records": pipeline_result.get("total_output_records", 0),
                "warnings_count": pipeline_result.get("warnings_count", 0),
            }
            log.info("Migration successful: %s", json.dumps(summary))
            results.append(summary)

    return {"results": results}
