"""Standalone Local Migration Runner for Topia -> Equus.

Executes the migration engine directly from the command line against local folders
standing in for S3 buckets without requiring Docker, MongoDB, FastAPI, or workers.

Folder layout:
  Input:  local_s3/source_s3/topia/incoming/*.xlsx
  Output: local_s3/dest_s3/equus/<name>_EQUUS_<timestamp>.xlsx
  Report: local_s3/dest_s3/equus/reports/<name>_MAPPING_REPORT_<timestamp>.xlsx

Usage:
  python local/run_local.py                           # Batch: all in incoming/
  python local/run_local.py "topia/incoming/x.xlsx"   # Single file relative to source_s3/
  python local/run_local.py path/to/export.xlsx       # Single file relative or absolute
  python local/run_local.py --strategy EMPLOYEE_NUMBER
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.equus import (  # noqa: E402
    DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
    DEFAULT_TEMPLATE_PATH,
    STRATEGY_EMPLOYEE_NUMBER,
    STRATEGY_TOPIA_ID_WITH_FALLBACK,
    run_equus_migration_pipeline,
)

DEFAULT_SOURCE_DIR = PROJECT_ROOT / "local_s3" / "source_s3" / "topia" / "incoming"
DEFAULT_SOURCE_BUCKET = PROJECT_ROOT / "local_s3" / "source_s3"
DEFAULT_DEST_DIR = PROJECT_ROOT / "local_s3" / "dest_s3" / "equus"


def resolve_single_file(file_arg: str, source_dir: Path, source_bucket: Path) -> Path:
    """Resolve a single input file argument to an existing file path."""
    p = Path(file_arg)

    # 1. Direct path (absolute or relative to CWD)
    if p.exists() and p.is_file():
        return p.resolve()

    # 2. Relative to source_bucket (e.g. "topia/incoming/export.xlsx")
    candidate_bucket = (source_bucket / file_arg).resolve()
    if candidate_bucket.exists() and candidate_bucket.is_file():
        return candidate_bucket

    # 3. Relative to incoming source_dir (e.g. "export.xlsx")
    candidate_incoming = (source_dir / file_arg).resolve()
    if candidate_incoming.exists() and candidate_incoming.is_file():
        return candidate_incoming

    raise FileNotFoundError(f"Specified input file not found: '{file_arg}'")


def process_file(
    file_path: Path,
    dest_dir: Path,
    template_path: Path,
    strategy: str,
) -> dict[str, Any]:
    """Execute pipeline for a single file and return status dictionary."""
    print("=" * 80)
    print(f"PROCESSING FILE: {file_path.name}")
    print(f"Source Path:     {file_path}")
    print(f"Strategy:        {strategy}")
    print("=" * 80)

    try:
        # Validate extension
        if file_path.suffix.lower() != ".xlsx":
            raise ValueError(f"Unsupported file format '{file_path.suffix}'; expected '.xlsx'")

        # Execute shared engine with overwrite protection
        result = run_equus_migration_pipeline(
            source_path=file_path,
            template_path=template_path,
            output_dir=dest_dir,
            source_name=file_path.stem,
            strategy=strategy,
            overwrite=False,
        )

        recon = result.get("reconciliation", {})
        is_valid = recon.get("is_valid", False)
        status = result.get("status", "UNKNOWN")
        errors = recon.get("errors", [])
        warnings = recon.get("warnings", [])
        coverage = result.get("coverage_percentage", 0.0)

        print(f"Reconciliation:  {'PASSED' if is_valid else 'FAILED'} (Status: {status})")
        print(f"Column Coverage: {coverage:.2f}%")
        print(
            f"Output Records:  {result.get('total_output_records', 0)} total "
            f"({result.get('insert_records', 0)} INSERT, {result.get('update_records', 0)} UPDATE)"
        )
        print(f"Equus Workbook:  {result.get('import_file')}")
        print(f"Mapping Report:  {result.get('report_file')}")

        if errors:
            print(f"\n[!] Reconciliation Errors ({len(errors)}):")
            for err in errors:
                print(f"    - {err}")

        if warnings:
            print(f"\n[*] Warnings ({len(warnings)}):")
            for warn in warnings:
                print(f"    - {warn}")

        return {
            "file": str(file_path),
            "success": is_valid,
            "status": status,
            "result": result,
            "error": None,
        }

    except FileExistsError as exc:
        print(f"[!] Error: Output collision detected: {exc}")
        return {
            "file": str(file_path),
            "success": False,
            "status": "FILE_EXISTS_ERROR",
            "result": None,
            "error": str(exc),
        }
    except Exception as exc:
        print(f"[!] Error processing '{file_path.name}': {exc}")
        return {
            "file": str(file_path),
            "success": False,
            "status": "EXECUTION_ERROR",
            "result": None,
            "error": str(exc),
        }


def main(argv: list[str] | None = None) -> int:
    """CLI Entry point for local migration runner."""
    parser = argparse.ArgumentParser(
        description="Run Topia-to-Equus migration locally without Docker or MongoDB."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Optional single file to process. If omitted, processes all in incoming/.",
    )
    parser.add_argument(
        "--strategy",
        choices=[STRATEGY_EMPLOYEE_NUMBER, STRATEGY_TOPIA_ID_WITH_FALLBACK],
        default=DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
        help=f"Assignment Identifier strategy (default: {DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY}).",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Directory for incoming files (default: {DEFAULT_SOURCE_DIR}).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=DEFAULT_DEST_DIR,
        help=f"Directory for generated Equus files (default: {DEFAULT_DEST_DIR}).",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE_PATH,
        help=f"Path to Equus Excel template (default: {DEFAULT_TEMPLATE_PATH}).",
    )

    args = parser.parse_args(argv)

    dest_dir = args.dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "reports").mkdir(parents=True, exist_ok=True)

    template_path = args.template.resolve()
    if not template_path.exists():
        print(f"[!] Equus template not found: {template_path}", file=sys.stderr)
        return 1

    files_to_process: list[Path] = []

    # Mode 1: Single file specified
    if args.file:
        try:
            resolved = resolve_single_file(args.file, args.source_dir, DEFAULT_SOURCE_BUCKET)
            if resolved.name.startswith("~$"):
                print(f"[!] Skipping Excel temporary file: {resolved.name}")
                return 0
            files_to_process.append(resolved)
        except Exception as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
    else:
        # Mode 2: Batch directory scan
        source_dir = args.source_dir.resolve()
        if not source_dir.exists():
            print(f"[!] Source incoming directory not found: {source_dir}", file=sys.stderr)
            print("    Please create the directory and place your .xlsx files there:")
            print(f"      mkdir -p {args.source_dir}")
            return 1

        for p in sorted(source_dir.glob("*.xlsx")):
            # Skip Excel temporary lock files
            if p.name.startswith("~$"):
                print(f"[*] Skipping temporary file: {p.name}")
                continue
            files_to_process.append(p)

        if not files_to_process:
            print(f"[*] No .xlsx files found in {source_dir}. Nothing to process.")
            return 0

    print(f"\nStarting local migration run ({len(files_to_process)} file(s) to process)...\n")

    results: list[dict[str, Any]] = []
    for fp in files_to_process:
        res = process_file(fp, dest_dir, template_path, args.strategy)
        results.append(res)
        print()

    # Summary
    success_count = sum(1 for r in results if r["success"])
    failure_count = len(results) - success_count

    print("=" * 80)
    print("MIGRATION RUN SUMMARY")
    print("=" * 80)
    print(f"Total Files Processed: {len(results)}")
    print(f"Successful:            {success_count}")
    print(f"Failed:                {failure_count}")

    if failure_count > 0:
        print("\nFailed Files:")
        for r in results:
            if not r["success"]:
                err_msg = r["error"] or f"Status: {r['status']}"
                print(f"  - {Path(r['file']).name}: {err_msg}")

    print("=" * 80)
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
