"""Service for building consolidated, professional code-review reports."""

from collections.abc import Sequence
from typing import Any

from reviewer.schemas.findings import Finding
from reviewer.schemas.review_job import (
    AnalysisStatusAndLimitations,
    CategoryBreakdown,
    DetailedFinding,
    ExecutiveSummary,
    FindingsSummary,
    JobStatus,
    RecommendedAction,
    ReviewOverview,
    ReviewReportResponse,
    SeverityBreakdown,
)

SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "unknown": 1,
}

CONFIDENCE_WEIGHTS: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}


def _extract_attr(item: Any, *keys: str, default: Any = None) -> Any:
    """Extract an attribute or dictionary key safely."""
    for key in keys:
        if isinstance(item, dict) and key in item:
            return item[key]
        if hasattr(item, key):
            return getattr(item, key)
    return default


def _format_finding_title(message: str, rule_id: str | None) -> str:
    """Generate a clean, concise title from the finding message or rule."""
    first_sentence = message.strip().split(".")[0].strip()
    if len(first_sentence) > 80:
        first_sentence = first_sentence[:77].rstrip() + "..."
    return first_sentence or (rule_id or "Identified Issue")


def _build_executive_summary(
    total: int,
    severities: SeverityBreakdown,
    categories: CategoryBreakdown,
    files_inspected: set[str],
    agent_failures: int,
) -> ExecutiveSummary:
    """Build a concise, honest executive summary grounded purely on findings."""
    if total == 0:
        return ExecutiveSummary(
            summary=(
                "No issues were identified during this review. All verified checks "
                "passed across static-analysis scans and AI source inspections."
            ),
            key_observations=[
                (
                    "Static and AI inspection found no security vulnerabilities, bugs, "
                    "quality issues, or testing gaps in inspected files."
                )
            ],
        )

    file_count = len(files_inspected)
    file_str = f"{file_count} file{'s' if file_count != 1 else ''}"

    crit_high = severities.critical + severities.high
    if crit_high > 0:
        urgency_phrase = (
            f"with {crit_high} high-priority finding(s) "
            f"({severities.critical} critical, {severities.high} high) "
            "requiring immediate attention"
        )
    else:
        urgency_phrase = "with no critical or high-severity issues identified"

    summary_text = (
        f"The review identified {total} finding(s) across {file_str}, {urgency_phrase}. "
        "Assessments are grounded in static tool scans and AI source inspection; "
        "test suites were not executed at runtime."
    )

    observations: list[str] = []
    if severities.critical > 0:
        observations.append(
            f"{severities.critical} critical severity issue(s) detected that should be resolved before release."
        )
    if severities.high > 0:
        observations.append(
            f"{severities.high} high severity issue(s) identified impacting security, reliability, or correctness."
        )

    dominant_categories: list[str] = []
    if categories.security > 0:
        dominant_categories.append(f"{categories.security} security")
    if categories.bug > 0:
        dominant_categories.append(f"{categories.bug} bug")
    if categories.quality > 0:
        dominant_categories.append(f"{categories.quality} code quality")
    if categories.test > 0:
        dominant_categories.append(f"{categories.test} testing gap")

    if dominant_categories:
        observations.append(
            f"Distribution across categories: {', '.join(dominant_categories)}."
        )

    if agent_failures > 0:
        observations.append(
            f"{agent_failures} AI analysis operation(s) encountered errors; results reflect completed operations."
        )

    return ExecutiveSummary(
        summary=summary_text,
        key_observations=observations,
    )


def _build_recommended_actions(
    detailed_findings: list[DetailedFinding],
) -> list[RecommendedAction]:
    """Generate a prioritized list of recommendations derived strictly from findings."""
    # Sort findings by severity weight, confidence weight, evidence presence, file, line
    def sort_key(f: DetailedFinding) -> tuple[int, int, int, str, int]:
        sev_w = SEVERITY_WEIGHTS.get(str(f.severity).lower(), 0)
        conf_w = CONFIDENCE_WEIGHTS.get(str(f.confidence).lower(), 0)
        ev_w = 1 if f.evidence else 0
        file_key = f.file_path or ""
        line_key = f.line or 0
        return (-sev_w, -conf_w, -ev_w, file_key, line_key)

    sorted_findings = sorted(detailed_findings, key=sort_key)

    actions: list[RecommendedAction] = []
    for rank, f in enumerate(sorted_findings, start=1):
        loc_str = f" in {f.file_path}"
        if f.line is not None:
            loc_str += f" (line {f.line})"

        if f.recommendation and f.recommendation.strip():
            action_text = f.recommendation.strip()
        else:
            action_text = f"Review and remediate {f.title}{loc_str}."

        action_title = f"Resolve {f.category} issue{loc_str}"

        actions.append(
            RecommendedAction(
                priority=rank,
                title=action_title,
                action=action_text,
                severity=str(f.severity),
                category=str(f.category),
                file_path=f.file_path,
                line=f.line,
            )
        )

    return actions


