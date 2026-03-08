"""Mock job scout extractor: converts raw listings to structured opportunities + evidence."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any


class JobScoutExtractor:
    """Phase-1 mock extractor. Converts raw job listings into
    structured opportunities with evidence items.
    """

    agent_name = "job_scout_extractor"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("raw_job_listings", [])
        opportunities: list[dict[str, Any]] = []
        evidence_items: list[dict[str, Any]] = []

        for listing in raw:
            eid = str(uuid.uuid4())
            content_hash = hashlib.sha256(
                (listing.get("description", "") + listing.get("url", "")).encode()
            ).hexdigest()

            evidence = {
                "id": eid,
                "evidence_type": "page",
                "url": listing["url"],
                "retrieved_at": listing.get(
                    "retrieved_at", datetime.now(timezone.utc).isoformat()
                ),
                "content_hash": content_hash,
                "snippet": listing.get("description", "")[:200],
            }
            evidence_items.append(evidence)

            opp = {
                "id": str(uuid.uuid4()),
                "opportunity_type": "job",
                "title": f"{listing['title']} at {listing['company']}",
                "source": listing["source"],
                "url": listing["url"],
                "description": listing["description"],
                "evidence_ids": [eid],
            }
            opportunities.append(opp)

        existing_opps = state.get("extracted_opportunities", [])
        existing_evidence = state.get("evidence_items", [])

        return {
            "extracted_opportunities": existing_opps + opportunities,
            "evidence_items": existing_evidence + evidence_items,
            "errors": state.get("errors", []),
        }
