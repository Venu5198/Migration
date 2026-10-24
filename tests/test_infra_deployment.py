"""Automated local regression tests for AWS deployment infrastructure.

Validates S3 notification filter specifications, safe notification merging,
idempotency, conflicting rule detection, bucket policy TLS enforcement,
and parameter guards without requiring AWS credentials or live cloud resources.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INFRA_DIR = PROJECT_ROOT / "infra"
FILTER_FILE = INFRA_DIR / "s3-notification-filter.json"
POLICY_FILE = INFRA_DIR / "source-bucket-policy.json"
MERGE_SCRIPT = INFRA_DIR / "merge_notification.py"

# Add infra directory to sys.path so merge_notification is importable
if str(INFRA_DIR) not in sys.path:
    sys.path.insert(0, str(INFRA_DIR))

import merge_notification  # noqa: E402


def test_notification_filter_structure_and_values():
    """Verify that the committed filter JSON conforms exactly to client expectations."""
    assert FILTER_FILE.exists(), "infra/s3-notification-filter.json must exist"
    data = json.loads(FILTER_FILE.read_text(encoding="utf-8"))

    assert data["Id"] == "topia-to-equus-migration"
    assert data["Events"] == ["s3:ObjectCreated:*"]

    filter_rules = data["Filter"]["Key"]["FilterRules"]
    rule_map = {r["Name"]: r["Value"] for r in filter_rules}

    assert rule_map.get("prefix") == "topia/incoming/"
    assert rule_map.get("suffix") == ".xlsx"


def test_merge_into_empty_configuration():
    """Verify that merging into an empty or newly provisioned bucket configuration works cleanly."""
    function_arn = "arn:aws:lambda:us-east-1:123456789012:function:topia-equus-migration"
    merged = merge_notification.merge_s3_notifications(
        current_config="{}",
        filter_template=FILTER_FILE,
        function_arn=function_arn,
        source_prefix="topia/incoming/",
    )

    assert "LambdaFunctionConfigurations" in merged
    lambdas = merged["LambdaFunctionConfigurations"]
    assert len(lambdas) == 1
    assert lambdas[0]["Id"] == "topia-to-equus-migration"
    assert lambdas[0]["LambdaFunctionArn"] == function_arn

    rules = {r["Name"]: r["Value"] for r in lambdas[0]["Filter"]["Key"]["FilterRules"]}
    assert rules["prefix"] == "topia/incoming/"
    assert rules["suffix"] == ".xlsx"


def test_merge_preserves_unrelated_notifications():
    """Verify that existing SQS, SNS, EventBridge, and unrelated Lambda triggers are strictly preserved."""
    function_arn = "arn:aws:lambda:us-east-1:123456789012:function:topia-equus-migration"
    existing_config = {
        "QueueConfigurations": [
            {
                "Id": "client-audit-sqs",
                "QueueArn": "arn:aws:sqs:us-east-1:123456789012:audit-events",
                "Events": ["s3:ObjectCreated:*"],
            }
        ],
        "TopicConfigurations": [
            {
                "Id": "client-ops-sns",
                "TopicArn": "arn:aws:sns:us-east-1:123456789012:ops-alerts",
                "Events": ["s3:ObjectRemoved:*"],
            }
        ],
        "EventBridgeConfiguration": {
            "EventBridgeEnabled": True,
        },
        "LambdaFunctionConfigurations": [
            {
                "Id": "unrelated-virus-scanner",
                "LambdaFunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:antivirus",
                "Events": ["s3:ObjectCreated:*"],
                "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/"}]}},
            }
        ],
        "ResponseMetadata": {"HTTPStatusCode": 200},  # Mock AWS CLI wrapper response
    }

    merged = merge_notification.merge_s3_notifications(
        current_config=existing_config,
        filter_template=FILTER_FILE,
        function_arn=function_arn,
        source_prefix="topia/incoming/",
    )

    # 1. Unrelated non-Lambda configs are preserved intact
    assert len(merged["QueueConfigurations"]) == 1
    assert merged["QueueConfigurations"][0]["Id"] == "client-audit-sqs"
    assert len(merged["TopicConfigurations"]) == 1
    assert merged["TopicConfigurations"][0]["Id"] == "client-ops-sns"
    assert merged["EventBridgeConfiguration"]["EventBridgeEnabled"] is True

    # 2. Both Lambda configurations exist in the merged output
    lambdas = merged["LambdaFunctionConfigurations"]
    assert len(lambdas) == 2
    lambda_ids = [l["Id"] for l in lambdas]
    assert "unrelated-virus-scanner" in lambda_ids
    assert "topia-to-equus-migration" in lambda_ids

    # 3. AWS ResponseMetadata stripped from PUT payload
    assert "ResponseMetadata" not in merged


def test_merge_is_strictly_idempotent():
    """Verify that running the merger multiple times never creates duplicate notification rules."""
    function_arn = "arn:aws:lambda:us-east-1:123456789012:function:topia-equus-migration"
    first_merge = merge_notification.merge_s3_notifications(
        current_config="{}",
        filter_template=FILTER_FILE,
        function_arn=function_arn,
        source_prefix="topia/incoming/",
    )
    assert len(first_merge["LambdaFunctionConfigurations"]) == 1

    # Second merge passing the result of the first merge
    second_merge = merge_notification.merge_s3_notifications(
        current_config=first_merge,
        filter_template=FILTER_FILE,
        function_arn=function_arn,
        source_prefix="topia/incoming/",
    )
    assert len(second_merge["LambdaFunctionConfigurations"]) == 1
    assert first_merge == second_merge


def test_merge_updates_arn_and_prefix_in_place():
    """Verify that re-deploying to a new ARN or prefix updates the existing rule cleanly."""
    initial_config = {
        "LambdaFunctionConfigurations": [
            {
                "Id": "topia-to-equus-migration",
                "LambdaFunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:old-version",
                "Events": ["s3:ObjectCreated:*"],
                "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "old/prefix/"}]}},
            }
        ]
    }
    new_arn = "arn:aws:lambda:us-east-1:123456789012:function:new-version"
    updated = merge_notification.merge_s3_notifications(
        current_config=initial_config,
        filter_template=FILTER_FILE,
        function_arn=new_arn,
        source_prefix="topia/incoming/",
    )

    lambdas = updated["LambdaFunctionConfigurations"]
    assert len(lambdas) == 1
    assert lambdas[0]["LambdaFunctionArn"] == new_arn
    rules = {r["Name"]: r["Value"] for r in lambdas[0]["Filter"]["Key"]["FilterRules"]}
    assert rules["prefix"] == "topia/incoming/"


def test_merge_detects_conflicting_overlapping_rules():
    """Verify conflict detection when an unrelated existing rule shares the same prefix."""
    existing_lambdas = [
        {
            "Id": "conflicting-third-party-tool",
            "LambdaFunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:other-processor",
            "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "topia/incoming"}]}},
        }
    ]
    conflicts = merge_notification.detect_conflicting_notifications(
        existing_lambdas,
        new_prefix="topia/incoming/",
        target_id="topia-to-equus-migration",
    )
    assert len(conflicts) == 1
    assert "conflicting-third-party-tool" in conflicts[0]


def test_merge_cli_execution_with_subprocess():
    """Verify that merge_notification.py executes reliably via CLI entry point."""
    function_arn = "arn:aws:lambda:us-east-1:123456789012:function:topia-equus-migration"
    cmd = [
        sys.executable,
        str(MERGE_SCRIPT),
        "--current-json",
        json.dumps({"QueueConfigurations": [{"Id": "q1"}]}),
        "--filter-file",
        str(FILTER_FILE),
        "--arn",
        function_arn,
        "--prefix",
        "topia/incoming/",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert proc.returncode == 0
    parsed = json.loads(proc.stdout)
    assert "QueueConfigurations" in parsed
    assert "LambdaFunctionConfigurations" in parsed
    assert parsed["LambdaFunctionConfigurations"][0]["LambdaFunctionArn"] == function_arn


def test_bucket_policy_tls_enforcement_structure():
    """Verify that source-bucket-policy.json enforces TLS and contains required safety conditions."""
    assert POLICY_FILE.exists(), "infra/source-bucket-policy.json must exist"
    policy_data = json.loads(POLICY_FILE.read_text(encoding="utf-8"))

    statements = policy_data["Statement"]
    tls_statement = next((s for s in statements if s.get("Sid") == "DenyInsecureTransport"), None)
    assert tls_statement is not None, "Policy must contain DenyInsecureTransport statement"
    assert tls_statement["Effect"] == "Deny"
    assert tls_statement["Action"] == "s3:*"
    assert tls_statement["Condition"]["Bool"]["aws:SecureTransport"] == "false"
    assert "arn:aws:s3:::__SOURCE_BUCKET__" in tls_statement["Resource"]


def test_deploy_script_structure_and_guards():
    """Verify that infra/deploy.sh includes essential safety guards and parameter validations."""
    deploy_sh = INFRA_DIR / "deploy.sh"
    assert deploy_sh.exists(), "infra/deploy.sh must exist"
    script_text = deploy_sh.read_text(encoding="utf-8")

    # 1. Parameter presence guard
    assert "$# -lt 2" in script_text, "deploy.sh must check for required bucket arguments"

    # 2. Tool prerequisite checks
    assert "aws sam" in script_text, "deploy.sh must check for aws and sam CLI tools"

    # 3. Anti-loop check
    assert 'DEST_PREFIX" == "$SRC_PREFIX"*' in script_text, "deploy.sh must verify anti-loop guard"

    # 4. Safe notification merger invocation
    assert "merge_notification.py" in script_text, "deploy.sh must invoke safe notification merger"
