from enum import StrEnum
from typing import Literal

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
    line: int | None = None
    column_number: int | None = None
    evidence: str | None = None
    recommendation: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReviewOverview(BaseModel):
    """Section A: Core metadata and scope of the review."""

    job_id: str = Field(description="Unique identifier for the review job")
    repository_url: str = Field(description="Target repository clone URL")
    commit_sha: str = Field(description="Git commit SHA inspected")
    status: str = Field(
        description="Review execution status (e.g. completed, completed_partial, failed)"
    )
    total_findings: int = Field(
        ge=0, description="Total verified and deduplicated findings"
    )

    model_config = ConfigDict(from_attributes=True)


class ExecutiveSummary(BaseModel):
    """Section B: Human-readable synopsis grounded strictly in actual findings."""

    summary: str = Field(
        description="Concise qualitative summary of the review outcome"
    )
    key_observations: list[str] = Field(
        default_factory=list,
        description="Key factual takeaways highlighting dominant severity and categories",
    )

    model_config = ConfigDict(from_attributes=True)


class SeverityBreakdown(BaseModel):
    """Strict breakdown across all recognized severity levels."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    unknown: int = 0

    model_config = ConfigDict(from_attributes=True)


class CategoryBreakdown(BaseModel):
    """Strict breakdown across all four analysis categories."""

    bug: int = 0
    security: int = 0
    quality: int = 0
    test: int = 0

    model_config = ConfigDict(from_attributes=True)


class FindingsSummary(BaseModel):
    """Section C: Quantitative aggregations of final verified findings."""

    total: int = Field(ge=0, description="Total number of findings")
    by_severity: SeverityBreakdown
    by_category: CategoryBreakdown

    model_config = ConfigDict(from_attributes=True)


class DetailedFinding(BaseModel):
    """Section D: Comprehensive finding item."""

    id: str | None = Field(
        default=None, description="Optional finding identifier if persisted"
    )
    title: str = Field(description="Concise description or issue title")
    severity: Literal["critical", "high", "medium", "low", "unknown"] | str
    category: Literal["bug", "security", "quality", "test"] | str
    source: str = Field(
        description="Source tool or agent: 'ruff', 'bandit', or 'ai_agent'"
    )
    rule_id: str | None = Field(
        default=None, description="Static rule ID or AI rule descriptor"
    )
    file_path: str = Field(
        description="Normalized relative path to the affected file"
    )
    line: int | None = Field(
        default=None, description="1-based line number if identifiable"
    )
    column: int | None = Field(
        default=None, description="1-based column number if identifiable"
    )
    evidence: str | None = Field(
        default=None, description="Verified source snippet, when available"
    )
    explanation: str = Field(
        description="Detailed explanation of the issue and its implications"
    )
    recommendation: str | None = Field(
        default=None,
        description="Practical recommendation for resolving the issue",
    )
    confidence: Literal["high", "medium", "low", "unknown"] | str = Field(
        default="unknown",
        description="Confidence level in the validity of this finding",
    )

    model_config = ConfigDict(from_attributes=True)


class RecommendedAction(BaseModel):
    """Section E: Prioritized actionable guidance derived directly from findings."""

    priority: int = Field(ge=1, description="Priority rank (1 being highest)")
    title: str = Field(description="Action summary")
    action: str = Field(description="Actionable instruction for remediation")
    severity: str = Field(description="Severity of the underlying finding")
    category: str = Field(description="Category of the finding")
    file_path: str = Field(description="File requiring attention")
    line: int | None = Field(default=None, description="Line number if available")

    model_config = ConfigDict(from_attributes=True)


class AnalysisStatusAndLimitations(BaseModel):
    """Section F: Transparent operational disclosure and system boundaries."""

    completion_status: str = Field(description="Execution status of the review")
    partial_review: bool = Field(
        description="True if any agent or analysis steps encountered errors"
    )
    agent_failures: int = Field(
        ge=0,
        description="Count of failed agent operations during analysis",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Recorded limitations and analysis boundaries",
    )

    model_config = ConfigDict(from_attributes=True)


class ReviewReportResponse(BaseModel):
    """Consolidated code-review report encompassing all sections."""

    overview: ReviewOverview
    executive_summary: ExecutiveSummary
    findings_summary: FindingsSummary
    detailed_findings: list[DetailedFinding]
    recommended_actions: list[RecommendedAction]
    analysis_limitations: AnalysisStatusAndLimitations

    # Compatibility attributes
    job_id: str | None = None
    total_findings: int | None = None
    severity_breakdown: dict[str, int] | None = None
    category_breakdown: dict[str, int] | None = None
    findings: list[DetailedFinding] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

