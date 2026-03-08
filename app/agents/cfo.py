"""Mock CFO agent: provides risk and ROI assessment on ranked opportunities."""

from __future__ import annotations

from typing import Any


class CFOAgent:
    """Phase-1 mock CFO planner. Produces risk/ROI assessments for the
    top-ranked opportunities. No retrieval; structured inputs only.

    Swappable for a real LLM-backed agent later.
    """

    agent_name = "cfo"

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        opportunities = state.get("ranked_opportunities", [])

        assessments: list[dict[str, Any]] = []
        for opp in opportunities[:5]:
            opp_type = opp.get("opportunity_type", "unknown")
            assessments.append(
                {
                    "opportunity_title": opp["title"],
                    "risk_level": "low" if opp_type == "cert" else "medium",
                    "time_investment": "40 hours" if opp_type == "cert" else "ongoing",
                    "roi_estimate": "high",
                }
            )

        return {
            "risk_assessment": assessments,
            "errors": state.get("errors", []),
        }
