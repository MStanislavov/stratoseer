"""Tests for the WebScraperAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.schemas import FilteredURL, WebScraperOutput, WebScraperResult
from app.agents.web_scraper import (
    _MIN_BODY_CHARS,
    WebScraperAgent,
    _check_fetched_content,
    _check_url_pattern,
    extract_http_body_and_status,
)

# ---------------------------------------------------------------------------
# Helpers to build mock LLM responses
# ---------------------------------------------------------------------------


def _make_ai_message(
    content: str = "",
    tool_calls: list | None = None,
    usage: dict | None = None,
):
    """Return a MagicMock that looks like an AIMessage."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.usage_metadata = usage or {"input_tokens": 10, "output_tokens": 5}
    return msg


def _make_search_tool(name: str = "web_search"):
    tool = AsyncMock()
    tool.name = name
    tool.ainvoke = AsyncMock(return_value="search result text")
    return tool


def _make_fetch_tool(name: str = "url_fetch"):
    tool = AsyncMock()
    tool.name = name
    tool.ainvoke = AsyncMock(return_value="HTTP 200 OK\n\n" + "x" * 2000)
    return tool


def _make_structured_result(
    results: list[WebScraperResult] | None = None,
    filtered: list[FilteredURL] | None = None,
    usage: dict | None = None,
):
    """Return (parsed_output, usage) as _invoke_structured would."""
    parsed = WebScraperOutput(
        results=results or [],
        filtered_urls=filtered or [],
    )
    return parsed, usage


def _make_llm(model_name: str = "gpt-test"):
    llm = MagicMock()
    llm.model_name = model_name
    llm.bind_tools = MagicMock()
    llm.with_structured_output = MagicMock()
    return llm


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestExtractHttpBodyAndStatus:
    def test_plain_text_returns_zero_status(self):
        status, body = extract_http_body_and_status("just some text")
        assert status == 0
        assert body == "just some text"

    def test_http_prefix_parses_status(self):
        status, body = extract_http_body_and_status("HTTP 200 OK\n\npage body")
        assert status == 200
        assert body == "page body"

    def test_http_404(self):
        status, body = extract_http_body_and_status("HTTP 404 Not Found\n\n")
        assert status == 404
        assert body == ""

    def test_http_malformed_status(self):
        status, body = extract_http_body_and_status("HTTP \n\nbody")
        assert status == 0
        assert body == "body"

    def test_http_no_double_newline(self):
        status, body = extract_http_body_and_status("HTTP 200 OK")
        assert status == 200
        assert body == ""


class TestCheckUrlPattern:
    def test_no_match_returns_empty(self):
        assert _check_url_pattern("https://example.com/jobs/view/123", "job") == ""

    def test_directory_pattern_rejects(self):
        reason = _check_url_pattern("https://linkedin.com/jobs/search?q=python", "job")
        assert "search/directory page" in reason

    def test_required_pattern_rejects_missing(self):
        reason = _check_url_pattern("https://linkedin.com/some-page", "job")
        assert "does not match required pattern" in reason

    def test_event_directory_pattern(self):
        reason = _check_url_pattern("https://lu.ma/discover", "event")
        assert "search/directory page" in reason

    def test_unknown_category_passes(self):
        assert _check_url_pattern("https://example.com/anything", "trend") == ""

    def test_case_insensitive(self):
        reason = _check_url_pattern("https://LinkedIn.com/Jobs/Search?q=py", "job")
        assert reason != ""


