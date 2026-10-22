from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import repository
from app.core.config import settings
from app.core.security import current_actor
from app.schemas import SourceResponse
from app.services.audit import audit
from app.services.workbooks import inspect_workbook, save_workbook, validate_excel_upload

router = APIRouter(
    prefix="/api/v1/sources", tags=["sources"], dependencies=[Depends(current_actor)]
)


@router.post("/upload", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_source(
    file: UploadFile = File(...), repo=Depends(repository), actor=Depends(current_actor)
):
    if not file.filename:
        raise HTTPException(
            400, detail={"code": "MISSING_FILENAME", "message": "A filename is required."}
        )
    filename, payload = validate_excel_upload(
        file.filename,
        file.file,
        max_bytes=settings.max_upload_bytes,
        allow_xlsm=settings.allow_xlsm,
    )
    source_id, path, digest = save_workbook(payload, filename, settings.upload_dir)
    sheets = inspect_workbook(path)
    source = {
        "source_id": source_id,
        "original_filename": filename,
        "storage_path": str(path),
        "sha256": digest,
        "created_at": datetime.now(UTC),
        "sheets": [item.model_dump() for item in sheets],
    }
    await repo.put_source(source)
    await audit(
        repo,
        action="source.uploaded",
        entity_id=source_id,
        actor=actor.subject,
        metadata={"sha256": digest},
    )
    return source


@router.get("")
async def list_sources(page: int = 1, page_size: int = 50, repo=Depends(repository)):
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_PAGINATION",
                "message": "page >= 1 and page_size 1..100 required.",
            },
        )
    sources = await repo.list_sources()
    start = (page - 1) * page_size
    return {
        "items": sources[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": len(sources),
    }


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(source_id: str, repo=Depends(repository), actor=Depends(current_actor)):
    source = await repo.get_source(source_id)
    if not source:
        raise HTTPException(
            404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source was not found."}
        )
    await audit(repo, action="source.accessed", entity_id=source_id, actor=actor.subject)
    return source


@router.get("/{source_id}/sheets")
async def get_sheets(source_id: str, repo=Depends(repository)):
    source = await repo.get_source(source_id)
    if not source:
        raise HTTPException(
            404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source was not found."}
        )
    return source["sheets"]
