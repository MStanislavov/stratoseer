from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RunCreate(BaseModel):
    """Request body for starting a new pipeline run."""

    mode: Literal["daily", "weekly", "cover_letter"]
    options: dict | None = None


class BulkDeleteRequest(BaseModel):
    """Request body for bulk-deleting runs."""

    run_ids: list[str]


class BulkDeleteResponse(BaseModel):
    """Result of a bulk delete operation."""

    deleted: list[str]
    skipped: list[str]


class RunRead(BaseModel):
    """Read-only representation of a pipeline run returned by the API."""

    id: str
    profile_id: str
    mode: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    verifier_status: str | None = None
    audit_path: str | None = None