class TestCheckFetchedContent:
    def test_exception_returns_fetch_error(self):
        reason = _check_fetched_content("job", RuntimeError("timeout"))
        assert "fetch error" in reason

    def test_fetch_error_text(self):
        reason = _check_fetched_content("job", "Fetch error: connection refused")
        assert reason == "Fetch error: connection refused"

    def test_http_403_treated_as_valid(self):
        assert _check_fetched_content("job", "HTTP 403 Forbidden\n\nlogin wall") == ""

    def test_http_404_rejected(self):
        reason = _check_fetched_content("job", "HTTP 404 Not Found\n\n")
        assert "HTTP 404" in reason

    def test_http_400_rejected(self):
        reason = _check_fetched_content("job", "HTTP 400 Bad Request\n\n")
        assert "HTTP 400" in reason

    def test_http_500_rejected(self):
        reason = _check_fetched_content("job", "HTTP 500 Server Error\n\nbody")
        assert "HTTP 500" in reason

    def test_http_429_rate_limited(self):
        reason = _check_fetched_content("job", "HTTP 429 Too Many Requests\n\n")
        assert reason == "HTTP 429"

    def test_insufficient_content_for_job(self):
        short_body = "HTTP 200 OK\n\n" + "x" * 10
        reason = _check_fetched_content("job", short_body)
        assert reason == "insufficient content"

    def test_sufficient_content_for_job(self):
        long_body = "HTTP 200 OK\n\n" + "x" * (_MIN_BODY_CHARS + 1)
        assert _check_fetched_content("job", long_body) == ""

    def test_insufficient_content_ignored_for_cert(self):
        short_body = "HTTP 200 OK\n\nshort"
        assert _check_fetched_content("cert", short_body) == ""

    def test_invalid_phrase_detected(self):
        body = "HTTP 200 OK\n\n" + "x" * 2000 + " no longer accepting applications"
        reason = _check_fetched_content("job", body)
        assert reason == "no longer accepting applications"

    def test_event_invalid_phrase(self):
        body = "This event has ended. Please check back later."
        reason = _check_fetched_content("event", body)
        assert reason != ""

    def test_valid_200_with_no_phrase_passes(self):
        body = "HTTP 200 OK\n\n" + "x" * 2000 + " a valid job listing"
        assert _check_fetched_content("job", body) == ""

    def test_plain_text_no_status(self):
        body = "x" * 2000
        assert _check_fetched_content("job", body) == ""


# ---------------------------------------------------------------------------
# WebScraperAgent unit tests
# ---------------------------------------------------------------------------


class TestWebScraperAgentInit:
    def test_default_init(self):
        llm = _make_llm()
        agent = WebScraperAgent(llm=llm)
        assert agent.agent_name == "web_scraper"
        assert agent._max_steps == 5
        assert agent._search_tool is None
        assert agent._fetch_tool is None
        assert agent._mode_category_budgets == {}

    def test_custom_init(self):
        llm = _make_llm()
        search = _make_search_tool()
        fetch = _make_fetch_tool()
        budgets = {"weekly:job": {"max_steps": 10, "min_searches": 3, "min_results": 5}}
        agent = WebScraperAgent(
            llm=llm,
            search_tool=search,
            fetch_tool=fetch,
            max_steps=8,
            mode_category_budgets=budgets,
        )
        assert agent._max_steps == 8
        assert agent._search_tool is search
        assert agent._fetch_tool is fetch
        assert agent._mode_category_budgets == budgets

    def test_model_name_from_llm(self):
        llm = _make_llm("gpt-test-model")
        agent = WebScraperAgent(llm=llm)
        assert agent._model_name == "gpt-test-model"


class TestResolveBudgets:
    def test_returns_defaults_when_no_budgets(self):
        agent = WebScraperAgent(llm=_make_llm(), max_steps=7)
        steps, searches, results = agent._resolve_budgets("weekly", "job")
        assert steps == 7
        assert searches == 0
        assert results == 0

    def test_returns_custom_budgets(self):
        budgets = {"weekly:job": {"max_steps": 10, "min_searches": 3, "min_results": 5}}
        agent = WebScraperAgent(llm=_make_llm(), mode_category_budgets=budgets)
        steps, searches, results = agent._resolve_budgets("weekly", "job")
        assert steps == 10
        assert searches == 3
        assert results == 5

    def test_partial_budgets_fill_defaults(self):
        budgets = {"daily:cert": {"min_searches": 2}}
        agent = WebScraperAgent(llm=_make_llm(), max_steps=6, mode_category_budgets=budgets)
        steps, searches, results = agent._resolve_budgets("daily", "cert")
        assert steps == 6
        assert searches == 2
        assert results == 0


class TestParseToolCall:
    def test_dict_tool_call(self):
        tc = {"name": "web_search", "id": "call_1", "args": {"query": "test"}}
        name, tc_id, args = WebScraperAgent._parse_tool_call(tc)
        assert name == "web_search"
        assert tc_id == "call_1"
        assert args == {"query": "test"}

    def test_object_tool_call(self):
        tc = MagicMock()
        tc.name = "url_fetch"
        tc.id = "call_2"
        tc.args = {"url": "https://example.com"}
        name, tc_id, args = WebScraperAgent._parse_tool_call(tc)
        assert name == "url_fetch"
        assert tc_id == "call_2"
        assert args == {"url": "https://example.com"}

    def test_dict_missing_keys(self):
        tc = {}
        name, tc_id, args = WebScraperAgent._parse_tool_call(tc)
        assert name is None
        assert tc_id is None
        assert args == {}


