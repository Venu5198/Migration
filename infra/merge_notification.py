"""S3 Bucket Notification Merger for Topia-to-Equus Migration.

Safely merges the migration Lambda notification filter into an existing S3 bucket
notification configuration without clobbering existing SQS, SNS, EventBridge,
or unrelated Lambda triggers.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("equus.infra.merge")


def parse_notification_config(raw_config: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse and normalize raw bucket notification configuration from AWS CLI or API."""
    if not raw_config:
        return {}
    if isinstance(raw_config, dict):
        return dict(raw_config)
    if isinstance(raw_config, str):
        trimmed = raw_config.strip()
        if not trimmed:
            return {}
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse current S3 notification JSON: {exc}") from exc
    raise TypeError(f"Expected dict, str, or None; got {type(raw_config).__name__}")


def load_filter_template(filter_source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Load filter template from JSON string, dict, or file path."""
    if isinstance(filter_source, dict):
        return json.loads(json.dumps(filter_source))
    if isinstance(filter_source, (str, Path)):
        p = Path(filter_source)
        if p.exists() and p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        try:
            return json.loads(str(filter_source))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse filter template: {exc}") from exc
    raise TypeError(f"Invalid filter source type: {type(filter_source).__name__}")


def detect_conflicting_notifications(
    existing_lambdas: list[dict[str, Any]],
    new_prefix: str,
    target_id: str,
) -> list[str]:
    """Check for existing Lambda notifications that overlap on the same prefix."""
    conflicts: list[str] = []
    clean_target = new_prefix.rstrip("/")
    for rule in existing_lambdas:
        if rule.get("Id") == target_id:
            continue
        filter_rules = rule.get("Filter", {}).get("Key", {}).get("FilterRules", [])
        for fr in filter_rules:
            if fr.get("Name") == "prefix":
                rule_prefix = fr.get("Value", "").rstrip("/")
                if rule_prefix == clean_target:
                    conflicts.append(
                        f"Overlapping prefix '{rule_prefix}' in existing "
                        f"Lambda rule Id: '{rule.get('Id')}'"
                    )
    return conflicts


def merge_s3_notifications(
    current_config: str | dict[str, Any] | None,
    filter_template: str | Path | dict[str, Any],
    function_arn: str,
    source_prefix: str = "topia/incoming/",
    detect_conflicts: bool = True,
) -> dict[str, Any]:
    """Idempotently merge new Lambda notification into existing bucket configuration.

    - Preserves QueueConfigurations (SQS)
    - Preserves TopicConfigurations (SNS)
    - Preserves EventBridgeConfiguration
    - Preserves unrelated LambdaFunctionConfigurations
    - Replaces previous entry with matching Id (idempotent update)
    """
    if not function_arn or not function_arn.strip():
        raise ValueError("function_arn must be a non-empty string.")

    cfg = parse_notification_config(current_config)
    new_rule = load_filter_template(filter_template)

    new_rule["LambdaFunctionArn"] = function_arn.strip()
    target_id = new_rule.get("Id", "topia-to-equus-migration")

    # Update prefix filter rule
    for rule in new_rule.get("Filter", {}).get("Key", {}).get("FilterRules", []):
        if rule.get("Name") == "prefix":
            rule["Value"] = source_prefix

    existing_lambdas = cfg.get("LambdaFunctionConfigurations", [])
    if detect_conflicts:
        overlaps = detect_conflicting_notifications(existing_lambdas, source_prefix, target_id)
        if overlaps:
            log.warning("Detected potential notification prefix overlaps: %s", overlaps)

    # Retain all unrelated Lambda rules; replace matching target_id rule
    retained_lambdas = [c for c in existing_lambdas if c.get("Id") != target_id]
    retained_lambdas.append(new_rule)

    result = dict(cfg)
    result["LambdaFunctionConfigurations"] = retained_lambdas

    # Strip AWS metadata keys if present from raw AWS CLI responses
    result.pop("ResponseMetadata", None)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge S3 bucket notifications safely.")
    parser.add_argument(
        "--current-json", default="{}", help="Existing notification JSON from s3api"
    )
    parser.add_argument("--filter-file", required=True, help="Path to s3-notification-filter.json")
    parser.add_argument("--arn", required=True, help="Lambda Function ARN to attach")
    parser.add_argument("--prefix", default="topia/incoming/", help="Source S3 prefix")

    args = parser.parse_args()

    try:
        merged = merge_s3_notifications(
            current_config=args.current_json,
            filter_template=args.filter_file,
            function_arn=args.arn,
            source_prefix=args.prefix,
        )
        print(json.dumps(merged, indent=2))
    except Exception as exc:
        print(f"Error merging notifications: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
