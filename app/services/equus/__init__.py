"""Shared Topia to Equus Migration Engine."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.equus.destination import (
    DestinationExecutionSummary,
    MockEquusDestination,
    get_mock_destination,
)
from app.services.equus.generator import (
    generate_equus_import_file,
    generate_mapping_report_file,
)
from app.services.equus.mapping_config import (
    DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
    STRATEGY_EMPLOYEE_NUMBER,
    STRATEGY_TOPIA_ID_WITH_FALLBACK,
)
from app.services.equus.parser import parse_three_row_workbook
from app.services.equus.reconciliation import reconcile_equus_transformation
from app.services.equus.transformer import transform_topia_to_equus

DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "templates" / "equus_template.xlsx"
)


def run_equus_migration_pipeline(
    source_path: Path | str,
    template_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    source_name: str | None = None,
    strategy: str = DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
    dependent_records: list[dict[str, Any]] | None = None,
    target: str = "mock",
    demo_writes_enabled: bool | None = None,
    destination_instance: MockEquusDestination | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Execute complete shared Topia-to-Equus migration pipeline.

    Parses multi-row header source, performs explicit transformations,
    executes against isolated mock destination (if demo_writes_enabled=True),
    generates Equus import artifact + mapping report, and verifies reconciliation.
    Can be invoked by both background worker and future AWS Lambda handlers.
    """
    src_file = Path(source_path)
    tpl_file = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    if output_dir:
        out_dir = Path(output_dir)
    else:
        try:
            from app.core.config import settings

            out_dir = settings.report_dir / "equus"
        except ImportError:
            out_dir = Path("data/reports/equus")
    base_name = source_name or src_file.stem
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # 1. Parse 3-row / 4-row header workbook
    parsed_sheet = parse_three_row_workbook(src_file)

    # 2. Transform into INSERT and UPDATE records
    transform_result = transform_topia_to_equus(
        parsed_sheet,
        tpl_file,
        strategy=strategy,
        dependent_records=dependent_records,
    )

    # 3. Reconcile and validate relational integrity
    recon_result = reconcile_equus_transformation(transform_result)

    # 4. Execute against isolated demo destination if enabled and reconciliation passed
    from app.core.config import settings


    should_demo_write = (
        settings.demo_writes_enabled if demo_writes_enabled is None else demo_writes_enabled
    )
    exec_summary: DestinationExecutionSummary | None = None

    # CRITICAL IMPORT SAFEGUARD: Destination writes are blocked if reconciliation failed
    if should_demo_write and recon_result.get("is_valid", False):
        dest = destination_instance or get_mock_destination()
        header_map = {m.eq_col_idx: m.eq_header for m in transform_result.mappings if m.eq_header}
        exec_summary = dest.execute_records(
            transform_result.all_output_records,
            header_map=header_map,
            run_id=f"run-{timestamp}",
            target=target,
            demo_writes_enabled=True,
        )

    # 5. Generate timestamped output artifacts
    import_file_path = out_dir / f"{base_name}_EQUUS_{timestamp}.xlsx"
    report_file_path = out_dir / "reports" / f"{base_name}_MAPPING_REPORT_{timestamp}.xlsx"

    generate_equus_import_file(
        tpl_file,
        transform_result.all_output_records,
        import_file_path,
        overwrite=overwrite,
    )
    generate_mapping_report_file(
        transform_result,
        base_name,
        report_file_path,
        exec_summary=exec_summary,
        overwrite=overwrite,
        recon_result=recon_result,
    )

    return {
        "source_name": base_name,
        "timestamp": timestamp,
        "strategy": strategy,
        "import_file": str(import_file_path),
        "report_file": str(report_file_path),
        "reconciliation": recon_result,
        "coverage_percentage": transform_result.coverage_percentage,
        "mapped_columns_count": transform_result.mapped_columns_count,
        "unmapped_columns_count": transform_result.unmapped_columns_count,
        "total_template_columns": 146,
        "total_source_rows": transform_result.total_evaluated_rows,
        "insert_records": len(transform_result.insert_records),
        "update_records": len(transform_result.update_records),
        "total_output_records": len(transform_result.all_output_records),
        "attempted_records": recon_result.get("attempted_records", len(transform_result.all_output_records)),
        "accepted_records": recon_result.get("accepted_records", 0),
        "rejected_records": recon_result.get("rejected_records", len(transform_result.all_output_records)),
        "warnings_count": len(transform_result.warnings),
        "status": recon_result["status"],
        "execution_summary": exec_summary.to_dict()
        if exec_summary
        else {
            "target": "none",
            "demo_writes_enabled": False,
            "status": "PLANNED_ONLY_SAFE_MODE" if not should_demo_write else "BLOCKED_RECONCILIATION_FAILED",
            "attempted": 0,
            "completed": 0,
        },
    }


__all__ = [
    "DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY",
    "DEFAULT_TEMPLATE_PATH",
    "DestinationExecutionSummary",
    "MockEquusDestination",
    "STRATEGY_EMPLOYEE_NUMBER",
    "STRATEGY_TOPIA_ID_WITH_FALLBACK",
    "generate_equus_import_file",
    "generate_mapping_report_file",
    "get_mock_destination",
    "parse_three_row_workbook",
    "reconcile_equus_transformation",
    "run_equus_migration_pipeline",
    "transform_topia_to_equus",
]
