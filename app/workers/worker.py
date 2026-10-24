import asyncio
import os
from pathlib import Path

from app.core.config import settings
from app.repositories import MemoryRepository, MongoRepository
from app.schemas import JobStatus
from app.services.audit import audit
from app.services.preview import preview_direct_mappings
from app.services.profiling import profile_workbook


async def process_once(repo, worker_id: str) -> bool:
    job = await repo.claim_job(worker_id, max_attempts=settings.max_job_attempts)
    if not job:
        return False
    try:
        if job.get("cancellation_requested"):
            await repo.finish_job(job["job_id"], JobStatus.CANCELLED)
            await audit(repo, action="job.cancelled", entity_id=job["job_id"], job_id=job["job_id"])
            return True
        source = await repo.get_source(job["source_id"])
        if not source:
            await repo.finish_job(job["job_id"], JobStatus.FAILED, failure_code="SOURCE_NOT_FOUND")
            return True
        if job["kind"] == "profile":
            result = profile_workbook(Path(source["storage_path"]))
            current = await repo.get_job(job["job_id"])
            if current and current.get("cancellation_requested"):
                await repo.finish_job(job["job_id"], JobStatus.CANCELLED)
                await audit(
                    repo, action="job.cancelled", entity_id=job["job_id"], job_id=job["job_id"]
                )
                return True
            await repo.finish_job(
                job["job_id"],
                JobStatus.COMPLETED_WITH_ERRORS if result["issues"] else JobStatus.COMPLETED,
                result,
            )
            await audit(repo, action="job.completed", entity_id=job["job_id"], job_id=job["job_id"])
        elif job["kind"] == "preview":
            mappings = await repo.list_mappings(job["source_id"])
            result = preview_direct_mappings(Path(source["storage_path"]), mappings)
            result["mapping_id"] = job["mapping_id"]
            result["mapping_versions"] = {item["mapping_id"]: item["version"] for item in mappings}
            current = await repo.get_job(job["job_id"])
            if current and current.get("cancellation_requested"):
                await repo.finish_job(job["job_id"], JobStatus.CANCELLED)
                await audit(
                    repo, action="job.cancelled", entity_id=job["job_id"], job_id=job["job_id"]
                )
                return True
            await repo.finish_job(
                job["job_id"],
                JobStatus.COMPLETED_WITH_ERRORS
                if result["warnings"] or result["issues"]
                else JobStatus.COMPLETED,
                result,
            )
            await audit(
                repo,
                action="preview.completed",
                entity_id=job["job_id"],
                job_id=job["job_id"],
                metadata={"mapping_id": job["mapping_id"]},
            )
        elif job["kind"] == "equus_migration":
            from app.services.equus import (
                DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY,
                run_equus_migration_pipeline,
            )

            strategy = job.get("strategy") or DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY
            target = job.get("target") or settings.equus_target
            demo_writes = job.get("demo_writes_enabled")
            if demo_writes is None:
                demo_writes = settings.demo_writes_enabled

            result = run_equus_migration_pipeline(
                source_path=Path(source["storage_path"]),
                output_dir=settings.report_dir / "equus",
                source_name=source.get("original_filename", "").replace(".xlsx", "")
                or job["source_id"],
                strategy=strategy,
                target=target,
                demo_writes_enabled=demo_writes,
            )
            current = await repo.get_job(job["job_id"])
            if current and current.get("cancellation_requested"):
                await repo.finish_job(job["job_id"], JobStatus.CANCELLED)
                await audit(
                    repo, action="job.cancelled", entity_id=job["job_id"], job_id=job["job_id"]
                )
                return True
            recon = result.get("reconciliation", {})
            job_status = (
                JobStatus.COMPLETED
                if recon.get("is_valid") and not result.get("warnings_count")
                else (
                    JobStatus.COMPLETED_WITH_ERRORS if recon.get("is_valid") else JobStatus.FAILED
                )
            )
            await repo.finish_job(job["job_id"], job_status, result)
            await audit(
                repo,
                action="equus_migration.completed",
                entity_id=job["job_id"],
                job_id=job["job_id"],
                metadata={
                    "status": job_status,
                    "coverage": result.get("coverage_percentage"),
                    "import_file": result.get("import_file"),
                    "demo_writes_enabled": demo_writes,
                    "target": target,
                    "destination_status": result.get("execution_summary", {}).get(
                        "verification_status"
                    ),
                },
            )
        else:
            await repo.finish_job(job["job_id"], JobStatus.FAILED, failure_code="UNKNOWN_JOB_KIND")

    except Exception:
        await repo.finish_job(job["job_id"], JobStatus.FAILED, failure_code="WORKER_ERROR")
        await audit(
            repo,
            action="job.failed",
            entity_id=job["job_id"],
            job_id=job["job_id"],
            metadata={"failure_code": "WORKER_ERROR"},
        )
    return True


async def main() -> None:
    settings.validate_production()
    repo = MongoRepository(settings.mongodb_uri) if settings.mongodb_uri else MemoryRepository()
    if settings.is_production() and not await repo.health():
        raise RuntimeError("Worker cannot start: MongoDB is unreachable in production mode.")
    await repo.create_indexes()
    worker_id = os.getenv("HOSTNAME", "local-worker")
    try:
        while True:
            processed = await process_once(repo, worker_id)
            await asyncio.sleep(0.1 if processed else 2)
    finally:
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
