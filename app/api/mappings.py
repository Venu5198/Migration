from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import repository
from app.core.config import settings
from app.core.errors import DomainError
from app.core.security import require_roles
from app.schemas import MappingCreate, MappingResponse, MappingStatus, MappingType, MappingUpdate
from app.services.audit import audit
from app.services.transform import (
    is_blank_or_ambiguous_header,
    validate_mapping_compatibility,
    validate_transformation,
)

router = APIRouter(
    prefix="/api/v1/mappings",
    tags=["mappings"],
    dependencies=[Depends(require_roles("viewer", "executor", "approver", "admin"))],
)


@router.post("", response_model=MappingResponse, status_code=201)
async def create_mapping(
    payload: MappingCreate,
    repo=Depends(repository),
    actor=Depends(require_roles("executor", "admin")),
):
    source = await repo.get_source(payload.source_id)
    if not source:
        raise HTTPException(
            404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source was not found."}
        )
    sheet_match = next(
        (s for s in source.get("sheets", []) if s["name"] == payload.source_sheet), None
    )
    if not sheet_match:
        raise DomainError(
            "SOURCE_SHEET_NOT_FOUND",
            f"Sheet '{payload.source_sheet}' was not found in the source workbook.",
        )
    valid_source_fields = set(sheet_match.get("headers", [])) | {
        h for h in sheet_match.get("technical_headers", []) if h
    }
    if (
        payload.mapping_type != MappingType.UNRESOLVED
        and payload.source_field not in valid_source_fields
    ):
        raise DomainError(
            "SOURCE_FIELD_NOT_FOUND",
            f"Field '{payload.source_field}' was not found in sheet '{payload.source_sheet}'.",
        )
    try:
        validate_transformation(payload.transformation)
    except ValueError as exc:
        raise DomainError("INVALID_TRANSFORMATION", str(exc)) from exc
    try:
        validate_mapping_compatibility(
            payload.source_field,
            payload.target_field,
            payload.transformation,
            payload.mapping_type,
        )
    except ValueError as exc:
        raise DomainError("INCOMPATIBLE_FIELD_MAPPING", str(exc), 400) from exc
    if payload.mapping_type == "direct" and payload.transformation:
        raise DomainError("INVALID_MAPPING", "Direct mappings cannot specify a transformation.")

    now = datetime.now(UTC)
    mapping = {
        **payload.model_dump(),
        "mapping_id": str(uuid4()),
        "version": 1,
        "created_at": now,
        "created_by": actor.subject,
        "approved_at": None,
        "approved_by": None,
    }
    await repo.put_mapping(mapping)
    if hasattr(repo, "put_mapping_version"):
        await repo.put_mapping_version(mapping.copy())
    await audit(
        repo,
        action="mapping.created",
        entity_id=mapping["mapping_id"],
        actor=actor.subject,
        metadata={"version": 1, "source_id": payload.source_id},
    )
    return mapping


@router.get("/{mapping_id}", response_model=MappingResponse)
async def get_mapping(mapping_id: str, repo=Depends(repository)):
    mapping = await repo.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(
            404, detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping was not found."}
        )
    return mapping


@router.put("/{mapping_id}", response_model=MappingResponse)
async def update_mapping(
    mapping_id: str,
    payload: MappingUpdate,
    repo=Depends(repository),
    actor=Depends(require_roles("executor", "admin")),
):
    mapping = await repo.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(
            404, detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping was not found."}
        )
    if mapping.get("status") == MappingStatus.APPROVED:
        raise DomainError(
            "MAPPING_ALREADY_APPROVED",
            "Approved mappings are immutable and cannot be updated. Create a new mapping instead.",
            409,
        )
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return mapping
    if "transformation" in updates:
        try:
            validate_transformation(updates["transformation"])
        except ValueError as exc:
            raise DomainError("INVALID_TRANSFORMATION", str(exc)) from exc
    m_type = updates.get("mapping_type", mapping.get("mapping_type"))
    t_spec = updates.get("transformation", mapping.get("transformation"))
    if m_type == "direct" and t_spec:
        raise DomainError("INVALID_MAPPING", "Direct mappings cannot specify a transformation.")
    t_sheet = updates.get("source_sheet", mapping["source_sheet"])
    t_sheet = updates.get("source_sheet", mapping["source_sheet"])
    t_field = updates.get("source_field", mapping["source_field"])
    t_target = updates.get("target_field", mapping["target_field"])
    source = await repo.get_source(mapping["source_id"])
    if source:
        sheet_match = next((s for s in source.get("sheets", []) if s["name"] == t_sheet), None)
        if not sheet_match:
            raise DomainError(
                "SOURCE_SHEET_NOT_FOUND",
                f"Sheet '{t_sheet}' was not found in the source workbook.",
            )
        valid_source_fields = set(sheet_match.get("headers", [])) | {
            h for h in sheet_match.get("technical_headers", []) if h
        }
        if m_type != MappingType.UNRESOLVED and t_field not in valid_source_fields:
            raise DomainError(
                "SOURCE_FIELD_NOT_FOUND",
                f"Field '{t_field}' was not found in sheet '{t_sheet}'.",
            )
    try:
        validate_mapping_compatibility(t_field, t_target, t_spec, m_type)
    except ValueError as exc:
        raise DomainError("INCOMPATIBLE_FIELD_MAPPING", str(exc), 400) from exc
    mapping.update(updates)
    await repo.put_mapping(mapping)
    if hasattr(repo, "put_mapping_version"):
        await repo.put_mapping_version(mapping.copy())
    await audit(
        repo,
        action="mapping.updated",
        entity_id=mapping_id,
        actor=actor.subject,
        metadata={"version": mapping["version"]},
    )
    return mapping


