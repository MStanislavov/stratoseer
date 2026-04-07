"""Schemas for user settings (BYOK API key management)."""

from pydantic import BaseModel, Field


class ApiKeyUpdate(BaseModel):
    """Request body for storing or updating a user's BYOK API key.

    Use this schema when a user submits their own OpenAI-compatible API key
    for authenticated LLM calls instead of using free-tier runs.
    """

    api_key: str = Field(..., min_length=10)


class ApiKeyStatus(BaseModel):
    """Read-only status of a user's API key and free-tier usage.

    Use this schema to display whether the user has a stored API key,
    how many free runs they have consumed, and their remaining free-tier allowance.
    """

    has_api_key: bool
    free_runs_used: int
    free_run_limit: int
    key_last_four: str | None = None
