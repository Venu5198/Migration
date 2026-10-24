from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import repository
from app.core.config import settings
from app.core.security import current_actor
from app.schemas import JobResponse, JobStatus, PagedJobs
from app.services.audit import audit
from app.services.reconciliation import reconcile_preview
from app.services.reporting import preview_csv

router = APIRouter(prefix="/api/v1", tags=["jobs"], dependencies=[Depends(current_actor)])


class JobCreate(BaseModel):
    source_id: str


class PreviewCreate(JobCreate):
    mapping_id: str


class EquusMigrationCreate(BaseModel):
    strategy: str | None = None
    target: str | None = None
    demo_writes_enabled: bool | None = None


def _sanitize_job_for_client(job: dict | None) -> dict | None:
    """Strip internal local filesystem paths from job result before serialization."""
    if not job:
        return job
    safe_job = dict(job)
    if safe_job.get("result") and isinstance(safe_job["result"], dict):
        safe_result = dict(safe_job["result"])
        from pathlib import Path

        for key in ("import_file", "report_file"):
            if key in safe_result and safe_result[key]:
                safe_result[key] = Path(safe_result[key]).name
        safe_job["result"] = safe_result
    return safe_job


async def _create(
    kind: str,
    payload: JobCreate,
    repo,
    actor: str = "system",
    extra: dict | None = None,
) -> dict:
    source = await repo.get_source(payload.source_id)
    if not source:
        raise HTTPException(
            404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source was not found."}
        )
    now = datetime.now(UTC)
    job = {
        "job_id": str(uuid4()),
        "kind": kind,
        "source_id": payload.source_id,
        "source_filename": source.get("original_filename"),
        "status": JobStatus.PENDING,
        "progress": 0,
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "failure_code": None,
        "cancellation_requested": False,
    }
    if extra:
        job.update(extra)
    if isinstance(payload, PreviewCreate):
        mapping = await repo.get_mapping(payload.mapping_id)
        if not mapping or mapping["source_id"] != payload.source_id:
            raise HTTPException(
                404, detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping was not found."}
            )
        job["mapping_id"] = payload.mapping_id
    await repo.put_job(job)
    await audit(
        repo,
        action="job.created",
        entity_id=job["job_id"],
        job_id=job["job_id"],
        actor=actor,
        metadata={"kind": kind, "source_id": payload.source_id},
    )
    return job


@router.post(
    "/sources/{source_id}/profile", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED
)
async def queue_profile(source_id: str, repo=Depends(repository), actor=Depends(current_actor)):
    return await _create("profile", JobCreate(source_id=source_id), repo, actor.subject)


@router.post(
    "/migrations/preview", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED
)
async def queue_preview(
    payload: PreviewCreate, repo=Depends(repository), actor=Depends(current_actor)
):
    return await _create("preview", payload, repo, actor.subject)


@router.post(
    "/sources/{source_id}/equus-migration",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_equus_migration(
    source_id: str,
    payload: EquusMigrationCreate | None = None,
    strategy: str | None = None,
    repo=Depends(repository),
    actor=Depends(current_actor),
):
    from app.core.config import settings
    from app.services.equus import DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY

    chosen_strategy = (
        (payload.strategy if payload and payload.strategy else None)
        or strategy
        or DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY
    )
    chosen_target = (payload.target if payload and payload.target else None) or settings.equus_target
    chosen_demo_writes = (
        payload.demo_writes_enabled
        if payload and payload.demo_writes_enabled is not None
        else settings.demo_writes_enabled
    )

    # Fail closed on invalid target or live writes
    try:
        settings.validate_equus_destination(target=chosen_target, demo_writes=chosen_demo_writes)
    except PermissionError as pe:
        raise HTTPException(
            403, detail={"code": "LIVE_WRITES_DISABLED", "message": str(pe)}
        )
    except ValueError as ve:
        raise HTTPException(
            422, detail={"code": "INVALID_DEMO_TARGET", "message": str(ve)}
        )

    return await _create(
        "equus_migration",
        JobCreate(source_id=source_id),
        repo,
        actor.subject,
        extra={
            "strategy": chosen_strategy,
            "target": chosen_target,
            "demo_writes_enabled": chosen_demo_writes,
        },
    )


@router.get("/jobs", response_model=PagedJobs)
async def list_jobs(
    kind: str | None = None,
    source_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
    repo=Depends(repository),
):
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_PAGINATION",
                "message": "page >= 1 and page_size 1..100 required.",
            },
        )
    jobs = await repo.list_jobs(kind=kind, source_id=source_id)
    start = (page - 1) * page_size
    items = [_sanitize_job_for_client(j) for j in jobs[start : start + page_size]]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": len(jobs),
    }


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, repo=Depends(repository)):
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "Job was not found."})
    return _sanitize_job_for_client(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str, repo=Depends(repository), actor=Depends(current_actor)):
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "Job was not found."})
    if job["status"] in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS, JobStatus.FAILED}:
        raise HTTPException(
            409, detail={"code": "JOB_TERMINAL", "message": "Terminal jobs cannot cancel."}
        )
    await repo.request_cancel(job_id)
    await audit(
        repo, action="job.cancel_requested", entity_id=job_id, job_id=job_id, actor=actor.subject
    )
    return _sanitize_job_for_client(await repo.get_job(job_id))


