from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IssueSeverity(StrEnum):
    WARNING = "WARNING"
    REJECTED = "REJECTED"


class ValidationIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str
    sheet: str | None = None
    row: int | None = None
    field: str | None = None
    raw_value: str | None = None


class SheetSchema(BaseModel):
    name: str
    max_row: int = 0
    max_column: int = 0
    headers: list[str] = Field(default_factory=list)
    technical_headers: list[str] = Field(default_factory=list)
    header_rows_count: int = 1
    data_start_row: int = 2
    inferred_types: dict[str, str] = Field(default_factory=dict)
    issues: list[ValidationIssue] = Field(default_factory=list)


class SourceResponse(BaseModel):
    source_id: str
    original_filename: str
    sha256: str
    created_at: datetime
    sheets: list[SheetSchema]


class MappingType(StrEnum):
    DIRECT = "direct"
    TRANSFORMED = "transformed"
    DERIVED = "derived"
    EXCLUDED = "excluded"
    UNRESOLVED = "unresolved"


class MappingStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class MappingCreate(BaseModel):
    source_id: str
    source_entity: str
    source_sheet: str
    source_field: str
    target_entity: str
    target_field: str
    mapping_type: MappingType = MappingType.UNRESOLVED
    status: MappingStatus = MappingStatus.PROPOSED
    required: bool = False
    transformation: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class MappingUpdate(BaseModel):
    source_entity: str | None = None
    source_sheet: str | None = None
    source_field: str | None = None
    target_entity: str | None = None
    target_field: str | None = None
    mapping_type: MappingType | None = None
    required: bool | None = None
    transformation: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class MappingResponse(MappingCreate):
    mapping_id: str
    version: int
    created_at: datetime
    created_by: str | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None


class JobStatus(StrEnum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobResponse(BaseModel):
    job_id: str
    kind: str
    source_id: str
    source_filename: str | None = None
    status: JobStatus
    progress: int
    attempts: int
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    failure_code: str | None = None
    cancellation_requested: bool = False


class PagedJobs(BaseModel):
    items: list[JobResponse]
    page: int
    page_size: int
    total: int
