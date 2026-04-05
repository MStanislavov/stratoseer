"""WebScraper agent: LLM-powered web search with structured output."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.agents.base import LLMAgent
from app.agents.schemas import FilteredURL, WebScraperOutput, WebScraperResult

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
        fetch_tool: Any | None = None,
        max_steps: int = 5,
    ):
        super().__init__(llm=llm, prompt_loader=prompt_loader)
        self._search_tool = search_tool
        self._fetch_tool = fetch_tool
        self._max_steps = max_steps

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
            usages: list[dict] = []
            tools = []
            tool_map: dict[str, Any] = {}
            if self._search_tool is not None:
                tools.append(self._search_tool)
                tool_map[self._search_tool.name] = self._search_tool
            if self._fetch_tool is not None:
                tools.append(self._fetch_tool)
                tool_map[self._fetch_tool.name] = self._fetch_tool

            if tools:
                llm_with_tools = self._llm.bind_tools(tools)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
                model_name = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "")
                response = await llm_with_tools.ainvoke(messages)
                if getattr(response, "usage_metadata", None):
                    u = dict(response.usage_metadata)
                    u["model_name"] = model_name
                    usages.append(u)
                messages.append(response)

                # Process tool calls until the LLM stops or max_steps reached
                step = 0
                while response.tool_calls and step < self._max_steps:
                    step += 1
                    for tool_call in response.tool_calls:
                        tool = tool_map.get(tool_call["name"])
                        if tool is None:
                            logger.warning("Unknown tool call: %s", tool_call["name"])
                            messages.append({
                                "role": "tool",
                                "content": f"Unknown tool: {tool_call['name']}",
                                "tool_call_id": tool_call["id"],
                            })
                            continue
                        tool_result = await tool.ainvoke(tool_call["args"])
                        messages.append({
                            "role": "tool",
                            "content": str(tool_result),
                            "tool_call_id": tool_call["id"],
                        })
                    response = await llm_with_tools.ainvoke(messages)
                    if getattr(response, "usage_metadata", None):
                        u = dict(response.usage_metadata)
                        u["model_name"] = model_name
                        usages.append(u)
                    messages.append(response)

                search_context = response.content or ""

            # Parse the final response as structured output
            structured_input = (
                f"Search for: {prompt}\n\nSearch results found:\n{search_context}"
                if search_context
                else user_content
            )
            result, structured_usage = await self._invoke_structured(
                WebScraperOutput, system_prompt, structured_input
            )
            if structured_usage:
                usages.append(structured_usage)

            # Deduplicate by URL -- keep first occurrence, move dupes to filtered
            seen_urls: set[str] = set()
            unique_results: list[WebScraperResult] = []
            for r in result.results:
                if r.url and r.url in seen_urls:
                    result.filtered_urls.append(FilteredURL(url=r.url, reason="duplicate URL"))
                else:
                    if r.url:
                        seen_urls.add(r.url)
                    unique_results.append(r)
            results = [r.model_dump() for r in unique_results]
            filtered = [f.model_dump() for f in result.filtered_urls]
            output: dict[str, Any] = {result_key: results, "_token_usage": usages}
            if filtered:
                output[f"filtered_{category}_urls"] = filtered
                for f in filtered:
                    logger.info("WebScraper (%s) filtered %s: %s", category, f["url"], f["reason"])
            return output

        except Exception as exc:
            logger.warning("WebScraper failed for %s: %s", category, exc)
            return {result_key: [], "errors": [f"WebScraper ({category}): {exc}"]}

