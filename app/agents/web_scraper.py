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
    "event": [
        "meetup.com/topics/",
        "/search?",
        "/search/?",
        "lu.ma/discover",
    ],
}

# URL patterns that a valid listing MUST match (if set for category)
_REQUIRED_URL_PATTERNS: dict[str, list[str]] = {
    "job": ["/jobs/view/"],
}

# ANSI colors per scraper category for log output
_CATEGORY_COLORS: dict[str, str] = {
    "job": "\033[34m",  # blue
    "cert": "\033[35m",  # magenta
    "course": "\033[36m",  # cyan
    "event": "\033[33m",  # yellow
    "group": "\033[32m",  # green
    "trend": "\033[37m",  # white
}
_RESET = "\033[0m"

_FETCH_BATCH_SIZE = 2
_FETCH_BATCH_DELAY = 1.5  # seconds between batches
_RETRY_BACKOFF = 3.0  # seconds before retrying 429s


def _cat_tag(category: str) -> str:
    color = _CATEGORY_COLORS.get(category, "")
    return f"{color}[{category}]{_RESET}"


_MIN_BODY_CHARS = 1000

_INVALID_PHRASES: dict[str, list[str]] = {
    "job": [
        "no longer accepting applications",
        "this job is no longer available",
        "this job has expired",
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
        "no events found",
        "no results found",
        "0 results",
        "no upcoming events",
        "there are no upcoming events",
        "no events match",
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
    """Parse an HTTP response string into its status code and body content.

    Args:
        text: Raw HTTP response text, optionally prefixed with "HTTP <status>".

    Returns:
        A tuple of (status_code, body) where status_code is 0 if no HTTP prefix
        is found.
    """
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
        mode_category_budgets: dict[str, dict[str, int]] | None = None,
    ):
        """Initialize the WebScraperAgent with tools and budget configuration.

        Args:
            llm: The ChatOpenAI (or compatible) LLM instance for generating queries.
            prompt_loader: Loader for system prompt templates.
            search_tool: LangChain tool for performing web searches.
            fetch_tool: Tool for fetching and reading URL content.
            max_steps: Maximum number of tool-calling loop iterations.
            mode_category_budgets: Per-mode, per-category budget overrides keyed
                as "mode:category" (e.g. "daily:job").
        """
        super().__init__(llm=llm, prompt_loader=prompt_loader)
        self._search_tool = search_tool
        self._fetch_tool = fetch_tool
        self._max_steps = max_steps
        self._mode_category_budgets = mode_category_budgets or {}

    def _resolve_budgets(self, mode: str, category: str) -> tuple[int, int, int]:
        """Return (max_steps, min_searches, min_results) for a mode+category."""
        budgets = self._mode_category_budgets.get(f"{mode}:{category}", {})
        return (
            budgets.get("max_steps", self._max_steps),
            budgets.get("min_searches", 0),
            budgets.get("min_results", 0),
        )

    # ------------------------------------------------------------------
    # Helper: extract name, id, args from a tool_call (dict or object)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tool_call(tool_call: Any) -> tuple[str | None, str | None, dict]:
        """Extract (name, id, args) from a tool_call which may be a dict or object."""
        if isinstance(tool_call, dict):
            return tool_call.get("name"), tool_call.get("id"), tool_call.get("args", {})
        return (
            getattr(tool_call, "name", None),
            getattr(tool_call, "id", None),
            getattr(tool_call, "args", {}),
        )

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
                tc_name, tc_id, tc_args = self._parse_tool_call(tool_call)
                if not tc_name or not tc_id:
                    logger.warning(
                        "Malformed tool_call (type=%s): %s",
                        type(tool_call).__name__,
                        str(tool_call)[:200],
                    )
                    continue
                if tc_name == search_tool_name:
                    batch_searches += 1
                tool = tool_map.get(tc_name)
                if tool is None:
                    logger.warning("Unknown tool call: %s", tc_name)
                    messages.append(
                        {
                            "role": "tool",
                            "content": f"Unknown tool: {tc_name}",
                            "tool_call_id": tc_id,
                        }
                    )
                    continue
                tool_result = await tool.ainvoke(tc_args)
                messages.append(
                    {
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_call_id": tc_id,
                    }
                )
            except Exception:
                logger.exception("Tool call failed in %s (step %d)", category, step)
                tc_id_safe = tc_id if tc_id else "unknown"
                messages.append(
                    {
                        "role": "tool",
                        "content": "Tool execution error, please continue with other searches.",
                        "tool_call_id": tc_id_safe,
                    }
                )
        return batch_searches

    # ------------------------------------------------------------------
    # Helper: phase-1 URL pattern filtering (no network)
    # ------------------------------------------------------------------

    def _filter_by_url_pattern(
        self,
        results: list[WebScraperResult],
        category: str,
    ) -> tuple[list[WebScraperResult], list[FilteredURL]]:
        """Reject results whose URL matches a known directory/search pattern.

        Returns (survivors, rejected_as_FilteredURL).
        """
        survivors: list[WebScraperResult] = []
        rejected: list[FilteredURL] = []
        for item in results:
            if not item.url:
                survivors.append(item)
                continue
            reason = _check_url_pattern(item.url, category)
            if reason:
                logger.info("%s rejected: %s -- %s", _cat_tag(category), item.url, reason)
                rejected.append(FilteredURL(url=item.url, reason=reason))
            else:
                survivors.append(item)
        return survivors, rejected

    # ------------------------------------------------------------------
    # Helper: phase-2 async fetch + content classification
    # ------------------------------------------------------------------

    async def _fetch_and_classify_urls(
        self,
        items: list[WebScraperResult],
        category: str,
        attempt_label: str = "",
    ) -> tuple[list[WebScraperResult], list[WebScraperResult], list[FilteredURL]]:
        """Fetch URLs and classify them as valid, rate-limited, or rejected.

        Returns (valid, rate_limited, rejected_as_FilteredURL).
        """
        fetched: list[str | Exception] = []
        for i in range(0, len(items), _FETCH_BATCH_SIZE):
            batch = items[i : i + _FETCH_BATCH_SIZE]
            batch_results = await asyncio.gather(
                *[self._fetch_tool.ainvoke(item.url) for item in batch],
                return_exceptions=True,
            )
            fetched.extend(batch_results)
            if i + _FETCH_BATCH_SIZE < len(items):
                await asyncio.sleep(_FETCH_BATCH_DELAY)

        valid: list[WebScraperResult] = []
        rate_limited: list[WebScraperResult] = []
        rejected: list[FilteredURL] = []
        for item, raw in zip(items, fetched):
            if not item.url:
                valid.append(item)
                continue
            reason = _check_fetched_content(category, raw)
            if reason == "HTTP 429":
                rate_limited.append(item)
            elif reason:
                logger.info(
                    "%s rejected%s: %s -- %s",
                    _cat_tag(category),
                    attempt_label,
                    item.url,
                    reason,
                )
                rejected.append(FilteredURL(url=item.url, reason=reason))
            else:
                valid.append(item)
                logger.info("%s valid%s: %s", _cat_tag(category), attempt_label, item.url)
        return valid, rate_limited, rejected

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

        # Phase 1: reject by URL pattern (no network needed)
        pattern_survivors, rejected = self._filter_by_url_pattern(results, category)

        # Phase 2: fetch surviving URLs and classify
        valid, rate_limited, fetch_rejected = await self._fetch_and_classify_urls(
            pattern_survivors,
            category,
        )
        rejected.extend(fetch_rejected)

        # Retry 429s up to 3 times with increasing backoff
        for attempt in range(1, 4):
            if not rate_limited:
                break
            backoff = _RETRY_BACKOFF * attempt
            logger.info(
                "%s retrying %d rate-limited URLs (attempt %d/3, %.1fs backoff)",
                _cat_tag(category),
                len(rate_limited),
                attempt,
                backoff,
            )
            await asyncio.sleep(backoff)
            retry_valid, still_limited, retry_rejected = await self._fetch_and_classify_urls(
                rate_limited,
                category,
                attempt_label=f" (attempt {attempt})",
            )
            valid.extend(retry_valid)
            rejected.extend(retry_rejected)
            rate_limited = still_limited

        # Any still rate-limited after 3 retries are rejected
        for item in rate_limited:
            logger.info("%s rejected (still 429 after 3 retries): %s", _cat_tag(category), item.url)
            rejected.append(FilteredURL(url=item.url, reason="HTTP 429 after 3 retries"))

        logger.info(
            "%s URL validation: %d valid, %d rejected out of %d",
            _cat_tag(category),
            len(valid),
            len(rejected),
            len(results),
        )
        return valid, rejected

    # ------------------------------------------------------------------
    # Helper: nudge the LLM when it stops before reaching min_searches
    # ------------------------------------------------------------------

    async def _nudge_for_more_searches(
        self,
        messages: list,
        category: str,
        search_count: int,
        min_searches: int,
        llm_with_tools: Any,
        usages: list[dict],
    ) -> Any:
        """Append a nudge message and re-invoke the LLM.

        Returns the new LLM response (caller checks for tool_calls).
        """
        logger.info(
            "%s nudging LLM: %d/%d searches done",
            _cat_tag(category),
            search_count,
            min_searches,
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"You have only completed {search_count} out of "
                    f"{min_searches} required searches. You MUST continue "
                    f"searching with different query variations. Do not "
                    f"summarize or stop -- call the search tool now."
                ),
            }
        )
        response = await llm_with_tools.ainvoke(messages)
        if getattr(response, "usage_metadata", None):
            usages.append({**dict(response.usage_metadata), "model_name": self._model_name})
        messages.append(response)
        if not response.tool_calls:
            logger.warning(
                "%s LLM refused to continue after nudge (%d/%d searches)",
                _cat_tag(category),
                search_count,
                min_searches,
            )
        return response

    # ------------------------------------------------------------------
    # Helper: run the tool-calling loop until budget or minimums are met
    # ------------------------------------------------------------------

    async def _run_tool_loop(
        self,
        response: Any,
        messages: list,
        llm_with_tools: Any,
        tool_map: dict[str, Any],
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
                response = await self._nudge_for_more_searches(
                    messages,
                    category,
                    search_count,
                    min_searches,
                    llm_with_tools,
                    usages,
                )
                if not response.tool_calls:
                    break

            step += 1
            search_count += await self._handle_tool_calls(
                response,
                messages,
                tool_map,
                search_tool_name,
                category,
                step,
            )
            response = await llm_with_tools.ainvoke(messages)
            if getattr(response, "usage_metadata", None):
                usages.append({**dict(response.usage_metadata), "model_name": self._model_name})
            messages.append(response)

        return response, search_count, step

    # ------------------------------------------------------------------
    # Helper: parse structured output and deduplicate by URL
    # ------------------------------------------------------------------

    async def _parse_and_deduplicate(
        self,
        result_text: str,
        seen_urls: set[str],
        prompt: str,
        usages: list[dict],
    ) -> tuple[list[WebScraperResult], list[FilteredURL]]:
        """Parse search results into structured output and deduplicate.

        Returns (unique_results, filtered_urls). Updates *seen_urls* in place.
        """
        structured_input = (
            f"Search for: {prompt}\n\nSearch results found:\n{result_text}"
            if result_text
            else prompt
        )
        result, structured_usage = await self._invoke_structured(
            WebScraperOutput, _EXTRACTION_PROMPT, structured_input
        )
        if structured_usage:
            usages.append(structured_usage)

        unique: list[WebScraperResult] = []
        filtered: list[FilteredURL] = list(result.filtered_urls)
        for r in result.results:
            if r.url and r.url in seen_urls:
                filtered.append(FilteredURL(url=r.url, reason="duplicate URL"))
            else:
                if r.url:
                    seen_urls.add(r.url)
                unique.append(r)
        return unique, filtered

    # ------------------------------------------------------------------
    # Helper: retry loop when insufficient valid results
    # ------------------------------------------------------------------

    async def _retry_insufficient_results(
        self,
        unique_results: list[WebScraperResult],
        all_filtered: list[FilteredURL],
        seen_urls: set[str],
        messages: list[Any],
        llm_with_tools: Any,
        tool_map: dict[str, Any],
        usages: list[dict],
        category: str,
        prompt: str,
        min_results: int,
        max_steps: int,
        step: int,
        search_count: int,
    ) -> tuple[list[WebScraperResult], list[FilteredURL], int, int]:
        """Keep searching until min_results are met or budget is exhausted.

        Mutates *unique_results*, *all_filtered*, *seen_urls*.
        Returns (unique_results, all_filtered, search_count, step).
        """
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
                "%s only %d/%d valid results, continuing search (retry %d)",
                _cat_tag(category),
                len(unique_results),
                min_results,
                result_retry,
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"You found only {len(unique_results)} valid results but "
                        f"the minimum required is {min_results}. Search for more "
                        f"with different query terms and job boards. Call the "
                        f"search tool now."
                    ),
                }
            )
            response = await llm_with_tools.ainvoke(messages)
            if getattr(response, "usage_metadata", None):
                usages.append({**dict(response.usage_metadata), "model_name": self._model_name})
            messages.append(response)

            if not response.tool_calls:
                logger.warning(
                    "%s LLM refused to search more (%d/%d results, retry %d)",
                    _cat_tag(category),
                    len(unique_results),
                    min_results,
                    result_retry,
                )
                break

            # Continue the tool-calling loop
            response, search_count, step = await self._run_tool_loop(
                response,
                messages,
                llm_with_tools,
                tool_map,
                usages,
                category,
                max_steps,
                0,
                step=step,
                search_count=search_count,
            )
            search_context = response.content or ""

            # Re-parse and merge new results
            new_unique, new_filtered = await self._parse_and_deduplicate(
                search_context,
                seen_urls,
                prompt,
                usages,
            )
            all_filtered.extend(new_filtered)

            # Validate new URLs via fetch
            new_valid, new_rejected = await self._validate_urls(new_unique, category)
            unique_results.extend(new_valid)
            all_filtered.extend(new_rejected)

        return unique_results, all_filtered, search_count, step

    # ------------------------------------------------------------------
    # Helper: assemble the final output dict
    # ------------------------------------------------------------------

    def _build_output(
        self,
        unique_results: list[WebScraperResult],
        all_filtered: list[FilteredURL],
        usages: list[dict],
        category: str,
        result_key: str,
        search_count: int,
        step: int,
    ) -> dict[str, Any]:
        """Log final statistics and return the output dict."""
        tag = _cat_tag(category)
        logger.info(
            "%s final: %d valid results, %d filtered, %d searches, %d steps",
            tag,
            len(unique_results),
            len(all_filtered),
            search_count,
            step,
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
            mode = state.get("pipeline_mode", "weekly")
            max_steps, min_searches, min_results = self._resolve_budgets(mode, category)

            user_content = prompt

            if min_results:
                user_content += f"\n\nYou must find at least {min_results} results."
            if min_searches:
                user_content += f" Execute at least {min_searches} distinct search queries."

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

            messages: list[Any] = []
            llm_with_tools = None
            step = 0
            search_count = 0

            if tools:
                llm_with_tools = self._llm.bind_tools(tools)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
                response = await llm_with_tools.ainvoke(messages)
                if getattr(response, "usage_metadata", None):
                    usages.append({**dict(response.usage_metadata), "model_name": self._model_name})
                messages.append(response)

                response, search_count, step = await self._run_tool_loop(
                    response,
                    messages,
                    llm_with_tools,
                    tool_map,
                    usages,
                    category,
                    max_steps,
                    min_searches,
                )

                logger.info(
                    "%s finished tool loop: %d searches, %d steps",
                    _cat_tag(category),
                    search_count,
                    step,
                )
                search_context = response.content or ""

            # Parse and deduplicate
            seen_urls: set[str] = set()
            unique_results, all_filtered = await self._parse_and_deduplicate(
                search_context,
                seen_urls,
                user_content,
                usages,
            )

            # URL validation via fetch
            validated, rejected = await self._validate_urls(unique_results, category)
            unique_results = validated
            all_filtered.extend(rejected)

            # min_results enforcement
            (
                unique_results,
                all_filtered,
                search_count,
                step,
            ) = await self._retry_insufficient_results(
                unique_results,
                all_filtered,
                seen_urls,
                messages,
                llm_with_tools,
                tool_map,
                usages,
                category,
                prompt,
                min_results,
                max_steps,
                step,
                search_count,
            )

            return self._build_output(
                unique_results,
                all_filtered,
                usages,
                category,
                result_key,
                search_count,
                step,
            )

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


def _check_fetched_content(category: str, raw: Any) -> str:
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

    if len(body) < _MIN_BODY_CHARS and category in ("job", "event"):
        return "insufficient content"

    body_lower = body.lower()
    for phrase in _INVALID_PHRASES.get(category, []):
        if phrase.lower() in body_lower:
            return phrase

    return ""
