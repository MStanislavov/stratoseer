from datetime import datetime

from pydantic import BaseModel


class EvidenceItemRead(BaseModel):
    id: str
    run_id: str
    evidence_type: str
    url: str
    retrieved_at: datetime
    content_hash: str
    snippet: str
    metadata: dict | None = None


class ClaimRead(BaseModel):
    id: str
    run_id: str
    text: str
    requires_evidence: bool
    evidence_ids: list[str] = []
    confidence: float
