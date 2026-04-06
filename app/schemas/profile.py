from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ProfileCreate(BaseModel):
    """Request body for creating a new user profile workspace."""

    name: str = Field(..., min_length=1, max_length=200)
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None
    # Career & Job
    preferred_titles: list[str] | None = None
    experience_level: str | None = None
    industries: list[str] | None = None
    locations: list[str] | None = None
    work_arrangement: str | None = None
    event_attendance: str | None = "no preference"
    event_topics: list[str] | None = None
    # Learning & Certification
    target_certifications: list[str] | None = None
    learning_format: str | None = None


class ProfileUpdate(BaseModel):
    """Request body for partially updating an existing user profile."""

    name: str | None = Field(None, min_length=1, max_length=200)
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None
    # Career & Job
    preferred_titles: list[str] | None = None
    experience_level: str | None = None
    industries: list[str] | None = None
    locations: list[str] | None = None
    work_arrangement: str | None = None
    event_attendance: str | None = "no preference"
    event_topics: list[str] | None = None
    # Learning & Certification
    target_certifications: list[str] | None = None
    learning_format: str | None = None

    @field_validator("preferred_titles")
    @classmethod
    def preferred_titles_not_empty(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) == 0:
            raise ValueError("preferred_titles cannot be empty")
        return v


class ProfileRead(BaseModel):
    """Read-only representation of a user profile returned by the API."""

    id: str
    name: str
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None
    cv_filename: str | None = None
    has_cv_summary: bool = False
    # Career & Job
    preferred_titles: list[str] | None = None
    experience_level: str | None = None
    industries: list[str] | None = None
    locations: list[str] | None = None
    work_arrangement: str | None = None
    event_attendance: str | None = "no preference"
    event_topics: list[str] | None = None
    # Learning & Certification
    target_certifications: list[str] | None = None
    learning_format: str | None = None
    created_at: datetime
    updated_at: datetime


class ProfileExport(BaseModel):
    """Portable profile data for export and import between systems."""

    name: str
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None
    # Career & Job
    preferred_titles: list[str] | None = None
    experience_level: str | None = None
    industries: list[str] | None = None
    locations: list[str] | None = None
    work_arrangement: str | None = None
    event_attendance: str | None = "no preference"
    event_topics: list[str] | None = None
    # Learning & Certification
    target_certifications: list[str] | None = None
    learning_format: str | None = None
