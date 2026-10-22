from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import repository
from app.core.security import current_actor
from app.schemas import JobResponse, JobStatus
from app.services.audit import audit
from app.services.reconciliation import reconcile_preview
from app.services.reporting import preview_csv

router = APIRouter(prefix="/api/v1", tags=["jobs"], dependencies=[Depends(current_actor)])


class JobCreate(BaseModel):
    source_id: str


class PreviewCreate(JobCreate):
    mapping_id: str


async def _create(kind: str, payload: JobCreate, repo, actor: str = "system") -> dict:
    if not await repo.get_source(payload.source_id):
        raise HTTPException(
            404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source was not found."}
        )
    now = datetime.now(UTC)
    job = {
        "job_id": str(uuid4()),
        "kind": kind,
        "source_id": payload.source_id,
        "status": JobStatus.PENDING,
        "progress": 0,
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "failure_code": None,
        "cancellation_requested": False,
    }
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


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, repo=Depends(repository)):
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "Job was not found."})
    return job


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
    return await repo.get_job(job_id)


@router.get("/reports/{job_id}/export")
async def export_report(job_id: str, repo=Depends(repository), actor=Depends(current_actor)):
    job = await repo.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(
            404, detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found."}
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
    return reconcile_preview(job["result"])


@router.get("/targets/mock/test-connection")
async def test_mock_target():
    from app.connectors import MockConnector

    return await MockConnector().test_connection()
