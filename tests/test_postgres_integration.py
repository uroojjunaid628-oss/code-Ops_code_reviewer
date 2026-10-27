"""Live PostgreSQL integration tests for report persistence and retrieval."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from reviewer.config.settings import settings
from reviewer.models import ReviewFinding, ReviewJob, ReviewReport
from reviewer.schemas.findings import Finding
from reviewer.schemas.review_job import JobStatus
from reviewer.services.report import build_review_report

try:
    pg_engine = create_engine(settings.database_url, pool_pre_ping=True)
    with pg_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    pg_available = True
except Exception:  # noqa: BLE001
    pg_available = False

pytestmark = pytest.mark.skipif(
    not pg_available,
    reason="PostgreSQL database is not reachable at settings.database_url",
)

PgSession = sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)


def test_postgres_report_persistence_and_query() -> None:
    job_id = str(uuid4())
    repo_url = "https://github.com/example/pg-integration-repo"
    commit_sha = "0123456789abcdef0123456789abcdef01234567"

    with PgSession() as db:
        # Create Job
        job = ReviewJob(
            id=job_id,
            repository=repo_url,
            commit_sha=commit_sha,
            status=JobStatus.COMPLETED.value,
        )
        db.add(job)
        db.flush()

        # Create Finding
        finding = Finding(
            source="bandit",
            category="security",
            rule_id="B105",
            severity="critical",
            confidence="high",
            message="Possible hardcoded password found",
            file_path="src/security.py",
            line=15,
            evidence="SECRET_KEY = 'insecure'",
            recommendation="Store key in vault or env",
        )
        finding_record = ReviewFinding(
            id=str(uuid4()),
            job_id=job_id,
            source=finding.source,
            category=finding.category,
            rule_id=finding.rule_id,
            severity=finding.severity,
            confidence=finding.confidence,
            message=finding.message,
            file_path=finding.file_path,
            line=finding.line,
            evidence=finding.evidence,
            recommendation=finding.recommendation,
        )
        db.add(finding_record)

        # Build Report
        report_dto = build_review_report(
            job_id=job_id,
            repository_url=repo_url,
            commit_sha=commit_sha,
            status=JobStatus.COMPLETED.value,
            findings=[finding],
        )

        # Persist Report in PostgreSQL JSONB column
        report_record = ReviewReport(
            id=str(uuid4()),
            job_id=job_id,
            report_data=report_dto.model_dump(),
        )
        db.add(report_record)
        db.commit()

        # Query back from PostgreSQL
        queried_report = (
            db.query(ReviewReport).filter(ReviewReport.job_id == job_id).first()
        )
        assert queried_report is not None
        assert queried_report.job_id == job_id
        assert queried_report.report_data["overview"]["repository_url"] == repo_url
        assert queried_report.report_data["overview"]["commit_sha"] == commit_sha
        assert queried_report.report_data["findings_summary"]["total"] == 1
        assert (
            queried_report.report_data["findings_summary"]["by_severity"]["critical"]
            == 1
        )

        # Cleanup test records
        db.delete(job)
        db.commit()
