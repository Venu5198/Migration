def reconcile_preview(preview: dict, target_records: list[dict] | None = None) -> dict:
    """Reconcile only source/preview unless a connector supplies readable target records."""
    issues = preview.get("issues", [])
    result = {
        "source_records": preview.get("records_evaluated", 0),
        "header_rows_count": preview.get("header_rows_count", 1),
        "accepted_records": preview.get("eligible_records", 0) - preview.get("rejected_records", 0),
        "rejected_records": preview.get("rejected_records", 0),
        "warning_count": len(preview.get("warnings", [])),
        "target_reconciliation": "NOT_PERFORMED",
    }
    if target_records is not None:
        result["target_reconciliation"] = "AVAILABLE_FOR_CONNECTOR_COMPARISON"
        result["target_record_count"] = len(target_records)
    result["issue_count"] = len(issues)
    return result
