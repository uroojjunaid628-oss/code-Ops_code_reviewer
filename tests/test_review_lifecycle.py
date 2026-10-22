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
from reviewer.models import ReviewFinding, ReviewJob
from reviewer.schemas.findings import Finding
from reviewer.schemas.review_job import JobStatus

lifecycle_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
LifecycleSessionLocal = sessionmaker(
    bind=lifecycle_engine,
    autoflush=False,
    autocommit=False,
)


def override_lifecycle_db() -> Generator[Session, None, None]:
    db = LifecycleSessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=lifecycle_engine)
app.dependency_overrides[get_db] = override_lifecycle_db
client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_lifecycle_db
    Base.metadata.drop_all(bind=lifecycle_engine)
    Base.metadata.create_all(bind=lifecycle_engine)


def teardown_module() -> None:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=lifecycle_engine)
    lifecycle_engine.dispose()



def test_create_review_job_rejects_invalid_url() -> None:
    response = client.post(
        "/review/",
        json={
            "repository": "not_a_valid_url",
            "commit_sha": "a" * 40,
        },
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("repository" in err["loc"] for err in errors)


def test_create_review_job_rejects_invalid_commit_sha() -> None:
    response = client.post(
        "/review/",
        json={
            "repository": "https://github.com/example/valid-repo",
            "commit_sha": "not-a-40-char-hex-sha",
        },
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("commit_sha" in err["loc"] for err in errors)


def test_create_review_job_accepts_valid_ssh_url(monkeypatch) -> None:
    monkeypatch.setattr(api_review, "process_review_job", lambda job_id: None)

    response = client.post(
        "/review/",
        json={
            "repository": "git@github.com:example/repo.git",
            "commit_sha": "0123456789abcdef0123456789abcdef01234567",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == JobStatus.QUEUED.value
    assert data["repository"] == "git@github.com:example/repo.git"


def test_lifecycle_transitions_to_completed_with_findings(monkeypatch) -> None:
    job_id = str(uuid4())
    with LifecycleSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository="https://github.com/example/repo",
            commit_sha="a" * 40,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.commit()

    mock_finding = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="medium",
        confidence="high",
        message="Line too long",
        file_path="app.py",
        line=1,
    )

    mock_service_instance = Mock()
    mock_service_instance.agent_failures = 0
    mock_service_instance.review_repository.return_value = [mock_finding]

    monkeypatch.setattr(api_review, "ReviewService", lambda: mock_service_instance)
    monkeypatch.setattr(api_review, "SessionLocal", LifecycleSessionLocal)

    api_review.process_review_job(job_id)

    with LifecycleSessionLocal() as db:
        updated_job = db.get(ReviewJob, job_id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.COMPLETED.value
        assert updated_job.error_message is None

        persisted_findings = (
            db.query(ReviewFinding)
            .filter(ReviewFinding.job_id == job_id)
            .all()
        )
        assert len(persisted_findings) == 1
        assert persisted_findings[0].rule_id == "E501"


def test_lifecycle_transitions_to_completed_partial_on_agent_failure(monkeypatch) -> None:
    job_id = str(uuid4())
    with LifecycleSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository="https://github.com/example/repo",
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

    mock_service_instance = Mock()
    mock_service_instance.agent_failures = 2
    mock_service_instance.review_repository.return_value = [mock_finding]

    monkeypatch.setattr(api_review, "ReviewService", lambda: mock_service_instance)
    monkeypatch.setattr(api_review, "SessionLocal", LifecycleSessionLocal)

    api_review.process_review_job(job_id)

    with LifecycleSessionLocal() as db:
        updated_job = db.get(ReviewJob, job_id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.COMPLETED_PARTIAL.value
        assert "2 AI analysis operation(s) failed" in updated_job.error_message

        # Successful findings still preserved
        persisted = db.query(ReviewFinding).filter(ReviewFinding.job_id == job_id).all()
        assert len(persisted) == 1


def test_lifecycle_transitions_to_failed_on_fatal_exception(monkeypatch) -> None:
    job_id = str(uuid4())
    with LifecycleSessionLocal() as db:
        job = ReviewJob(
            id=job_id,
            repository="https://github.com/example/repo",
            commit_sha="a" * 40,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.commit()

    mock_service_instance = Mock()
    mock_service_instance.review_repository.side_effect = RuntimeError("Fatal: Git clone timed out")

    monkeypatch.setattr(api_review, "ReviewService", lambda: mock_service_instance)
    monkeypatch.setattr(api_review, "SessionLocal", LifecycleSessionLocal)

    api_review.process_review_job(job_id)

    with LifecycleSessionLocal() as db:
        updated_job = db.get(ReviewJob, job_id)
        assert updated_job is not None
        assert updated_job.status == JobStatus.FAILED.value
        assert "Fatal: Git clone timed out" in updated_job.error_message
