"""Tests for report persistence and retrieval API endpoint."""

from collections.abc import Generator
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from reviewer.api import api_review
from reviewer.api.dependencies import get_db
from reviewer.api.main import app
from reviewer.database import Base
from reviewer.models import ReviewFinding, ReviewJob, ReviewReport
from reviewer.schemas.findings import Finding
from reviewer.schemas.review_job import JobStatus

report_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
ReportSessionLocal = sessionmaker(
    bind=report_test_engine,
    autoflush=False,
    autocommit=False,
)


def override_report_db() -> Generator[Session, None, None]:
    db = ReportSessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=report_test_engine)
app.dependency_overrides[get_db] = override_report_db
client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_report_db
    Base.metadata.drop_all(bind=report_test_engine)
    Base.metadata.create_all(bind=report_test_engine)


def teardown_module() -> None:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=report_test_engine)
    report_test_engine.dispose()


def test_completed_job_persists_report_and_retrieves_via_api(monkeypatch) -> None:
    """1. Completed job produces one stored report; 6. GET /review/{job_id}/report returns stored report."""
    job_id = str(uuid4())
    repo_url = "https://github.com/example/completed-repo"
    commit = "1234567890abcdef1234567890abcdef12345678"

    with ReportSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository=repo_url,
            commit_sha=commit,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.commit()

    mock_finding = Finding(
        source="bandit",
        category="security",
        rule_id="B105",
        severity="critical",
        confidence="high",
        message="Hardcoded password string found",
        file_path="config.py",
        line=12,
        evidence="PW = 'admin123'",
        recommendation="Use environment variables",
    )

    mock_service = Mock()
    mock_service.agent_failures = 0
    mock_service.review_repository.return_value = [mock_finding]

    monkeypatch.setattr(api_review, "ReviewService", lambda: mock_service)
    monkeypatch.setattr(api_review, "SessionLocal", ReportSessionLocal)

    api_review.process_review_job(job_id)

    # 1. Verify job reached completed and exactly one report exists in DB
    with ReportSessionLocal() as db:
        updated_job = db.get(ReviewJob, job_id)
        assert updated_job.status == JobStatus.COMPLETED.value

        reports = db.query(ReviewReport).filter(ReviewReport.job_id == job_id).all()
        assert len(reports) == 1
        stored_report = reports[0]
        assert stored_report.job_id == job_id

        # 3. Verify repo URL and commit SHA in stored report
        data = stored_report.report_data
        assert data["overview"]["repository_url"] == repo_url
        assert data["overview"]["commit_sha"] == commit
        assert data["overview"]["status"] == JobStatus.COMPLETED.value

        # 4. Report findings and counts match final persisted findings
        persisted_findings = (
            db.query(ReviewFinding).filter(ReviewFinding.job_id == job_id).all()
        )
        assert len(persisted_findings) == 1
        assert data["findings_summary"]["total"] == 1
        assert data["findings_summary"]["by_severity"]["critical"] == 1
        assert data["findings_summary"]["by_category"]["security"] == 1

    # 6. Verify GET /review/{job_id}/report returns the stored report
    response = client.get(f"/review/{job_id}/report")
    assert response.status_code == 200
    report_json = response.json()
    assert report_json["overview"]["job_id"] == job_id
    assert report_json["overview"]["repository_url"] == repo_url
    assert report_json["overview"]["commit_sha"] == commit
    assert report_json["findings_summary"]["total"] == 1
    assert len(report_json["detailed_findings"]) == 1
    assert report_json["detailed_findings"][0]["rule_id"] == "B105"
    assert len(report_json["recommended_actions"]) == 1
    assert report_json["recommended_actions"][0]["severity"] == "critical"


