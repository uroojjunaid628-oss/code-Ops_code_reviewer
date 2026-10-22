from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from reviewer.api import api_review
from reviewer.api.dependencies import get_db
from reviewer.api.main import app
from reviewer.database import Base
from reviewer.models import ReviewJob

test_engine = create_engine(
    "sqlite://",
    connect_args= {"check_same_thread":False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
)

def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

Base.metadata.create_all(bind=test_engine)
app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def teardown_module() -> None:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_get_missing_review_job_returns_404() -> None:
    response = client.get("/review/nonexistent-job")

    assert response.status_code == 404
    assert response.json() == {"detail": "Review job not found"}


def test_get_findings_for_missing_job_returns_404() -> None:
    response = client.get("/review/nonexistent-job/findings")

    assert response.status_code == 404
    assert response.json() == {"detail": "Review job not found"}

def test_create_review_job_returns_202(monkeypatch) -> None:
    monkeypatch.setattr(
        api_review,
        "process_review_job",
        lambda job_id: None,
    )

    response = client.post(
        "/review/",
        json={
            "repository": "https://github.com/example/test-repo",
            "commit_sha": "a" * 40,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["repository"] == "https://github.com/example/test-repo"
    assert data["commit_sha"] == "a" * 40
    assert data["status"] == "queued"

    with TestingSessionLocal() as db:
        saved_job = db.get(ReviewJob, data["id"])
        assert saved_job is not None
        assert saved_job.status == "queued"    