def build_review_report(
    *,
    job_id: str,
    repository_url: str,
    commit_sha: str,
    status: str = JobStatus.COMPLETED.value,
    findings: Sequence[Finding | Any] = (),
    agent_failures: int = 0,
    error_message: str | None = None,
    limitations: list[str] | None = None,
) -> ReviewReportResponse:
    """Build a consolidated, professional code-review report.

    Args:
        job_id: Unique identifier for the review job.
        repository_url: URL of the reviewed repository.
        commit_sha: Commit hash analyzed.
        status: Execution status (completed, completed_partial, failed).
        findings: Sequence of verified, deduplicated findings (Finding or ReviewFinding).
        agent_failures: Number of agent operation failures recorded.
        error_message: Optional error message recorded on the job.
        limitations: Optional additional limitation strings.

    Returns:
        ReviewReportResponse: Consolidated report conforming to the redesigned schema.
    """
    severity_counts = SeverityBreakdown()
    category_counts = CategoryBreakdown()
    files_inspected: set[str] = set()
    detailed_findings: list[DetailedFinding] = []

    for item in findings:
        severity = str(_extract_attr(item, "severity", default="unknown")).lower()
        category = str(_extract_attr(item, "category", default="quality")).lower()
        source = str(_extract_attr(item, "source", default="ai_agent"))
        rule_id = _extract_attr(item, "rule_id", default=None)
        file_path = str(_extract_attr(item, "file_path", default=""))
        line = _extract_attr(item, "line", default=None)
        column = _extract_attr(item, "column", "column_number", default=None)
        evidence = _extract_attr(item, "evidence", default=None)
        recommendation = _extract_attr(item, "recommendation", default=None)
        confidence = str(_extract_attr(item, "confidence", default="unknown")).lower()
        message = str(_extract_attr(item, "message", default=""))
        finding_id = _extract_attr(item, "id", default=None)

        if file_path:
            files_inspected.add(file_path)

        # Count severities
        if severity == "critical":
            severity_counts.critical += 1
        elif severity == "high":
            severity_counts.high += 1
        elif severity == "medium":
            severity_counts.medium += 1
        elif severity == "low":
            severity_counts.low += 1
        else:
            severity_counts.unknown += 1

        # Count categories
        if category == "bug":
            category_counts.bug += 1
        elif category == "security":
            category_counts.security += 1
        elif category == "quality":
            category_counts.quality += 1
        elif category == "test":
            category_counts.test += 1

        detailed_findings.append(
            DetailedFinding(
                id=finding_id,
                title=_format_finding_title(message, rule_id),
                severity=severity,
                category=category,
                source=source,
                rule_id=rule_id,
                file_path=file_path,
                line=line,
                column=column,
                evidence=evidence,
                explanation=message,
                recommendation=recommendation,
                confidence=confidence,
            )
        )

    total_findings = len(detailed_findings)

    # Section A: Review Overview
    overview = ReviewOverview(
        job_id=job_id,
        repository_url=repository_url,
        commit_sha=commit_sha,
        status=status,
        total_findings=total_findings,
    )

    # Section B: Executive Summary
    executive_summary = _build_executive_summary(
        total=total_findings,
        severities=severity_counts,
        categories=category_counts,
        files_inspected=files_inspected,
        agent_failures=agent_failures,
    )

    # Section C: Findings Summary
    findings_summary = FindingsSummary(
        total=total_findings,
        by_severity=severity_counts,
        by_category=category_counts,
    )

    # Section E: Recommended Actions
    recommended_actions = _build_recommended_actions(detailed_findings)

    # Section F: Analysis Status and Limitations
    is_partial = (
        status == JobStatus.COMPLETED_PARTIAL.value
        or agent_failures > 0
    )
    system_limitations = [
        "AI agent analysis was scoped to a maximum of 3 Python files of size up to 10,000 bytes.",
        "Static analysis was executed with Ruff and Bandit.",
        "Analysis is based on source code and test file inspection. Test suites were not executed at runtime.",
    ]
    if agent_failures > 0:
        system_limitations.append(
            f"{agent_failures} AI analysis operation(s) failed during processing; findings from successful operations are preserved."
        )
    if error_message and error_message.strip():
        system_limitations.append(f"Recorded message: {error_message.strip()}")
    if limitations:
        system_limitations.extend(limitations)

    analysis_limitations = AnalysisStatusAndLimitations(
        completion_status=status,
        partial_review=is_partial,
        agent_failures=agent_failures,
        limitations=system_limitations,
    )

    # Backward compatibility mappings
    severity_breakdown_dict = {
        "critical": severity_counts.critical,
        "high": severity_counts.high,
        "medium": severity_counts.medium,
        "low": severity_counts.low,
        "unknown": severity_counts.unknown,
    }
    category_breakdown_dict = {
        "bug": category_counts.bug,
        "security": category_counts.security,
        "quality": category_counts.quality,
        "test": category_counts.test,
    }

    return ReviewReportResponse(
        overview=overview,
        executive_summary=executive_summary,
        findings_summary=findings_summary,
        detailed_findings=detailed_findings,
        recommended_actions=recommended_actions,
        analysis_limitations=analysis_limitations,
        # Backwards compatibility attributes
        job_id=job_id,
        total_findings=total_findings,
        severity_breakdown=severity_breakdown_dict,
        category_breakdown=category_breakdown_dict,
        findings=detailed_findings,
    )
