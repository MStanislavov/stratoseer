"""Mock cert scout retriever: returns realistic stub certification listings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class CertScoutRetriever:
    """Phase-1 mock retriever. Returns hard-coded certification listings.

    Swappable for a real LLM-backed retriever later.
    """

    agent_name = "cert_scout_retriever"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        raw_listings = [
            {
                "title": "AWS Solutions Architect Professional",
                "provider": "Amazon Web Services",
                "url": "https://aws.amazon.com/certification/solutions-architect-professional",
                "description": "Validate advanced technical skills in designing "
                "distributed systems on AWS.",
                "source": "aws.amazon.com/certification",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "title": "Google Cloud Professional Cloud Architect",
                "provider": "Google",
                "url": "https://cloud.google.com/certification/cloud-architect",
                "description": "Demonstrate ability to design and manage "
                "Google Cloud solutions.",
                "source": "cloud.google.com/certification",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        return {"raw_cert_listings": raw_listings, "errors": state.get("errors", [])}