class TestHandleToolCalls:
    @pytest.fixture()
    def agent(self):
        llm = _make_llm()
        search = _make_search_tool()
        return WebScraperAgent(llm=llm, search_tool=search)

    async def test_processes_search_tool_call(self, agent):
        search = agent._search_tool
        tool_map = {search.name: search}
        response = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "c1", "args": {"query": "python jobs"}},
            ]
        )
        messages = []
        count = await agent._handle_tool_calls(
            response,
            messages,
            tool_map,
            "web_search",
            "job",
            1,
        )
        assert count == 1
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "c1"
        search.ainvoke.assert_awaited_once_with({"query": "python jobs"})

    async def test_unknown_tool_appends_error_message(self, agent):
        tool_map = {}
        response = _make_ai_message(
            tool_calls=[
                {"name": "unknown_tool", "id": "c2", "args": {}},
            ]
        )
        messages = []
        count = await agent._handle_tool_calls(
            response,
            messages,
            tool_map,
            "web_search",
            "job",
            1,
        )
        assert count == 0
        assert "Unknown tool" in messages[0]["content"]

    async def test_malformed_tool_call_skipped(self, agent):
        tool_map = {}
        response = _make_ai_message(
            tool_calls=[
                {"args": {"query": "test"}},  # missing name and id
            ]
        )
        messages = []
        count = await agent._handle_tool_calls(
            response,
            messages,
            tool_map,
            "web_search",
            "job",
            1,
        )
        assert count == 0
        assert len(messages) == 0

    async def test_tool_execution_error_appends_error_message(self, agent):
        search = agent._search_tool
        search.ainvoke = AsyncMock(side_effect=RuntimeError("network error"))
        tool_map = {search.name: search}
        response = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "c3", "args": {"query": "test"}},
            ]
        )
        messages = []
        count = await agent._handle_tool_calls(
            response,
            messages,
            tool_map,
            "web_search",
            "job",
            1,
        )
        assert count == 1
        assert "Tool execution error" in messages[0]["content"]

    async def test_multiple_tool_calls_counted(self, agent):
        search = agent._search_tool
        tool_map = {search.name: search}
        response = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "c1", "args": {"query": "q1"}},
                {"name": "web_search", "id": "c2", "args": {"query": "q2"}},
            ]
        )
        messages = []
        count = await agent._handle_tool_calls(
            response,
            messages,
            tool_map,
            "web_search",
            "job",
            1,
        )
        assert count == 2
        assert len(messages) == 2


class TestFilterByUrlPattern:
    @pytest.fixture()
    def agent(self):
        return WebScraperAgent(llm=_make_llm())

    def test_valid_urls_survive(self, agent):
        results = [
            WebScraperResult(title="Job", url="https://linkedin.com/jobs/view/123"),
        ]
        survivors, rejected = agent._filter_by_url_pattern(results, "job")
        assert len(survivors) == 1
        assert len(rejected) == 0

    def test_directory_urls_rejected(self, agent):
        results = [
            WebScraperResult(title="Search", url="https://linkedin.com/jobs/search?q=py"),
        ]
        survivors, rejected = agent._filter_by_url_pattern(results, "job")
        assert len(survivors) == 0
        assert len(rejected) == 1
        assert "search/directory page" in rejected[0].reason

    def test_empty_url_survives(self, agent):
        results = [WebScraperResult(title="No URL")]
        survivors, rejected = agent._filter_by_url_pattern(results, "job")
        assert len(survivors) == 1
        assert len(rejected) == 0

    def test_mixed_results(self, agent):
        results = [
            WebScraperResult(title="Valid", url="https://linkedin.com/jobs/view/1"),
            WebScraperResult(title="Invalid", url="https://linkedin.com/jobs/search?q=x"),
            WebScraperResult(title="Also Invalid", url="https://example.com/no-view"),
        ]
        survivors, rejected = agent._filter_by_url_pattern(results, "job")
        assert len(survivors) == 1
        assert len(rejected) == 2


