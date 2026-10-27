"""Tests for the consolidated code-review report builder and schemas."""

from uuid import uuid4

from reviewer.models.review_findings import ReviewFinding
from reviewer.schemas.findings import Finding
from reviewer.schemas.review_job import (
    DetailedFinding,
    JobStatus,
    ReviewReportResponse,
)
from reviewer.services.report import build_review_report


def test_build_report_empty_findings() -> None:
    job_id = str(uuid4())
    report = build_review_report(
        job_id=job_id,
        repository_url="https://github.com/example/empty-repo",
        commit_sha="a" * 40,
        status=JobStatus.COMPLETED.value,
        findings=[],
        agent_failures=0,
    )

    assert isinstance(report, ReviewReportResponse)
    # Section A
    assert report.overview.job_id == job_id
    assert report.overview.repository_url == "https://github.com/example/empty-repo"
    assert report.overview.commit_sha == "a" * 40
    assert report.overview.status == "completed"
    assert report.overview.total_findings == 0

    # Section B
    assert "No issues were identified" in report.executive_summary.summary
    assert len(report.executive_summary.key_observations) >= 1

    # Section C
    assert report.findings_summary.total == 0
    assert report.findings_summary.by_severity.critical == 0
    assert report.findings_summary.by_severity.high == 0
    assert report.findings_summary.by_severity.medium == 0
    assert report.findings_summary.by_severity.low == 0
    assert report.findings_summary.by_severity.unknown == 0
    assert report.findings_summary.by_category.bug == 0
    assert report.findings_summary.by_category.security == 0
    assert report.findings_summary.by_category.quality == 0
    assert report.findings_summary.by_category.test == 0

    # Section D
    assert report.detailed_findings == []

    # Section E
    assert report.recommended_actions == []

    # Section F
    assert report.analysis_limitations.completion_status == "completed"
    assert report.analysis_limitations.partial_review is False
    assert report.analysis_limitations.agent_failures == 0
    assert any("Ruff and Bandit" in lim for lim in report.analysis_limitations.limitations)
    assert any("Test suites were not executed" in lim for lim in report.analysis_limitations.limitations)

    # Backwards compatibility attributes
    assert report.job_id == job_id
    assert report.total_findings == 0
    assert report.severity_breakdown["critical"] == 0
    assert report.category_breakdown["security"] == 0
    assert report.findings == []


def test_build_report_with_findings_and_prioritization() -> None:
    job_id = str(uuid4())
    findings = [
        Finding(
            source="ruff",
            category="quality",
            rule_id="F401",
            severity="low",
            confidence="high",
            message="`os` imported but unused",
            file_path="src/main.py",
            line=2,
            column=1,
            evidence="import os",
            recommendation="Remove unused import",
        ),
        Finding(
            source="bandit",
            category="security",
            rule_id="B105",
            severity="critical",
            confidence="high",
            message="Possible hardcoded password: 'secret'",
            file_path="src/config.py",
            line=10,
            evidence="PASSWORD = 'secret'",
            recommendation="Load secrets from environment variables",
        ),
        Finding(
            source="ai_agent",
            category="bug",
            rule_id="resource-leak",
            severity="high",
            confidence="medium",
            message="Unclosed file handle in process_data",
            file_path="src/utils.py",
            line=45,
            evidence="f = open('data.txt')",
            recommendation="Use with open(...) as f context manager",
        ),
        Finding(
            source="ai_agent",
            category="test",
            rule_id="missing-test",
            severity="medium",
            confidence="low",
            message="Missing test for error branch in calculate()",
            file_path="src/calc.py",
            line=12,
            recommendation="Add unit test with negative values",
        ),
    ]

    report = build_review_report(
        job_id=job_id,
        repository_url="https://github.com/example/repo",
        commit_sha="b" * 40,
        status=JobStatus.COMPLETED.value,
        findings=findings,
        agent_failures=0,
    )

    # Overview
    assert report.overview.total_findings == 4

    # Executive Summary
    assert "4 finding(s)" in report.executive_summary.summary
    assert "1 critical, 1 high" in report.executive_summary.summary

    # Findings Summary Counts
    assert report.findings_summary.total == 4
    assert report.findings_summary.by_severity.critical == 1
    assert report.findings_summary.by_severity.high == 1
    assert report.findings_summary.by_severity.medium == 1
    assert report.findings_summary.by_severity.low == 1
    assert report.findings_summary.by_severity.unknown == 0

    assert report.findings_summary.by_category.security == 1
    assert report.findings_summary.by_category.bug == 1
    assert report.findings_summary.by_category.quality == 1
    assert report.findings_summary.by_category.test == 1

    # Detailed Findings
    assert len(report.detailed_findings) == 4
    sources = {f.source for f in report.detailed_findings}
    assert sources == {"ruff", "bandit", "ai_agent"}

    # Honest attribution check: AI findings retain "ai_agent"
    ai_findings = [f for f in report.detailed_findings if f.source == "ai_agent"]
    assert len(ai_findings) == 2
    for f in ai_findings:
        assert f.source == "ai_agent"

    # Prioritization check in recommended actions
    # Critical should be priority 1, High should be priority 2, Medium priority 3, Low priority 4
    assert len(report.recommended_actions) == 4
    priorities = [a.priority for a in report.recommended_actions]
    assert priorities == [1, 2, 3, 4]

    action_severities = [a.severity for a in report.recommended_actions]
    assert action_severities == ["critical", "high", "medium", "low"]
    assert report.recommended_actions[0].category == "security"
    assert report.recommended_actions[0].file_path == "src/config.py"
    assert "Load secrets" in report.recommended_actions[0].action


def test_build_report_partial_review_status() -> None:
    job_id = str(uuid4())
    finding = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="low",
        confidence="high",
        message="Line too long",
        file_path="app.py",
        line=10,
    )

    report = build_review_report(
        job_id=job_id,
        repository_url="https://github.com/example/repo",
        commit_sha="c" * 40,
        status=JobStatus.COMPLETED_PARTIAL.value,
        findings=[finding],
        agent_failures=2,
        error_message="2 AI analysis operation(s) failed.",
    )

    assert report.overview.status == "completed_partial"
    assert report.analysis_limitations.partial_review is True
    assert report.analysis_limitations.agent_failures == 2
    assert any("2 AI analysis operation(s) failed" in lim for lim in report.analysis_limitations.limitations)


def test_build_report_with_review_finding_db_objects() -> None:
    job_id = str(uuid4())
    db_finding = ReviewFinding(
        id=str(uuid4()),
        job_id=job_id,
        source="bandit",
        category="security",
        rule_id="B301",
        severity="high",
        confidence="high",
        message="Use of pickle is insecure",
        file_path="service.py",
        line=25,
        column_number=5,
        evidence="pickle.loads(payload)",
        recommendation="Use JSON or safe serialization",
    )

    report = build_review_report(
        job_id=job_id,
        repository_url="https://github.com/example/repo",
        commit_sha="d" * 40,
        findings=[db_finding],
    )

    assert report.overview.total_findings == 1
    assert len(report.detailed_findings) == 1
    df = report.detailed_findings[0]
    assert isinstance(df, DetailedFinding)
    assert df.id == db_finding.id
    assert df.column == 5
    assert df.line == 25
    assert df.evidence == "pickle.loads(payload)"
    assert df.recommendation == "Use JSON or safe serialization"
