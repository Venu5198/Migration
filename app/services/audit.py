from datetime import UTC, datetime
from uuid import uuid4


async def audit(
    repo,
    *,
    action: str,
    entity_id: str,
    actor: str = "system",
    job_id: str | None = None,
    correlation_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Persist metadata-only lineage; callers must not put raw spreadsheet values here."""
    await repo.add_audit(
        {
            "event_id": str(uuid4()),
            "timestamp": datetime.now(UTC),
            "action": action,
            "entity_id": entity_id,
            "actor": actor,
            "job_id": job_id,
            "correlation_id": correlation_id,
            "metadata": metadata or {},
        }
    )