class TestFetchAndClassifyUrls:
    @pytest.fixture()
    def agent(self):
        fetch = _make_fetch_tool()
        return WebScraperAgent(llm=_make_llm(), fetch_tool=fetch)

    async def test_valid_urls_classified(self, agent):
        items = [WebScraperResult(title="Job", url="https://example.com/job/1")]
        valid, rate_limited, rejected = await agent._fetch_and_classify_urls(
            items,
            "cert",
        )
        assert len(valid) == 1
        assert len(rate_limited) == 0
        assert len(rejected) == 0

    async def test_404_rejected(self, agent):
        agent._fetch_tool.ainvoke = AsyncMock(return_value="HTTP 404 Not Found\n\n")
        items = [WebScraperResult(title="Gone", url="https://example.com/gone")]
        valid, _, rejected = await agent._fetch_and_classify_urls(
            items,
            "cert",
        )
        assert len(valid) == 0
        assert len(rejected) == 1

    async def test_429_rate_limited(self, agent):
        agent._fetch_tool.ainvoke = AsyncMock(
            return_value="HTTP 429 Too Many Requests\n\n",
        )
        items = [WebScraperResult(title="Limited", url="https://example.com/slow")]
        valid, rate_limited, rejected = await agent._fetch_and_classify_urls(
            items,
            "cert",
        )
        assert len(valid) == 0
        assert len(rate_limited) == 1
        assert len(rejected) == 0

    async def test_empty_url_goes_to_valid(self, agent):
        items = [WebScraperResult(title="No URL", url="")]
        valid, _, _ = await agent._fetch_and_classify_urls(
            items,
            "cert",
        )
        assert len(valid) == 1

    async def test_fetch_exception_rejected(self, agent):
        agent._fetch_tool.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        items = [WebScraperResult(title="Err", url="https://example.com/err")]
        valid, _, rejected = await agent._fetch_and_classify_urls(
            items,
            "cert",
        )
        assert len(valid) == 0
        assert len(rejected) == 1
        assert "fetch error" in rejected[0].reason

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_batching_with_delay(self, mock_sleep, agent):
        items = [
            WebScraperResult(title=f"Item {i}", url=f"https://example.com/{i}") for i in range(4)
        ]
        valid, _, _ = await agent._fetch_and_classify_urls(items, "cert")
        assert len(valid) == 4
        # With batch size 2 and 4 items, sleep is called once (between first and second batch)
        assert mock_sleep.await_count == 1


class TestValidateUrls:
    @pytest.fixture()
    def agent(self):
        fetch = _make_fetch_tool()
        return WebScraperAgent(llm=_make_llm(), fetch_tool=fetch)

    async def test_returns_unchanged_when_no_fetch_tool(self):
        agent = WebScraperAgent(llm=_make_llm(), fetch_tool=None)
        results = [WebScraperResult(title="Job", url="https://example.com")]
        valid, rejected = await agent._validate_urls(results, "cert")
        assert valid == results
        assert rejected == []

    async def test_returns_unchanged_when_empty_results(self, agent):
        valid, rejected = await agent._validate_urls([], "cert")
        assert valid == []
        assert rejected == []

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_url_pattern_and_fetch_combined(self, mock_sleep, agent):
        results = [
            WebScraperResult(title="Valid", url="https://example.com/cert/1"),
            WebScraperResult(title="Search", url="https://linkedin.com/jobs/search?q=x"),
        ]
        valid, rejected = await agent._validate_urls(results, "job")
        # "Valid" lacks /jobs/view/ so is rejected by required pattern check;
        # "Search" matches the directory pattern. Both are rejected.
        assert len(valid) == 0
        assert len(rejected) == 2

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_retry(self, mock_sleep):
        fetch = _make_fetch_tool()
        # First call returns 429, second call returns 200
        fetch.ainvoke = AsyncMock(
            side_effect=[
                "HTTP 429 Too Many Requests\n\n",
                "HTTP 200 OK\n\n" + "x" * 2000,
            ]
        )
        agent = WebScraperAgent(llm=_make_llm(), fetch_tool=fetch)
        results = [WebScraperResult(title="Retried", url="https://example.com/retry")]
        valid, rejected = await agent._validate_urls(results, "cert")
        assert len(valid) == 1
        assert len(rejected) == 0

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_exhausted_after_3_retries(self, mock_sleep):
        fetch = _make_fetch_tool()
        # Always returns 429
        fetch.ainvoke = AsyncMock(return_value="HTTP 429 Too Many Requests\n\n")
        agent = WebScraperAgent(llm=_make_llm(), fetch_tool=fetch)
        results = [WebScraperResult(title="Never OK", url="https://example.com/stuck")]
        valid, rejected = await agent._validate_urls(results, "cert")
        assert len(valid) == 0
        assert len(rejected) == 1
        assert "429 after 3 retries" in rejected[0].reason


