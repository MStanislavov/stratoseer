"""Mock coordinator: merges extracted items, produces ranked list + claims + summary."""

from __future__ import annotations

from typing import Any


class Coordinator:
    """Phase-1 mock coordinator. Passes through opportunities as-is,
    generates one claim per opportunity, and produces a summary string.
    """

    agent_name = "coordinator"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        opportunities = state.get("extracted_opportunities", [])
        evidence_items = state.get("evidence_items", [])

        # Simple ranking: pass through (mock behaviour)
        ranked = list(opportunities)

        # Generate one claim per opportunity
        claims: list[dict[str, Any]] = []
        for opp in ranked:
            claims.append(
                {
                    "claim_text": f"{opp['title']} is available",
                    "requires_evidence": True,
                    "evidence_ids": opp.get("evidence_ids", []),
                    "confidence": 0.85,
                }
            )

        sources = {o.get("source", "") for o in ranked}
        summary = (
            f"Found {len(ranked)} opportunities across {len(sources)} sources."
        )

        return {
            "ranked_opportunities": ranked,
            "claims": claims,
            "summary": summary,
            "errors": state.get("errors", []),
        }