def test_partial_completion_job_stores_correct_status_and_limitations(monkeypatch) -> None:
    """2. Partial-completion job stores the correct status and recorded limitations."""
    job_id = str(uuid4())
    repo_url = "https://github.com/example/partial-repo"
    commit = "abcdef0123456789abcdef0123456789abcdef01"

    with ReportSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository=repo_url,
            commit_sha=commit,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.commit()

    mock_finding = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="low",
        confidence="high",
        message="Line too long",
        file_path="main.py",
        line=20,
    )

    mock_service = Mock()
    mock_service.agent_failures = 2
    mock_service.review_repository.return_value = [mock_finding]

    monkeypatch.setattr(api_review, "ReviewService", lambda: mock_service)
    monkeypatch.setattr(api_review, "SessionLocal", ReportSessionLocal)

    api_review.process_review_job(job_id)

    response = client.get(f"/review/{job_id}/report")
    assert response.status_code == 200
    report_json = response.json()
    assert report_json["overview"]["status"] == JobStatus.COMPLETED_PARTIAL.value
    assert report_json["analysis_limitations"]["completion_status"] == JobStatus.COMPLETED_PARTIAL.value
    assert report_json["analysis_limitations"]["partial_review"] is True
    assert report_json["analysis_limitations"]["agent_failures"] == 2
    assert any("2 AI analysis operation(s) failed" in lim for lim in report_json["analysis_limitations"]["limitations"])


def test_reprocessing_does_not_create_duplicate_reports(monkeypatch) -> None:
    """5. Reprocessing or retrying does not create duplicate reports."""
    job_id = str(uuid4())
    with ReportSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository="https://github.com/example/retry-repo",
            commit_sha="a" * 40,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.commit()

    mock_finding = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="Unused import",
        file_path="app.py",
        line=1,
    )

    mock_service = Mock()
    mock_service.agent_failures = 0
    mock_service.review_repository.return_value = [mock_finding]

    monkeypatch.setattr(api_review, "ReviewService", lambda: mock_service)
    monkeypatch.setattr(api_review, "SessionLocal", ReportSessionLocal)

    # First execution
    api_review.process_review_job(job_id)
    # Second execution (retry/reprocessing)
    api_review.process_review_job(job_id)

    with ReportSessionLocal() as db:
        reports = db.query(ReviewReport).filter(ReviewReport.job_id == job_id).all()
        assert len(reports) == 1

        findings = db.query(ReviewFinding).filter(ReviewFinding.job_id == job_id).all()
        assert len(findings) == 1


def test_get_report_nonexistent_job_returns_404() -> None:
    """7. Nonexistent job returns 404."""
    response = client.get("/review/nonexistent-id/report")
    assert response.status_code == 404
    assert response.json()["detail"] == "Review job not found"


def test_get_report_queued_or_running_job_returns_409() -> None:
    """8. Queued or running job without a report returns 409."""
    job_id_queued = str(uuid4())
    job_id_running = str(uuid4())

    with ReportSessionLocal() as db:
        db.add(
            ReviewJob(
                id=job_id_queued,
                repository="https://github.com/example/queued",
                commit_sha="a" * 40,
                status=JobStatus.QUEUED.value,
            )
        )
        db.add(
            ReviewJob(
                id=job_id_running,
                repository="https://github.com/example/running",
                commit_sha="b" * 40,
                status=JobStatus.RUNNING.value,
            )
        )
        db.commit()

    res_queued = client.get(f"/review/{job_id_queued}/report")
    assert res_queued.status_code == 409
    assert "currently 'queued'" in res_queued.json()["detail"]

    res_running = client.get(f"/review/{job_id_running}/report")
    assert res_running.status_code == 409
    assert "currently 'running'" in res_running.json()["detail"]


def test_terminal_job_missing_report_returns_404() -> None:
    """9. Terminal job with a missing report is handled explicitly."""
    job_id = str(uuid4())
    with ReportSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository="https://github.com/example/failed-repo",
            commit_sha="c" * 40,
            status=JobStatus.FAILED.value,
            error_message="Git clone failed",
        )
        db.add(job)
        db.commit()

    response = client.get(f"/review/{job_id}/report")
    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found for this review job"