class TestNudgeForMoreSearches:
    @pytest.fixture()
    def agent(self):
        llm = _make_llm()
        search = _make_search_tool()
        return WebScraperAgent(llm=llm, search_tool=search)

    async def test_nudge_appends_message_and_invokes(self, agent):
        llm_with_tools = AsyncMock()
        response_msg = _make_ai_message(
            tool_calls=[{"name": "web_search", "id": "n1", "args": {"query": "more"}}],
        )
        llm_with_tools.ainvoke = AsyncMock(return_value=response_msg)

        messages = []
        usages = []
        result = await agent._nudge_for_more_searches(
            messages,
            "job",
            1,
            3,
            llm_with_tools,
            usages,
        )
        assert result is response_msg
        # Nudge adds a user message + appends the response
        assert any(m.get("role") == "user" for m in messages if isinstance(m, dict))
        assert len(usages) == 1

    async def test_nudge_no_usage_metadata(self, agent):
        llm_with_tools = AsyncMock()
        msg = _make_ai_message(tool_calls=[])
        msg.usage_metadata = None
        llm_with_tools.ainvoke = AsyncMock(return_value=msg)

        usages = []
        await agent._nudge_for_more_searches(
            [],
            "job",
            0,
            2,
            llm_with_tools,
            usages,
        )
        assert len(usages) == 0

    async def test_nudge_llm_refuses(self, agent):
        llm_with_tools = AsyncMock()
        msg = _make_ai_message(tool_calls=[])
        llm_with_tools.ainvoke = AsyncMock(return_value=msg)

        result = await agent._nudge_for_more_searches(
            [],
            "job",
            0,
            2,
            llm_with_tools,
            [],
        )
        assert result.tool_calls == []


class TestRunToolLoop:
    @pytest.fixture()
    def agent(self):
        llm = _make_llm()
        search = _make_search_tool()
        return WebScraperAgent(llm=llm, search_tool=search)

    async def test_no_tool_calls_exits_immediately(self, agent):
        response = _make_ai_message(tool_calls=[])
        llm_with_tools = AsyncMock()
        messages = []
        usages = []

        final, search_count, step = await agent._run_tool_loop(
            response,
            messages,
            llm_with_tools,
            {},
            usages,
            "job",
            5,
            0,
        )
        assert final is response
        assert search_count == 0
        assert step == 0

    async def test_single_tool_call_step(self, agent):
        search = agent._search_tool
        tool_map = {search.name: search}

        # First response has tool calls, second does not
        first_response = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "t1", "args": {"query": "test"}},
            ]
        )
        second_response = _make_ai_message(content="Final results", tool_calls=[])

        llm_with_tools = AsyncMock()
        llm_with_tools.ainvoke = AsyncMock(return_value=second_response)
        messages = []
        usages = []

        final, search_count, step = await agent._run_tool_loop(
            first_response,
            messages,
            llm_with_tools,
            tool_map,
            usages,
            "job",
            5,
            0,
        )
        assert final is second_response
        assert search_count == 1
        assert step == 1

    async def test_max_steps_limit_enforced(self, agent):
        search = agent._search_tool
        tool_map = {search.name: search}

        # Always return tool calls to keep looping
        always_tool = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "t1", "args": {"query": "loop"}},
            ]
        )
        llm_with_tools = AsyncMock()
        llm_with_tools.ainvoke = AsyncMock(return_value=always_tool)

        _, _, steps = await agent._run_tool_loop(
            always_tool,
            [],
            llm_with_tools,
            tool_map,
            [],
            "job",
            3,
            0,
        )
        assert steps == 3

    async def test_nudge_when_below_min_searches(self, agent):
        search = agent._search_tool
        tool_map = {search.name: search}

        # First response has no tool calls (below min_searches=2)
        no_tools = _make_ai_message(content="done", tool_calls=[])

        # Flow:
        # 1. nudge -> ainvoke returns with_tools (has tool calls)
        # 2. handle tool calls (1 search), ainvoke returns final_resp (no tool calls)
        # 3. search_count=1 < min_searches=2, nudge again -> ainvoke returns refuse
        with_tools = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "n1", "args": {"query": "nudge query"}},
            ]
        )
        final_resp = _make_ai_message(content="now done", tool_calls=[])
        refuse = _make_ai_message(content="no more", tool_calls=[])

        llm_with_tools = AsyncMock()
        llm_with_tools.ainvoke = AsyncMock(
            side_effect=[with_tools, final_resp, refuse],
        )

        messages = []
        usages = []

        _, search_count, step = await agent._run_tool_loop(
            no_tools,
            messages,
            llm_with_tools,
            tool_map,
            usages,
            "job",
            5,
            2,
        )
        assert search_count == 1
        assert step == 1


