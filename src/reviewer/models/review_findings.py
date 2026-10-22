from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from reviewer.database import Base


class ReviewFinding(Base):
    __tablename__= "review_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key= True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("review_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,

    )

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text , nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)




