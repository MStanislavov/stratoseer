"""DuckDuckGo search tool that explicitly excludes Wikipedia/Grokipedia engines."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import Field, model_validator

logger = logging.getLogger(__name__)

# Engines to never use (encyclopedia-style, not real web search;
# the "auto" backend in ddgs v8 hits wt.wikipedia.org which is unreachable)
_BLOCKED_ENGINES = frozenset({"wikipedia", "grokipedia"})

# Preferred engine order: Google first for best results, then DuckDuckGo
_PREFERRED_ORDER = ["google", "duckduckgo", "brave", "yahoo", "mojeek", "yandex"]


class SafeDuckDuckGoSearchTool(BaseTool):
    """Web search via DuckDuckGo that skips Wikipedia/Grokipedia engines.

    duckduckgo-search v8 prioritises Wikipedia as the first text engine
    in ``backend="auto"``, which hits unreliable regional Wikipedia
    subdomains (e.g. ``wt.wikipedia.org`` for region ``wt-wt``).
    This tool builds an explicit backend list from all available engines
    minus the blocked ones so Wikipedia is never contacted.
    """

    name: str = "duckduckgo_search"
    description: str = (
        "Search the web using DuckDuckGo. "
        "Input should be a search query string."
    )
    max_results: int = Field(default=10, description="Max results to return")
    region: str = Field(default="wt-wt", description="Search region")
    timelimit: str = Field(default="", description="Time filter: d (day), w (week), m (month), y (year)")
    _backend: str = ""

    @model_validator(mode="after")
    def _resolve_backends(self) -> "SafeDuckDuckGoSearchTool":
        from ddgs.engines import ENGINES

        available = set(ENGINES.get("text", {})) - _BLOCKED_ENGINES
        ordered = [e for e in _PREFERRED_ORDER if e in available]
        # Append any new engines not in our preferred list
        ordered += sorted(available - set(ordered))
        self._backend = ",".join(ordered)
        logger.info("SafeDuckDuckGoSearchTool backends: %s", self._backend)
        return self

    def _run(self, query: str) -> str:
        from ddgs import DDGS

        try:
            kwargs: dict[str, Any] = dict(
                region=self.region,
                safesearch="moderate",
                max_results=self.max_results,
                backend=self._backend,
            )
            if self.timelimit:
                kwargs["timelimit"] = self.timelimit
            with DDGS() as ddgs:
                results = ddgs.text(query, **kwargs)
            if not results:
                return "No good DuckDuckGo Search Result was found"
            return "\n\n".join(
                f"Title: {r.get('title', '')}\nURL: {r.get('href', '')}\nSnippet: {r.get('body', '')}"
                for r in results
            )
        except Exception as exc:
            logger.warning("DuckDuckGo search error: %s", exc)
            return f"Search error: {exc}"

    async def _arun(self, query: str) -> str:
        return await asyncio.to_thread(self._run, query)
