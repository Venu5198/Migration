from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import repository
from app.core.security import require_roles

router = APIRouter(prefix="/api/v1", tags=["audit"], dependencies=[Depends(require_roles("admin"))])


@router.get("/audit-events")
async def audit_events(
    entity_id: str | None = None, page: int = 1, page_size: int = 50, repo=Depends(repository)
):
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_PAGINATION",
                "message": "page >= 1 and page_size 1..100 required.",
            },
        )
    items, total = await repo.list_audit_page(entity_id, (page - 1) * page_size, page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}
