from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_PARTIAL = "completed_partial"
    FAILED = "failed"


class ReviewJobCreate(BaseModel):
    repository: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Repository URL (HTTP/HTTPS or SSH Git clone URL)",
        pattern=r"^(https?://[^\s/$.?#].[^\s]*|git@[^\s:]+:[^\s]+)$",
    )
    commit_sha: str = Field(
        ...,
        min_length=40,
        max_length=40,
        description="40-character hexadecimal git commit hash",
        pattern=r"^[0-9a-fA-F]{40}$",
    )


class ReviewJobResponse(BaseModel):
    id: str
    repository: str
    commit_sha: str
    status: JobStatus | str
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)
    


class ReviewFindingResponse(BaseModel):
    id: str
    job_id: str
    source: str
    category: str
    rule_id: str
    severity: str
    confidence: str
    message: str
    file_path: str
    line: int | None
    column_number: int | None
    evidence: str | None
    recommendation: str | None

    model_config = ConfigDict(from_attributes=True)
