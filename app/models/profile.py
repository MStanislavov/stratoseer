import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserProfile(Base):
    """Persistent user profile representing an independent workspace."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    targets: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Career & Job
    preferred_titles: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    industries: Mapped[str | None] = mapped_column(Text, nullable=True)
    locations: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_attendance: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Learning & Certification
    target_certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    learning_budget: Mapped[str | None] = mapped_column(String(50), nullable=True)
    learning_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time_commitment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
