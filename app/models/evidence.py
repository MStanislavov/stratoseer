import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id"), nullable=False
    )
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("artifacts.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    requires_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    evidence_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
