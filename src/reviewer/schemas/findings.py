
from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    source: Literal["ruff", "bandit", "ai_agent"]
    category: Literal["bug", "security", "quality", "test"]
    rule_id: str
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    confidence: Literal["high", "medium", "low", "unknown"]
    message: str
    file_path: str
    line: int | None = None
    column: int | None = None
    evidence: str | None = None
    recommendation: str | None = None
