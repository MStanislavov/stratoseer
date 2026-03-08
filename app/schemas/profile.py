from datetime import datetime

from pydantic import BaseModel, Field


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None


class ProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None


class ProfileRead(BaseModel):
    id: str
    name: str
    targets: list[str] | None = None
    constraints: list[str] | None = None
    skills: list[str] | None = None
    cv_path: str | None = None
    created_at: datetime
    updated_at: datetime
