"""Mock trends scout retriever: returns realistic stub industry trend data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TrendsScoutRetriever:
    """Phase-1 mock retriever. Returns hard-coded industry trend items.

    Swappable for a real LLM-backed retriever later.
    """

    agent_name = "trends_scout_retriever"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        raw_data = [
            {
                "title": "AI Agents Reshaping Software Development",
                "source": "news.ycombinator.com",
                "url": "https://news.ycombinator.com/item?id=12345",
                "description": "Multi-agent systems becoming mainstream in "
                "enterprise software development workflows.",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "title": "Rust Adoption in Cloud Infrastructure",
                "source": "techcrunch.com",
                "url": "https://techcrunch.com/2025/rust-cloud",
                "description": "Major cloud providers adopting Rust for "
                "performance-critical infrastructure components.",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        return {"raw_trends_data": raw_data, "errors": state.get("errors", [])}
