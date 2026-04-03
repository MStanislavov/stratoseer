"""WebScraper agent: LLM-powered web search with structured output."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.agents.base import LLMAgent
from app.agents.schemas import WebScraperOutput

logger = logging.getLogger(__name__)


class WebScraperAgent(LLMAgent):
    """Searches the web via an LLM with a bound search tool.

    Binds the search tool to the LLM and uses a tool-calling loop
    to find and return structured results.
    """

    agent_name = "web_scraper"

    def __init__(
        self,
        llm: Any | None = None,
        prompt_loader: Any | None = None,
        search_tool: Any | None = None,
    ):
        super().__init__(llm=llm, prompt_loader=prompt_loader)
        self._search_tool = search_tool

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute a web search for the given category and return raw results."""
        prompt = state.get("search_prompt", "")
        category = state.get("search_category", "")
        result_key = f"raw_{category}_results"

        try:
            today = date.today().isoformat()
            prompt_name = f"web_scraper/{category}" if category else "web_scraper/job"
            system_prompt = (
                self._prompt_loader.load(prompt_name, today=today)
                if self._prompt_loader
                else f"You are a helpful web search agent."
            )
            user_content = f"Search for: {prompt}"

            search_context = ""
            if self._search_tool is not None:
                # Tool-calling loop: bind search tool to LLM
                llm_with_tools = self._llm.bind_tools([self._search_tool])
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
                response = await llm_with_tools.ainvoke(messages)
                messages.append(response)

                # Process tool calls until the LLM returns a final response
                while response.tool_calls:
                    for tool_call in response.tool_calls:
                        tool_result = await self._search_tool.ainvoke(
                            tool_call["args"]
                        )
                        messages.append({
                            "role": "tool",
                            "content": str(tool_result),
                            "tool_call_id": tool_call["id"],
                        })
                    response = await llm_with_tools.ainvoke(messages)
                    messages.append(response)

                search_context = response.content or ""

            # Parse the final response as structured output
            structured_input = (
                f"Search for: {prompt}\n\nSearch results found:\n{search_context}"
                if search_context
                else user_content
            )
            result = await self._invoke_structured(
                WebScraperOutput, system_prompt, structured_input
            )
            results = [r.model_dump() for r in result.results]
            return {result_key: results}

        except Exception as exc:
            logger.warning("WebScraper failed for %s: %s", category, exc)
            return {result_key: [], "errors": [f"WebScraper ({category}): {exc}"]}

