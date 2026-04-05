"""WebScraper agent: LLM-powered web search with structured output."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from app.agents.base import LLMAgent
from app.agents.schemas import FilteredURL, WebScraperOutput, WebScraperResult

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = (
    "You are extracting search results into structured JSON. "
    "Put ALL relevant URLs found during searching into the `results` array. "
    "IMPORTANT: Only include URLs that point to specific individual pages "
    "(e.g. a single job listing, a single event page, a single course page). "
    "Do NOT include search result pages, directory listings, or homepage URLs. "
    "Put exact duplicates or clearly unrelated URLs into `filtered_urls`."
)

# URL patterns that indicate a search/directory page rather than a specific listing
_DIRECTORY_PATTERNS: dict[str, list[str]] = {
    "job": [
        "linkedin.com/jobs/search",
        "linkedin.com/jobs/?",
    ],
}

# URL patterns that a valid listing MUST match (if set for category)
_REQUIRED_URL_PATTERNS: dict[str, list[str]] = {
    "job": ["/jobs/view/"],
}

# ANSI colors per scraper category for log output
_CATEGORY_COLORS: dict[str, str] = {
    "job": "\033[34m",           # blue
    "cert": "\033[35m",          # magenta
    "course": "\033[36m",        # cyan
    "event": "\033[33m",         # yellow
    "group": "\033[32m",         # green
    "trend": "\033[37m",         # white
}
_RESET = "\033[0m"

_FETCH_BATCH_SIZE = 2
_FETCH_BATCH_DELAY = 1.5   # seconds between batches
_RETRY_BACKOFF = 3.0        # seconds before retrying 429s


def _cat_tag(category: str) -> str:
    color = _CATEGORY_COLORS.get(category, "")
    return f"{color}[{category}]{_RESET}"


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
        category_max_steps: dict[str, int] | None = None,
        category_min_searches: dict[str, int] | None = None,
        category_min_results: dict[str, int] | None = None,
    ):
        super().__init__(llm=llm, prompt_loader=prompt_loader)
        self._search_tool = search_tool
        self._fetch_tool = fetch_tool
        self._max_steps = max_steps
        self._category_max_steps = category_max_steps or {}
        self._category_min_searches = category_min_searches or {}
        self._category_min_results = category_min_results or {}

    # ------------------------------------------------------------------
    # Helper: process one batch of tool calls from an LLM response
    # ------------------------------------------------------------------

    async def _handle_tool_calls(
        self,
        response: Any,
        messages: list,
        tool_map: dict[str, Any],
        search_tool_name: str,
        category: str,
        step: int,
    ) -> int:
        """Process all tool calls in *response*, appending results to *messages*.

        Returns the number of search-tool calls executed in this batch.
        """
        batch_searches = 0
        for tool_call in response.tool_calls:
            try:
                tc_name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", None)
                tc_id = tool_call.get("id") if isinstance(tool_call, dict) else getattr(tool_call, "id", None)
                tc_args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                if not tc_name or not tc_id:
                    logger.warning("Malformed tool_call (type=%s): %s", type(tool_call).__name__, str(tool_call)[:200])
                    continue
                if tc_name == search_tool_name:
                    batch_searches += 1
                tool = tool_map.get(tc_name)
                if tool is None:
                    logger.warning("Unknown tool call: %s", tc_name)
                    messages.append({
                        "role": "tool",
                        "content": f"Unknown tool: {tc_name}",
                        "tool_call_id": tc_id,
                    })
                    continue
                tool_result = await tool.ainvoke(tc_args)
                messages.append({
                    "role": "tool",
                    "content": str(tool_result),
                    "tool_call_id": tc_id,
                })
            except Exception:
                logger.exception("Tool call failed in %s (step %d)", category, step)
                tc_id_safe = tc_id if tc_id else "unknown"
                messages.append({
                    "role": "tool",
                    "content": "Tool execution error, please continue with other searches.",
                    "tool_call_id": tc_id_safe,
                })
        return batch_searches

    # ------------------------------------------------------------------
    # Helper: validate URLs by fetching them and applying deterministic rules
    # ------------------------------------------------------------------

    async def _validate_urls(
        self,
        results: list[WebScraperResult],
        category: str,
    ) -> tuple[list[WebScraperResult], list[FilteredURL]]:
        """Fetch all result URLs and validate content.

        Returns (valid_results, rejected_as_FilteredURL).
        """
        if not self._fetch_tool or not results:
            return results, []

        rejected: list[FilteredURL] = []

        # Phase 1: reject by URL pattern (no network needed)
        pattern_survivors: list[WebScraperResult] = []
        for item in results:
            if not item.url:
                pattern_survivors.append(item)
                continue
            reason = _check_url_pattern(item.url, category)
            if reason:
                logger.info("%s rejected: %s -- %s", _cat_tag(category), item.url, reason)
                rejected.append(FilteredURL(url=item.url, reason=reason))
            else:
                pattern_survivors.append(item)

        # Phase 2: fetch surviving URLs in small batches to avoid 429s
        fetched: list[str | Exception] = []
        for i in range(0, len(pattern_survivors), _FETCH_BATCH_SIZE):
            batch = pattern_survivors[i:i + _FETCH_BATCH_SIZE]
            batch_results = await asyncio.gather(
                *[self._fetch_tool.ainvoke(item.url) for item in batch],
                return_exceptions=True,
            )
            fetched.extend(batch_results)
            if i + _FETCH_BATCH_SIZE < len(pattern_survivors):
                await asyncio.sleep(_FETCH_BATCH_DELAY)

        valid: list[WebScraperResult] = []
        rate_limited: list[WebScraperResult] = []
        for item, raw in zip(pattern_survivors, fetched):
            if not item.url:
                valid.append(item)
                continue
            reason = _check_fetched_content(item.url, category, raw)
            if reason == "HTTP 429":
                rate_limited.append(item)
            elif reason:
                logger.info("%s rejected: %s -- %s", _cat_tag(category), item.url, reason)
                rejected.append(FilteredURL(url=item.url, reason=reason))
            else:
                valid.append(item)
                logger.info("%s valid: %s", _cat_tag(category), item.url)

        # Retry 429s up to 3 times with increasing backoff
        for attempt in range(1, 4):
            if not rate_limited:
                break
            backoff = _RETRY_BACKOFF * attempt
            logger.info(
                "%s retrying %d rate-limited URLs (attempt %d/3, %.1fs backoff)",
                _cat_tag(category), len(rate_limited), attempt, backoff,
            )
            await asyncio.sleep(backoff)
            retry_fetched: list[str | Exception] = []
            for i in range(0, len(rate_limited), _FETCH_BATCH_SIZE):
                batch = rate_limited[i:i + _FETCH_BATCH_SIZE]
                batch_results = await asyncio.gather(
                    *[self._fetch_tool.ainvoke(item.url) for item in batch],
                    return_exceptions=True,
                )
                retry_fetched.extend(batch_results)
                if i + _FETCH_BATCH_SIZE < len(rate_limited):
                    await asyncio.sleep(_FETCH_BATCH_DELAY)
            still_limited: list[WebScraperResult] = []
            for item, raw in zip(rate_limited, retry_fetched):
                reason = _check_fetched_content(item.url, category, raw)
                if reason == "HTTP 429":
                    still_limited.append(item)
                elif reason:
                    logger.info("%s rejected (attempt %d): %s -- %s", _cat_tag(category), attempt, item.url, reason)
                    rejected.append(FilteredURL(url=item.url, reason=reason))
                else:
                    valid.append(item)
                    logger.info("%s valid (attempt %d): %s", _cat_tag(category), attempt, item.url)
            rate_limited = still_limited

        # Any still rate-limited after 3 retries are rejected
        for item in rate_limited:
            logger.info("%s rejected (still 429 after 3 retries): %s", _cat_tag(category), item.url)
            rejected.append(FilteredURL(url=item.url, reason="HTTP 429 after 3 retries"))

        logger.info(
            "%s URL validation: %d valid, %d rejected out of %d",
            _cat_tag(category), len(valid), len(rejected), len(results),
        )
        return valid, rejected

    # ------------------------------------------------------------------
    # Helper: run the tool-calling loop until budget or minimums are met
    # ------------------------------------------------------------------

    async def _run_tool_loop(
        self,
        response: Any,
        messages: list,
        llm_with_tools: Any,
        tool_map: dict[str, Any],
        model_name: str,
        usages: list[dict],
        category: str,
        max_steps: int,
        min_searches: int,
        step: int = 0,
        search_count: int = 0,
    ) -> tuple[Any, int, int]:
        """Run the tool-calling loop, nudging the LLM if it stops too early.

        Returns (final_response, total_search_count, total_steps).
        """
        search_tool_name = self._search_tool.name if self._search_tool else ""

        while step < max_steps:
            if not response.tool_calls:
                if search_count >= min_searches or min_searches == 0:
                    break
                logger.info(
                    "%s nudging LLM: %d/%d searches done",
                    _cat_tag(category), search_count, min_searches,
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"You have only completed {search_count} out of "
                        f"{min_searches} required searches. You MUST continue "
                        f"searching with different query variations. Do not "
                        f"summarize or stop -- call the search tool now."
                    ),
                })
                response = await llm_with_tools.ainvoke(messages)
                if getattr(response, "usage_metadata", None):
                    usages.append({**dict(response.usage_metadata), "model_name": model_name})
                messages.append(response)
                if not response.tool_calls:
                    logger.warning(
                        "%s LLM refused to continue after nudge "
                        "(%d/%d searches)", _cat_tag(category), search_count, min_searches,
                    )
                    break

            step += 1
            search_count += await self._handle_tool_calls(
                response, messages, tool_map, search_tool_name, category, step,
            )
            response = await llm_with_tools.ainvoke(messages)
            if getattr(response, "usage_metadata", None):
                usages.append({**dict(response.usage_metadata), "model_name": model_name})
            messages.append(response)

        return response, search_count, step

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute a web search for the given category and return raw results."""
        prompt = state.get("search_prompt", "")
        category = state.get("search_category", "")
        result_key = f"raw_{category}_results"

        try:
            today = date.today().isoformat()
            year = str(date.today().year)
            prompt_name = f"web_scraper/{category}" if category else "web_scraper/job"
            system_prompt = (
                self._prompt_loader.load(prompt_name, today=today, year=year)
                if self._prompt_loader
                else "You are a helpful web search agent."
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

            max_steps = self._category_max_steps.get(category, self._max_steps)
            min_searches = self._category_min_searches.get(category, 0)
            min_results = self._category_min_results.get(category, 0)

            messages: list[Any] = []
            llm_with_tools = None
            model_name = ""
            step = 0
            search_count = 0

            if tools:
                llm_with_tools = self._llm.bind_tools(tools)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
                model_name = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "")
                response = await llm_with_tools.ainvoke(messages)
                if getattr(response, "usage_metadata", None):
                    usages.append({**dict(response.usage_metadata), "model_name": model_name})
                messages.append(response)

                response, search_count, step = await self._run_tool_loop(
                    response, messages, llm_with_tools, tool_map,
                    model_name, usages, category, max_steps, min_searches,
                )

                logger.info(
                    "%s finished tool loop: %d searches, %d steps",
                    _cat_tag(category), search_count, step,
                )
                search_context = response.content or ""

            # Parse the final response as structured output
            structured_input = (
                f"Search for: {prompt}\n\nSearch results found:\n{search_context}"
                if search_context
                else user_content
            )
            result, structured_usage = await self._invoke_structured(
                WebScraperOutput, _EXTRACTION_PROMPT, structured_input
            )
            if structured_usage:
                usages.append(structured_usage)

            # Deduplicate by URL -- keep first occurrence, move dupes to filtered
            seen_urls: set[str] = set()
            unique_results: list[WebScraperResult] = []
            all_filtered: list[FilteredURL] = list(result.filtered_urls)
            for r in result.results:
                if r.url and r.url in seen_urls:
                    all_filtered.append(FilteredURL(url=r.url, reason="duplicate URL"))
                else:
                    if r.url:
                        seen_urls.add(r.url)
                    unique_results.append(r)

            # ---- URL validation via fetch ----
            validated, rejected = await self._validate_urls(unique_results, category)
            unique_results = validated
            all_filtered.extend(rejected)

            # ---- min_results enforcement ----
            # If we don't have enough valid results and still have budget,
            # nudge the LLM back into search mode and re-parse.
            result_retry = 0
            while (
                min_results
                and len(unique_results) < min_results
                and result_retry < 3
                and step < max_steps
                and llm_with_tools is not None
            ):
                result_retry += 1
                logger.info(
                    "%s only %d/%d valid results, "
                    "continuing search (retry %d)",
                    _cat_tag(category), len(unique_results), min_results, result_retry,
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"You found only {len(unique_results)} valid results but "
                        f"the minimum required is {min_results}. Search for more "
                        f"with different query terms and job boards. Call the "
                        f"search tool now."
                    ),
                })
                response = await llm_with_tools.ainvoke(messages)
                if getattr(response, "usage_metadata", None):
                    usages.append({**dict(response.usage_metadata), "model_name": model_name})
                messages.append(response)

                if not response.tool_calls:
                    logger.warning(
                        "%s LLM refused to search more "
                        "(%d/%d results, retry %d)",
                        _cat_tag(category), len(unique_results), min_results, result_retry,
                    )
                    break

                # Continue the tool-calling loop
                response, search_count, step = await self._run_tool_loop(
                    response, messages, llm_with_tools, tool_map,
                    model_name, usages, category, max_steps, 0,
                    step=step, search_count=search_count,
                )
                search_context = response.content or ""

                # Re-parse and merge new results
                structured_input = (
                    f"Search for: {prompt}\n\nSearch results found:\n{search_context}"
                )
                new_result, structured_usage = await self._invoke_structured(
                    WebScraperOutput, _EXTRACTION_PROMPT, structured_input
                )
                if structured_usage:
                    usages.append(structured_usage)
                new_unique: list[WebScraperResult] = []
                for r in new_result.results:
                    if r.url and r.url in seen_urls:
                        all_filtered.append(FilteredURL(url=r.url, reason="duplicate URL"))
                    else:
                        if r.url:
                            seen_urls.add(r.url)
                        new_unique.append(r)
                all_filtered.extend(new_result.filtered_urls)

                # Validate new URLs via fetch
                new_valid, new_rejected = await self._validate_urls(new_unique, category)
                unique_results.extend(new_valid)
                all_filtered.extend(new_rejected)

            tag = _cat_tag(category)
            logger.info(
                "%s final: %d valid results, %d filtered, "
                "%d searches, %d steps",
                tag, len(unique_results), len(all_filtered),
                search_count, step,
            )
            for r in unique_results:
                logger.info("%s  -> %s  %s", tag, r.title, r.url or "")

            results = [r.model_dump() for r in unique_results]
            filtered = [f.model_dump() for f in all_filtered]
            output: dict[str, Any] = {result_key: results, "_token_usage": usages}
            if filtered:
                output[f"filtered_{category}_urls"] = filtered
                for f in filtered:
                    logger.info("%s filtered %s: %s", tag, f["url"], f["reason"])
            return output

        except Exception as exc:
            logger.exception("%s failed", _cat_tag(category))
            return {result_key: [], "errors": [f"WebScraper ({category}): {exc}"]}


