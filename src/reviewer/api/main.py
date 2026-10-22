from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from reviewer.api.api_review import router as review_jobs_router
from reviewer.api.dependencies import get_db
from reviewer.config.settings import settings

REVIEWER_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REVIEWER_DIR / "templates"
STATIC_DIR = REVIEWER_DIR / "static"

app = FastAPI(
    title=settings.app_name,
    description="Agentic AI code review and verification system",
    version=settings.app_version,
)

app.include_router(review_jobs_router)


@app.get("/")
def root():
    return FileResponse(TEMPLATES_DIR / "index.html")

@app.get("/health/db")
def database_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))

    return {
        "database": "connected",
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")