class TestParseAndDeduplicate:
    @pytest.fixture()
    def agent(self):
        llm = _make_llm()
        return WebScraperAgent(llm=llm)

    async def test_parses_and_deduplicates(self, agent):
        results = [
            WebScraperResult(title="A", url="https://a.com"),
            WebScraperResult(title="B", url="https://b.com"),
            WebScraperResult(title="A dup", url="https://a.com"),
        ]
        structured_output = WebScraperOutput(results=results, filtered_urls=[])

        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(structured_output, {"input_tokens": 20, "output_tokens": 10}),
        ):
            seen = set()
            usages = []
            unique, filtered = await agent._parse_and_deduplicate(
                "search text",
                seen,
                "prompt",
                usages,
            )
            assert len(unique) == 2
            assert len(filtered) == 1
            assert filtered[0].reason == "duplicate URL"
            assert "https://a.com" in seen
            assert "https://b.com" in seen
            assert len(usages) == 1

    async def test_preserves_existing_filtered_urls(self, agent):
        existing_filtered = FilteredURL(url="https://spam.com", reason="unrelated")
        structured_output = WebScraperOutput(
            results=[WebScraperResult(title="C", url="https://c.com")],
            filtered_urls=[existing_filtered],
        )
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(structured_output, None),
        ):
            usages = []
            unique, filtered = await agent._parse_and_deduplicate(
                "text",
                set(),
                "prompt",
                usages,
            )
            assert len(unique) == 1
            assert len(filtered) == 1
            assert filtered[0].url == "https://spam.com"
            assert len(usages) == 0  # usage was None

    async def test_empty_url_not_deduplicated(self, agent):
        results = [
            WebScraperResult(title="No URL 1", url=""),
            WebScraperResult(title="No URL 2", url=""),
        ]
        structured_output = WebScraperOutput(results=results, filtered_urls=[])
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(structured_output, None),
        ):
            unique, filtered = await agent._parse_and_deduplicate(
                "text",
                set(),
                "prompt",
                [],
            )
            assert len(unique) == 2
            assert len(filtered) == 0

    async def test_seen_urls_respected(self, agent):
        results = [WebScraperResult(title="Already seen", url="https://seen.com")]
        structured_output = WebScraperOutput(results=results, filtered_urls=[])
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(structured_output, None),
        ):
            seen = {"https://seen.com"}
            unique, filtered = await agent._parse_and_deduplicate(
                "text",
                seen,
                "prompt",
                [],
            )
            assert len(unique) == 0
            assert len(filtered) == 1


class TestRetryInsufficientResults:
    @pytest.fixture()
    def agent(self):
        llm = _make_llm()
        search = _make_search_tool()
        fetch = _make_fetch_tool()
        return WebScraperAgent(llm=llm, search_tool=search, fetch_tool=fetch)

    async def test_skips_when_min_results_zero(self, agent):
        results = []
        filtered = []
        r, _, sc, _ = await agent._retry_insufficient_results(
            results,
            filtered,
            set(),
            [],
            AsyncMock(),
            {},
            [],
            "job",
            "prompt",
            0,
            5,
            0,
            0,
        )
        assert r == []
        assert sc == 0

    async def test_skips_when_already_enough_results(self, agent):
        results = [
            WebScraperResult(title="A", url="https://a.com"),
            WebScraperResult(title="B", url="https://b.com"),
        ]
        r, _, sc, _ = await agent._retry_insufficient_results(
            results,
            [],
            set(),
            [],
            AsyncMock(),
            {},
            [],
            "job",
            "prompt",
            2,
            5,
            0,
            0,  # min_results=2 and already have 2
        )
        assert len(r) == 2
        assert sc == 0

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_when_insufficient(self, mock_sleep, agent):
        results = []
        llm_with_tools = AsyncMock()

        # First invocation: LLM returns tool calls
        tool_response = _make_ai_message(
            tool_calls=[{"name": "web_search", "id": "r1", "args": {"query": "retry"}}],
        )
        # After tool loop, LLM returns final content
        final_response = _make_ai_message(content="new results found", tool_calls=[])
        llm_with_tools.ainvoke = AsyncMock(side_effect=[tool_response, final_response])

        new_result = WebScraperResult(title="New", url="https://new.com")
        structured_output = WebScraperOutput(results=[new_result], filtered_urls=[])

        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(structured_output, None),
        ):
            search = agent._search_tool
            tool_map = {search.name: search}
            r, _, _, _ = await agent._retry_insufficient_results(
                results,
                [],
                set(),
                [],
                llm_with_tools,
                tool_map,
                [],
                "cert",
                "prompt",
                1,
                10,
                0,
                0,
            )
            assert len(r) >= 1

    async def test_stops_when_llm_refuses(self, agent):
        results = []
        llm_with_tools = AsyncMock()
        # LLM refuses to search (no tool calls)
        refuse = _make_ai_message(content="cannot search more", tool_calls=[])
        llm_with_tools.ainvoke = AsyncMock(return_value=refuse)

        r, _, _, _ = await agent._retry_insufficient_results(
            results,
            [],
            set(),
            [],
            llm_with_tools,
            {},
            [],
            "job",
            "prompt",
            5,
            10,
            0,
            0,
        )
        assert len(r) == 0

    async def test_stops_at_max_3_retries(self, agent):
        """Even if min_results is not met, the retry loop caps at 3."""
        results = []
        llm_with_tools = AsyncMock()
        # LLM always refuses
        refuse = _make_ai_message(content="no", tool_calls=[])
        llm_with_tools.ainvoke = AsyncMock(return_value=refuse)

        await agent._retry_insufficient_results(
            results,
            [],
            set(),
            [],
            llm_with_tools,
            {},
            [],
            "job",
            "prompt",
            10,
            20,
            0,
            0,
        )
        # Should have been invoked once per retry (up to 3) before the LLM refuses
        assert llm_with_tools.ainvoke.await_count <= 3

    async def test_skips_when_llm_with_tools_is_none(self, agent):
        results = []
        r, _, sc, _ = await agent._retry_insufficient_results(
            results,
            [],
            set(),
            [],
            None,
            {},
            [],
            "job",
            "prompt",
            5,
            10,
            0,
            0,
        )
        assert len(r) == 0
        assert sc == 0


