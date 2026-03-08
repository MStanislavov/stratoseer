from datetime import datetime

from pydantic import BaseModel


class CoverLetterCreate(BaseModel):
    opportunity_id: str | None = None
    jd_text: str | None = None


class CoverLetterRead(BaseModel):
    id: str
    profile_id: str
    opportunity_id: str | None = None
    run_id: str | None = None
    content: str
    evidence_ids: list[str] = []
    created_at: datetime
