"""DataFormatter agent: converts raw search results into structured DTOs."""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import LLMAgent
from pydantic import BaseModel

from app.agents.schemas import DataFormatterOutput


def _dedup(items: list[BaseModel]) -> list[dict]:
    """Deduplicate by title, keeping the first occurrence."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        title = getattr(item, "title", "")
        if title not in seen:
            seen.add(title)
            out.append(item.model_dump())
    return out


class DataFormatterAgent(LLMAgent):
    """Normalizes raw search results into structured DTOs for each category."""

    agent_name = "data_formatter"

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Format raw search results from all categories into structured DTOs."""
        raw_jobs = state.get("raw_job_results", [])
        raw_certs = state.get("raw_cert_results", [])
        raw_courses = state.get("raw_course_results", [])
        raw_events = state.get("raw_event_results", [])
        raw_groups = state.get("raw_group_results", [])
        raw_trends = state.get("raw_trend_results", [])

        system_prompt = self._get_system_prompt()
        user_content = (
            f"Raw job results:\n{json.dumps(raw_jobs, indent=2)}\n\n"
            f"Raw certification results:\n{json.dumps(raw_certs, indent=2)}\n\n"
            f"Raw course results:\n{json.dumps(raw_courses, indent=2)}\n\n"
            f"Raw event results:\n{json.dumps(raw_events, indent=2)}\n\n"
            f"Raw group results:\n{json.dumps(raw_groups, indent=2)}\n\n"
            f"Raw trend results:\n{json.dumps(raw_trends, indent=2)}"
        )
        result, usage = await self._invoke_structured(DataFormatterOutput, system_prompt, user_content)
        return {
            "formatted_jobs": _dedup(result.jobs),
            "formatted_certifications": _dedup(result.certifications),
            "formatted_courses": _dedup(result.courses),
            "formatted_events": _dedup(result.events),
            "formatted_groups": _dedup(result.groups),
            "formatted_trends": _dedup(result.trends),
            "_token_usage": [usage] if usage else [],
        }