class TestBuildOutput:
    @pytest.fixture()
    def agent(self):
        return WebScraperAgent(llm=_make_llm())

    def test_basic_output(self, agent):
        results = [WebScraperResult(title="A", url="https://a.com")]
        filtered = [FilteredURL(url="https://x.com", reason="dupe")]
        usages = [{"input_tokens": 10}]
        output = agent._build_output(
            results,
            filtered,
            usages,
            "job",
            "raw_job_results",
            2,
            1,
        )
        assert len(output["raw_job_results"]) == 1
        assert output["_token_usage"] == usages
        assert "filtered_job_urls" in output

    def test_no_filtered_urls(self, agent):
        output = agent._build_output(
            [],
            [],
            [],
            "cert",
            "raw_cert_results",
            0,
            0,
        )
        assert output["raw_cert_results"] == []
        assert "filtered_cert_urls" not in output

    def test_results_serialized_as_dicts(self, agent):
        results = [
            WebScraperResult(title="B", url="https://b.com", snippet="snip"),
        ]
        output = agent._build_output(
            results,
            [],
            [],
            "event",
            "raw_event_results",
            1,
            1,
        )
        item = output["raw_event_results"][0]
        assert isinstance(item, dict)
        assert item["title"] == "B"
        assert item["url"] == "https://b.com"


