"""Content validator: deterministic validation of URLs from raw results."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.llm.url_fetch_tool import URLFetchTool

logger = logging.getLogger(__name__)


# -- Schemas --

class URLValidationItem(BaseModel):
    """Validation result for a single URL."""

    url: str = Field(description="The URL that was validated")
    valid: bool = Field(description="True if the content is still active and relevant")
    reason: str = Field(default="", description="Brief reason if invalid")


class URLValidationOutput(BaseModel):
    """Structured output from the content validator with per-URL validity flags."""

    results: list[URLValidationItem] = Field(default_factory=list)


# -- Constants --

_CATEGORIES = [
    ("job", "raw_job_results"),
    ("cert", "raw_cert_results"),
    ("course", "raw_course_results"),
    ("event", "raw_event_results"),
    ("group", "raw_group_results"),
    ("trend", "raw_trend_results"),
]

_MIN_BODY_CHARS = 1000

_INVALID_PHRASES: dict[str, list[str]] = {
    "job": [
        "no longer accepting applications",
        "this job is no longer available",
        "this job has expired",
        "this position has been filled",
        "this listing has expired",
        "this job posting has been removed",
        "sorry, this job is no longer available",
        "the job you are looking for is no longer available",
        "this position is no longer open",
        "job has been closed",
        "this job is closed",
        "this position has expired",
        "job expired",
        "This job post is closed",
    ],
    "cert": [
        "this certification has been discontinued",
        "this program is no longer offered",
        "no longer available",
        "certification not found",
    ],
    "course": [
        "this course has been retired",
        "no longer available",
        "this program is no longer offered",
        "course not found",
    ],
    "event": [
        "past event",
        "this event ended",
        "event ended",
        "this event has ended",
        "this event has passed",
        "registration is closed",
        "event is over",
        "this event already took place",
        "registration has ended",
        "this event is no longer available",
    ],
    "group": [
        "this community has been archived",
        "this group has been deleted",
        "this subreddit is private",
        "this community is banned",
    ],
    "trend": [],
}

_LINKEDIN_ACTUAL_PAGE_MARKERS = [
    "use ai to assess how you fit",
    "am i a good fit for this job",
    "sign in to evaluate your skills",
    "sign in to tailor your resume",
]


class ContentValidator:
    """Deterministic content validator -- no LLM, pure phrase/content checks.

    Fetches each URL and applies rules:
    - HTTP 404 or fetch error -> invalid
    - Body below _MIN_BODY_CHARS -> invalid
    - Body contains a category-specific invalid phrase -> invalid
    - Otherwise -> valid
    """

    agent_name = "content_validator"

    def __init__(self, fetch_tool: URLFetchTool | None = None):
        self._fetch_tool = fetch_tool

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        all_items: list[tuple[str, str, dict[str, Any]]] = []
        for category, key in _CATEGORIES:
            for item in state.get(key, []):
                all_items.append((category, key, item))

        if not all_items:
            return {}

        if self._fetch_tool is None:
            return {}

        fetch_tool = self._fetch_tool
        tasks = [fetch_tool.ainvoke(item.get("url", "")) for _, _, item in all_items]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

        invalid_results: list[URLValidationItem] = []
        valid_by_key: dict[str, list[dict[str, Any]]] = {}
        for (category, key, item), raw in zip(all_items, fetched):
            url = item.get("url", "")
            result: URLValidationItem = _check_content(url, category, raw)
            if result.valid:
                valid_by_key.setdefault(key, []).append(item)
            else:
                logger.info("Content validator flagged %s as invalid: %s", url, result.reason)
                invalid_results.append(result)

        # Include web scraper filtered URLs in the validation results
        for category, _ in _CATEGORIES:
            for f in state.get(f"filtered_{category}_urls", []):
                invalid_results.append(URLValidationItem(
                    url=f.get("url", ""),
                    valid=False,
                    reason=f.get("reason", "filtered by web scraper"),
                ))

        updates: dict[str, Any] = {
            "url_validation_results": [r.model_dump() for r in invalid_results],
        }
        for _, key in _CATEGORIES:
            original = state.get(key, [])
            filtered = valid_by_key.get(key, [])
            if len(filtered) != len(original):
                updates[key] = filtered

        return updates


def _check_content(url: str, category: str, raw: Any) -> URLValidationItem:
    """Apply deterministic rules to fetched content."""
    if isinstance(raw, Exception):
        return URLValidationItem(url=url, valid=False, reason=f"fetch error: {raw}")

    text = str(raw)

    if text.startswith("Fetch error:"):
        return URLValidationItem(url=url, valid=False, reason=text)

    # Parse HTTP status
    status, body = extract_http_body_and_status(text)

    if status == 403:
        return URLValidationItem(url=url, valid=True)

    if status == 404 or status == 400:
        return URLValidationItem(url=url, valid=False, reason=f"HTTP {status} - page unavailable - {url}")

    if status < 200 or status > 299:
        return URLValidationItem(url=url, valid=False, reason=f"HTTP {status} - unknown error - {url}")

    if len(body) < _MIN_BODY_CHARS and (category == "job" or category == "event"):
        return URLValidationItem(url=url, valid=False, reason=f"insufficient content - {url}")

    body_lower = body.lower()
    for phrase in _INVALID_PHRASES.get(category, []):
        if phrase in body_lower:
            return URLValidationItem(url=url, valid=False, reason=phrase)

    return URLValidationItem(url=url, valid=True)


def extract_http_body_and_status(text: str) -> tuple[int, str]:
    status = 0
    body = text
    if text.startswith("HTTP "):
        parts = text.split("\n\n", 1)
        try:
            status = int(parts[0].split()[1])
        except (IndexError, ValueError):
            pass
        body = parts[1] if len(parts) > 1 else ""
    return status, body
