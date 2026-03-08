"""Mock trends scout extractor: converts raw trend data to structured opportunities + evidence."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any


class TrendsScoutExtractor:
    """Phase-1 mock extractor. Converts raw trend data into
    structured opportunities with evidence items.
    """

    agent_name = "trends_scout_extractor"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("raw_trends_data", [])
        opportunities: list[dict[str, Any]] = []
        evidence_items: list[dict[str, Any]] = []

        for item in raw:
            eid = str(uuid.uuid4())
            content_hash = hashlib.sha256(
                (item.get("description", "") + item.get("url", "")).encode()
            ).hexdigest()

            evidence = {
                "id": eid,
                "evidence_type": "page",
                "url": item["url"],
                "retrieved_at": item.get(
                    "retrieved_at", datetime.now(timezone.utc).isoformat()
                ),
                "content_hash": content_hash,
                "snippet": item.get("description", "")[:200],
            }
            evidence_items.append(evidence)

            opp = {
                "id": str(uuid.uuid4()),
                "opportunity_type": "trend",
                "title": item["title"],
                "source": item["source"],
                "url": item["url"],
                "description": item["description"],
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