class TestCallIntegration:
    """Integration tests for __call__ with all dependencies mocked."""

    @pytest.fixture()
    def agent(self):
        llm = _make_llm()
        search = _make_search_tool()
        fetch = _make_fetch_tool()
        return WebScraperAgent(
            llm=llm,
            search_tool=search,
            fetch_tool=fetch,
            max_steps=3,
        )

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_full_call_with_tools(self, mock_sleep, agent):
        # LLM with tools: first call returns a search tool call, second returns final
        first_msg = _make_ai_message(
            tool_calls=[
                {"name": "web_search", "id": "s1", "args": {"query": "python jobs"}},
            ]
        )
        final_msg = _make_ai_message(content="Found 2 results", tool_calls=[])

        llm_with_tools = AsyncMock()
        llm_with_tools.ainvoke = AsyncMock(side_effect=[first_msg, final_msg])
        agent._llm.bind_tools = MagicMock(return_value=llm_with_tools)

        # Structured output mock
        parsed = WebScraperOutput(
            results=[
                WebScraperResult(title="Job 1", url="https://example.com/jobs/view/1"),
                WebScraperResult(title="Job 2", url="https://example.com/jobs/view/2"),
            ],
            filtered_urls=[],
        )
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, {"input_tokens": 50, "output_tokens": 25}),
        ):
            state = {
                "search_prompt": "Find Python developer jobs",
                "search_category": "job",
                "pipeline_mode": "weekly",
            }
            result = await agent(state)

        assert "raw_job_results" in result
        assert "_token_usage" in result
        assert len(result["raw_job_results"]) == 2

    async def test_call_without_tools(self):
        """When no search tool is provided, agent skips tool loop."""
        llm = _make_llm()
        agent = WebScraperAgent(llm=llm, search_tool=None, fetch_tool=None)

        parsed = WebScraperOutput(
            results=[WebScraperResult(title="Direct", url="https://direct.com")],
            filtered_urls=[],
        )
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, None),
        ):
            state = {
                "search_prompt": "Find certs",
                "search_category": "cert",
            }
            result = await agent(state)

        assert len(result["raw_cert_results"]) == 1

    async def test_call_exception_returns_error(self, agent):
        """When an unhandled exception occurs, __call__ returns an error dict."""
        agent._llm.bind_tools = MagicMock(
            side_effect=RuntimeError("LLM init failed"),
        )
        state = {
            "search_prompt": "test",
            "search_category": "job",
        }
        result = await agent(state)
        assert result["raw_job_results"] == []
        assert "errors" in result
        assert "LLM init failed" in result["errors"][0]

    async def test_call_uses_prompt_loader(self):
        llm = _make_llm()
        loader = MagicMock()
        loader.load = MagicMock(return_value="Custom system prompt for jobs")

        agent = WebScraperAgent(llm=llm, prompt_loader=loader, search_tool=None)

        parsed = WebScraperOutput(results=[], filtered_urls=[])
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, None),
        ):
            state = {
                "search_prompt": "test",
                "search_category": "job",
            }
            await agent(state)

        loader.load.assert_called_once()
        call_args = loader.load.call_args
        assert call_args[0][0] == "web_scraper/job"

    async def test_call_default_system_prompt_without_loader(self):
        llm = _make_llm()
        agent = WebScraperAgent(llm=llm, prompt_loader=None, search_tool=None)

        parsed = WebScraperOutput(results=[], filtered_urls=[])
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, None),
        ):
            state = {"search_prompt": "test", "search_category": "cert"}
            result = await agent(state)

        assert "raw_cert_results" in result

    async def test_call_empty_category(self):
        """When category is empty, agent uses 'job' default for prompt."""
        llm = _make_llm()
        loader = MagicMock()
        loader.load = MagicMock(return_value="system prompt")
        agent = WebScraperAgent(llm=llm, prompt_loader=loader, search_tool=None)

        parsed = WebScraperOutput(results=[], filtered_urls=[])
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, None),
        ):
            state = {"search_prompt": "test", "search_category": ""}
            await agent(state)

        loader.load.assert_called_once()
        assert loader.load.call_args[0][0] == "web_scraper/job"

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_token_usage_tracking(self, mock_sleep, agent):
        """Verify usages are collected from both tool loop and structured output."""
        first_msg = _make_ai_message(
            tool_calls=[{"name": "web_search", "id": "u1", "args": {"query": "q"}}],
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        final_msg = _make_ai_message(
            content="results",
            tool_calls=[],
            usage={"input_tokens": 80, "output_tokens": 30},
        )

        llm_with_tools = AsyncMock()
        llm_with_tools.ainvoke = AsyncMock(side_effect=[first_msg, final_msg])
        agent._llm.bind_tools = MagicMock(return_value=llm_with_tools)

        parsed = WebScraperOutput(results=[], filtered_urls=[])
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, {"input_tokens": 20, "output_tokens": 10}),
        ):
            state = {
                "search_prompt": "test",
                "search_category": "cert",
                "pipeline_mode": "weekly",
            }
            result = await agent(state)

        usages = result["_token_usage"]
        # First response + tool loop response + structured output = 3
        assert len(usages) == 3

    @patch("app.agents.web_scraper.asyncio.sleep", new_callable=AsyncMock)
    async def test_min_results_appended_to_prompt(self, mock_sleep, agent):
        """When budgets set min_results, it appears in the user content."""
        agent._mode_category_budgets = {
            "weekly:job": {"min_results": 5, "min_searches": 3},
        }

        first_msg = _make_ai_message(
            tool_calls=[{"name": "web_search", "id": "m1", "args": {"query": "q"}}],
        )
        final_msg = _make_ai_message(content="done", tool_calls=[])

        llm_with_tools = AsyncMock()
        llm_with_tools.ainvoke = AsyncMock(side_effect=[first_msg, final_msg])
        agent._llm.bind_tools = MagicMock(return_value=llm_with_tools)

        parsed = WebScraperOutput(
            results=[
                WebScraperResult(title=f"J{i}", url=f"https://example.com/jobs/view/{i}")
                for i in range(5)
            ],
            filtered_urls=[],
        )
        with patch.object(
            agent,
            "_invoke_structured",
            new_callable=AsyncMock,
            return_value=(parsed, None),
        ):
            state = {
                "search_prompt": "Find jobs",
                "search_category": "job",
                "pipeline_mode": "weekly",
            }
            await agent(state)

        # The user message sent to LLM should mention min results
        init_call = llm_with_tools.ainvoke.call_args_list[0]
        messages = init_call[0][0]
        user_msg = messages[1]["content"]
        assert "at least 5 results" in user_msg
        assert "at least 3 distinct search queries" in user_msg