@router.get("/{mapping_id}/versions")
async def mapping_versions(mapping_id: str, repo=Depends(repository)):
    if not await repo.get_mapping(mapping_id):
        raise HTTPException(
            404, detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping was not found."}
        )
    return await repo.list_mapping_versions(mapping_id)


@router.post("/{mapping_id}/approve", response_model=MappingResponse)
async def approve_mapping(
    mapping_id: str, repo=Depends(repository), actor=Depends(require_roles("approver", "admin"))
):
    mapping = await repo.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(
            404, detail={"code": "MAPPING_NOT_FOUND", "message": "Mapping was not found."}
        )
    if mapping.get("status") == MappingStatus.APPROVED:
        raise DomainError(
            "MAPPING_ALREADY_APPROVED",
            "Mapping is already approved and cannot be re-approved.",
            409,
        )
    if mapping["mapping_type"] == "unresolved":
        raise DomainError("UNRESOLVED_MAPPING", "Unresolved mappings cannot be approved.", 409)
    if is_blank_or_ambiguous_header(mapping["source_field"]):
        raise DomainError(
            "AMBIGUOUS_SOURCE_HEADER",
            (
                f"Mapping with blank or ambiguous source header '{mapping['source_field']}'"
                " cannot be approved."
            ),
            409,
        )
    try:
        validate_mapping_compatibility(
            mapping["source_field"],
            mapping["target_field"],
            mapping.get("transformation"),
            mapping.get("mapping_type", "direct"),
        )
    except ValueError as exc:
        raise DomainError("INCOMPATIBLE_FIELD_MAPPING", str(exc), 409) from exc

    source = await repo.get_source(mapping["source_id"])
    if source:
        sheet_match = next(
            (s for s in source.get("sheets", []) if s["name"] == mapping["source_sheet"]), None
        )
        if not sheet_match:
            raise DomainError(
                "SOURCE_SHEET_NOT_FOUND",
                f"Sheet '{mapping['source_sheet']}' was not found in the source workbook.",
                409,
            )
        valid_source_fields = set(sheet_match.get("headers", [])) | {
            h for h in sheet_match.get("technical_headers", []) if h
        }
        if mapping["source_field"] not in valid_source_fields:
            raise DomainError(
                "SOURCE_FIELD_NOT_FOUND",
                f"Field '{mapping['source_field']}' is not in sheet '{mapping['source_sheet']}' "
                "and cannot be approved.",
                409,
            )
    if settings.require_auth() and settings.enforce_separation_of_duties:
        creator = mapping.get("created_by")
        if creator and creator == actor.subject:
            raise DomainError(
                "SEPARATION_OF_DUTIES_VIOLATION",
                "The mapping author cannot approve their own mapping. "
                "Another approver must review.",
                403,
            )

    mapping.update(
        status=MappingStatus.APPROVED,
        approved_at=datetime.now(UTC),
        approved_by=actor.subject,
        version=mapping["version"] + 1,
    )
    await repo.put_mapping(mapping)
    if hasattr(repo, "put_mapping_version"):
        await repo.put_mapping_version(mapping.copy())
    await audit(
        repo,
        action="mapping.approved",
        entity_id=mapping_id,
        actor=actor.subject,
        metadata={"version": mapping["version"]},
    )
    return mapping
