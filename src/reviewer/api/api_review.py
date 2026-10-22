
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from reviewer.api.dependencies import get_db
from reviewer.database import SessionLocal
from reviewer.models import ReviewFinding, ReviewJob
from reviewer.schemas.review_job import (
    JobStatus,
    ReviewFindingResponse,
    ReviewJobCreate,
    ReviewJobResponse,
)
from reviewer.services.review import ReviewService

router = APIRouter(prefix="/review", tags=["Review Jobs"])



def process_review_job(job_id: str) -> None:
    """Run a review and persist findings and final status."""
    db = SessionLocal()

    try:
        job = db.get(ReviewJob, job_id)
        if job is None:
            return

        job.status = JobStatus.RUNNING.value
        job.error_message = None
        db.commit()

        review_service = ReviewService()
        findings = review_service.review_repository(
            repository_url=job.repository,
            commit_sha=job.commit_sha,
            job_id=job.id,
        )

        for finding in findings:
            db.add(
                ReviewFinding(
                    id=str(uuid4()),
                    job_id=job.id,
                    source=finding.source,
                    category=finding.category,
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    confidence=finding.confidence,
                    message=finding.message,
                    file_path=finding.file_path,
                    line=finding.line,
                    column_number=finding.column,
                    evidence=finding.evidence,
                    recommendation=finding.recommendation,
                )
            )

        if review_service.agent_failures:
            job.status = JobStatus.COMPLETED_PARTIAL.value
            job.error_message = (
                f"{review_service.agent_failures} AI analysis operation(s) "
                "failed. Findings from successful analysis operations "
                "were preserved."
            )
        else:
            job.status = JobStatus.COMPLETED.value
            job.error_message = None

        db.commit()

    except Exception as exc:   # noqa: BLE001
        db.rollback()

        job = db.get(ReviewJob, job_id)
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.error_message = str(exc)[:4000]
            db.commit()

    finally:
        db.close()

@router.post("/", response_model=ReviewJobResponse, status_code=202)
def create_review_job(
    payload: ReviewJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    review_job = ReviewJob(
        id=str(uuid4()),
        repository=payload.repository,
        commit_sha=payload.commit_sha,
        status=JobStatus.QUEUED.value,
    )

    db.add(review_job)
    db.commit()
    db.refresh(review_job)

    background_tasks.add_task(process_review_job, review_job.id)

    return review_job


@router.get("/{job_id}", response_model=ReviewJobResponse)
def get_review_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ReviewJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")
    return job



@router.get(
    "/{job_id}/findings",
    response_model=list[ReviewFindingResponse],
)
def get_review_findings(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.get(ReviewJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")

    
    findings = (
        db.query(ReviewFinding)
        .filter(ReviewFinding.job_id == job_id)
        .order_by(ReviewFinding.file_path)
        .all()
    )

    severity_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
    }

    return sorted(
        findings,
        key=lambda finding: (
            severity_order.get(finding.severity.lower(), 99),
            finding.file_path,
            finding.line or 0,
        ),
    )

