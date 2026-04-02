"""URL Validator agent: uses LLM + URL fetch tool to validate URLs from raw results."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.agents.base import LLMAgent
from app.agents.schemas import URLValidationOutput
from app.llm.url_fetch_tool import URLFetchTool

logger = logging.getLogger(__name__)

_CATEGORIES = [
    ("job", "raw_job_results"),
    ("cert", "raw_cert_results"),
    ("event", "raw_event_results"),
    ("group", "raw_group_results"),
    ("trend", "raw_trend_results"),
]


class URLValidatorAgent(LLMAgent):
    """Validates URLs from raw scraper results using LLM + URL fetch tool.

    In mock mode (llm=None), passes all results through unchanged.
    In live mode, gives the LLM the URLs + categories and a fetch tool
    so it can open each URL and judge whether the content is still valid.
    """

    agent_name = "url_validator"

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._llm is None:
            return {}

        try:
            today = date.today().isoformat()
            system_prompt = self._get_system_prompt(today=today)

            # Collect all results with their URLs
            all_items: list[tuple[str, str, dict[str, Any]]] = []
            for category, key in _CATEGORIES:
                for item in state.get(key, []):
                    all_items.append((category, key, item))

            if not all_items:
                return {}

            # Build user input: just URLs, titles, and categories
            lines: list[str] = []
            for i, (category, _, item) in enumerate(all_items, 1):
                lines.append(
                    f"{i}. [{category.upper()}] {item.get('title', 'Untitled')}\n"
                    f"   URL: {item.get('url', 'N/A')}"
                )
            user_content = (
                f"Validate these {len(all_items)} URLs. "
                f"Use the fetch_url tool to open each URL and check its content.\n\n"
                + "\n".join(lines)
            )

            # Tool-calling loop: LLM fetches URLs via the fetch tool
            fetch_tool = URLFetchTool()
            llm_with_tools = self._llm.bind_tools([fetch_tool])
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            while response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_result = await fetch_tool.ainvoke(tool_call["args"])
                    messages.append({
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_call_id": tool_call["id"],
                    })
                response = await llm_with_tools.ainvoke(messages)
                messages.append(response)

            validation_context = response.content or ""

            # Structured output: get validity verdicts
            structured_input = (
                f"{user_content}\n\nValidation findings:\n{validation_context}"
                if validation_context
                else user_content
            )
            result = await self._invoke_structured(
                URLValidationOutput, system_prompt, structured_input
            )

            # Build set of invalid URLs
            invalid_urls = {r.url for r in result.results if not r.valid}

            if invalid_urls:
                logger.info(
                    "URL validator flagged %d invalid result(s): %s",
                    len(invalid_urls),
                    [r.reason for r in result.results if not r.valid],
                )

            # Filter each category
            updates: dict[str, Any] = {}
            for _, key in _CATEGORIES:
                original = state.get(key, [])
                filtered = [r for r in original if r.get("url", "") not in invalid_urls]
                if len(filtered) != len(original):
                    updates[key] = filtered

            return updates

        except Exception as exc:
            logger.warning("URL validator failed: %s", exc)
            return {}