@router.get("/reports/{job_id}/export")
async def export_report(
    job_id: str,
    artifact: str = "report",
    repo=Depends(repository),
    actor=Depends(current_actor),
):
    job = await repo.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(
            404, detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found."}
        )

    # Equus Migration Excel Artifacts (Report or Import File)
    if job.get("kind") == "equus_migration":
        from pathlib import Path

        if artifact not in {"report", "import"}:
            raise HTTPException(
                400,
                detail={
                    "code": "INVALID_ARTIFACT",
                    "message": f"Artifact '{artifact}' is not supported. Use 'report' or 'import'.",
                },
            )

        file_key = "report_file" if artifact == "report" else "import_file"
        file_path_str = job["result"].get(file_key)
        if not file_path_str:
            raise HTTPException(
                404,
                detail={
                    "code": "ARTIFACT_NOT_FOUND",
                    "message": f"Artifact '{file_key}' was not found in job results.",
                },
            )
        file_path = Path(file_path_str).resolve()
        if not file_path.exists():
            raise HTTPException(
                404,
                detail={
                    "code": "ARTIFACT_NOT_FOUND",
                    "message": f"Artifact file '{file_key}' does not exist on disk.",
                },
            )

        # Enforce authorized directory boundary to prevent path traversal
        try:
            file_path.relative_to(settings.report_dir.resolve())
        except ValueError as exc:
            raise HTTPException(
                403,
                detail={
                    "code": "ACCESS_DENIED",
                    "message": "Artifact path is outside authorized report directory.",
                },
            ) from exc

        content = file_path.read_bytes()

        # Check if job reconciliation failed
        is_recon_failed = False


        if job.get("kind") == "equus_migration":
            recon = (job.get("result", {}) or {}).get("reconciliation", {})
            if recon.get("status") == "FAILED" or recon.get("is_valid") is False:
                is_recon_failed = True

        out_headers: dict[str, str] = {}
        download_filename = file_path.name
        if is_recon_failed and artifact == "import":
            out_headers["X-Equus-Diagnostic-Only"] = "true"
            if not download_filename.startswith("DIAGNOSTIC_ONLY_"):
                download_filename = f"DIAGNOSTIC_ONLY_{download_filename}"

        out_headers["Content-Disposition"] = f'attachment; filename="{download_filename}"'

        await audit(
            repo,
            action="report.exported",
            entity_id=job_id,
            job_id=job_id,
            actor=actor.subject,
            metadata={
                "artifact": artifact,
                "filename": download_filename,
                "diagnostic_only": is_recon_failed and artifact == "import",
            },
        )
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=out_headers,
        )


    report_id = str(uuid4())
    source = await repo.get_source(job["source_id"])
    workbook_digest = source["sha256"] if source else "UNKNOWN"
    await repo.put_report(
        {
            "report_id": report_id,
            "job_id": job_id,
            "report_type": "preview_csv",
            "generated_at": datetime.now(UTC),
            "workbook_digest": workbook_digest,
            "mapping_id": job.get("mapping_id"),
            "mapping_versions": job["result"].get("mapping_versions", {}),
        }
    )
    await audit(
        repo,
        action="report.exported",
        entity_id=report_id,
        job_id=job_id,
        actor=actor.subject,
        metadata={"report_type": "preview_csv", "mapping_id": job.get("mapping_id")},
    )
    return Response(
        preview_csv(job["result"]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="migration-{job_id}.csv"'},
    )


@router.get("/reports/{job_id}/reconciliation")
async def reconciliation(job_id: str, repo=Depends(repository), actor=Depends(current_actor)):
    job = await repo.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(
            404, detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found."}
        )
    await audit(
        repo,
        action="report.reconciliation_accessed",
        entity_id=job_id,
        job_id=job_id,
        actor=actor.subject,
    )
    if job.get("kind") == "equus_migration":
        return job["result"].get("reconciliation", {})

    return reconcile_preview(job["result"])


@router.get("/targets/mock/test-connection")
async def test_mock_target():
    from app.connectors import MockConnector

    return await MockConnector().test_connection()
