"""Shared Topia to Equus Migration Engine."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.equus.generator import (
    generate_equus_import_file,
    generate_mapping_report_file,
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
) -> dict[str, Any]:
    """Execute complete shared Topia-to-Equus migration pipeline.

    Parses multi-row header source, performs explicit transformations,
    generates Equus import artifact + mapping report, and verifies reconciliation.
    Can be invoked by both background worker and future AWS Lambda handlers.
    """
    src_file = Path(source_path)
    tpl_file = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    out_dir = Path(output_dir) if output_dir else settings.report_dir / "equus"
    base_name = source_name or src_file.stem
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # 1. Parse 3-row / 4-row header workbook
    parsed_sheet = parse_three_row_workbook(src_file)

    # 2. Transform into INSERT and UPDATE records
    transform_result = transform_topia_to_equus(parsed_sheet, tpl_file)

    # 3. Reconcile and validate relational integrity
    recon_result = reconcile_equus_transformation(transform_result)

    # 4. Generate timestamped output artifacts
    import_file_path = out_dir / f"{base_name}_EQUUS_{timestamp}.xlsx"
    report_file_path = out_dir / "reports" / f"{base_name}_MAPPING_REPORT_{timestamp}.xlsx"

    generate_equus_import_file(tpl_file, transform_result.all_output_records, import_file_path)
    generate_mapping_report_file(transform_result, base_name, report_file_path)

    return {
        "source_name": base_name,
        "timestamp": timestamp,
        "import_file": str(import_file_path),
        "report_file": str(report_file_path),
        "reconciliation": recon_result,
        "coverage_percentage": transform_result.coverage_percentage,
        "total_source_rows": transform_result.total_evaluated_rows,
        "insert_records": len(transform_result.insert_records),
        "update_records": len(transform_result.update_records),
        "total_output_records": len(transform_result.all_output_records),
        "warnings_count": len(transform_result.warnings),
        "status": recon_result["status"],
    }


__all__ = [
    "DEFAULT_TEMPLATE_PATH",
    "generate_equus_import_file",
    "generate_mapping_report_file",
    "parse_three_row_workbook",
    "reconcile_equus_transformation",
    "run_equus_migration_pipeline",
    "transform_topia_to_equus",
]
