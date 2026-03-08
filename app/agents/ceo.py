"""Mock CEO agent: provides strategic recommendations on ranked opportunities."""

from __future__ import annotations

from typing import Any


class CEOAgent:
    """Phase-1 mock CEO planner. Produces strategic alignment recommendations
    for the top-ranked opportunities. No retrieval; structured inputs only.

    Swappable for a real LLM-backed agent later.
    """

    agent_name = "ceo"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        opportunities = state.get("ranked_opportunities", [])

        recommendations: list[dict[str, Any]] = []
        for opp in opportunities[:5]:  # Top 5
            opp_type = opp.get("opportunity_type", "unknown")
            recommendations.append(
                {
                    "opportunity_title": opp["title"],
                    "strategic_alignment": "high" if opp_type == "job" else "medium",
                    "recommendation": f"Pursue {opp['title']} - aligns with career growth targets",
                    "priority": "high",
                }
            )

        return {
            "strategic_recommendations": recommendations,
            "errors": state.get("errors", []),
        }
