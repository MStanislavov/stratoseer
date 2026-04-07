"""DataFormatter agent: converts raw search results into structured DTOs."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from app.agents.base import LLMAgent
from app.agents.schemas import DataFormatterOutput

logger = logging.getLogger(__name__)


# -- Dedup helpers ----------------------------------------------------------


def _dedup_key(item: BaseModel) -> str:
    """Build a dedup key from title + distinguishing field."""
    title = getattr(item, "title", "")
    for attr in ("company", "provider", "platform", "organizer", "url"):
        val = getattr(item, attr, None)
        if val:
            return f"{title}||{val}"
    return title


def _dedup(items: list[BaseModel]) -> list[dict]:
    """Deduplicate keeping first occurrence per (title + company/provider/url)."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = _dedup_key(item)
        if key not in seen:
            seen.add(key)
            out.append(item.model_dump())
    return out


# -- Recovery: deterministic fallback for dropped items ---------------------

# Maps (raw_state_key, subtitle_field) for each category
_CATEGORY_MAP = {
    "jobs": ("raw_job_results", "company"),
    "certifications": ("raw_cert_results", "provider"),
    "courses": ("raw_course_results", "platform"),
    "events": ("raw_event_results", "organizer"),
    "groups": ("raw_group_results", "platform"),
    "trends": ("raw_trend_results", "source"),
}


def _raw_to_formatted(raw: dict[str, Any], subtitle_field: str) -> dict[str, Any]:
    """Convert a raw search result to a formatted dict without LLM."""
    return {
        "title": raw.get("title", "Untitled"),
        subtitle_field: raw.get("source"),
        "url": raw.get("url"),
        "description": raw.get("snippet"),
    }


def _recover_missing(
    formatted: list[dict],
    raw_items: list[dict],
    subtitle_field: str,
    category: str,
) -> list[dict]:
    """Append any raw items the LLM dropped, using deterministic field mapping."""
    if len(formatted) >= len(raw_items):
        return formatted

    formatted_urls = {item.get("url") for item in formatted if item.get("url")}
    formatted_titles = {item.get("title", "").lower() for item in formatted}

    recovered = list(formatted)
    for raw in raw_items:
        url = raw.get("url", "")
        title = raw.get("title", "").lower()
        if url and url in formatted_urls:
            continue
        if title and title in formatted_titles:
            continue
        recovered.append(_raw_to_formatted(raw, subtitle_field))
        logger.warning(
            "data_formatter: recovered dropped %s item: %s",
            category,
            raw.get("title", "?"),
        )

    return recovered


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
        result, usage = await self._invoke_structured(
            DataFormatterOutput, system_prompt, user_content
        )

        raw_by_category = {
            "jobs": raw_jobs,
            "certifications": raw_certs,
            "courses": raw_courses,
            "events": raw_events,
            "groups": raw_groups,
            "trends": raw_trends,
        }
        llm_by_category = {
            "jobs": _dedup(result.jobs),
            "certifications": _dedup(result.certifications),
            "courses": _dedup(result.courses),
            "events": _dedup(result.events),
            "groups": _dedup(result.groups),
            "trends": _dedup(result.trends),
        }

        output: dict[str, Any] = {}
        for cat, (_, subtitle_field) in _CATEGORY_MAP.items():
            formatted = llm_by_category[cat]
            raw = raw_by_category[cat]
            output[f"formatted_{cat}"] = _recover_missing(formatted, raw, subtitle_field, cat)

        output["_token_usage"] = [usage] if usage else []
        return output
