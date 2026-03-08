from datetime import datetime

from pydantic import BaseModel


class OpportunityRead(BaseModel):
    id: str
    profile_id: str
    run_id: str
    opportunity_type: str
    title: str
    source: str
    url: str | None = None
    description: str | None = None
    evidence_ids: list[str] = []
    metadata: dict | None = None
    created_at: datetime