# ------------------------------------------------------------------
# Module-level validation helpers
# ------------------------------------------------------------------


def _check_url_pattern(url: str, category: str) -> str:
    """Return a rejection reason if the URL matches a known directory/search pattern."""
    url_lower = url.lower()

    # Check directory/search page patterns
    for pattern in _DIRECTORY_PATTERNS.get(category, []):
        if pattern in url_lower:
            return f"search/directory page ({pattern})"

    # Check required URL patterns (e.g., jobs must have /jobs/view/)
    required = _REQUIRED_URL_PATTERNS.get(category)
    if required and not any(p in url_lower for p in required):
        return f"URL does not match required pattern for {category}"

    return ""


def _check_fetched_content(url: str, category: str, raw: Any) -> str:
    """Apply deterministic content rules to fetched page content."""
    if isinstance(raw, Exception):
        return f"fetch error: {raw}"

    text = str(raw)
    if text.startswith("Fetch error:"):
        return text

    status, body = extract_http_body_and_status(text)

    # 403 = login wall, treat as valid (LinkedIn does this for real listings)
    if status == 403:
        return ""

    if status == 404 or status == 400:
        return f"HTTP {status} - page unavailable"

    if status and (status < 200 or status > 299):
        return f"HTTP {status}"

    if len(body) < _MIN_BODY_CHARS and category == "job":
        return "insufficient content"

    body_lower = body.lower()
    for phrase in _INVALID_PHRASES.get(category, []):
        if phrase.lower() in body_lower:
            return phrase

    return ""
