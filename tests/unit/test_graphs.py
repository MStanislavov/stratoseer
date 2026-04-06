"""Unit tests for graph modules: log helpers, node factories, and graph builders."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine
from app.engine.token_tracker import RunTokenTracker
from app.engine.verifier import (
    AgentVerification,
    CheckResult,
    Verifier,
    VerificationStatus,
)
from app.graphs.log import (
    _accumulate_verifier_results,
    _build_verification_dict,
    _publish_sse,
    _record_token_usage,
    _write_audit_end,
    call_agent,
    check_tool,
    make_fan_out_node,
    make_node,
    make_url_filter_report_node,
)


# ------------------------------------------------------------------
# Mock agent helpers
# ------------------------------------------------------------------


def _make_async_agent(name: str = "test_agent", result: dict | None = None):
    """Return an async callable with agent_name attribute."""

    async def agent(state: dict[str, Any]) -> dict[str, Any]:
        return result if result is not None else {"output": "ok"}

    agent.agent_name = name
    return agent


def _make_sync_agent(name: str = "sync_agent", result: dict | None = None):
    """Return a sync callable with agent_name attribute."""

    def agent(state: dict[str, Any]) -> dict[str, Any]:
        return result if result is not None else {"output": "sync_ok"}

    agent.agent_name = name
    return agent


def _make_mock_factory(
    goal_result: dict | None = None,
    scraper_result: dict | None = None,
    formatter_result: dict | None = None,
    ceo_result: dict | None = None,
    cfo_result: dict | None = None,
    cover_letter_result: dict | None = None,
):
    """Create a MagicMock AgentFactory that returns async mock agents."""
    factory = MagicMock()
    factory.create_goal_extractor.return_value = _make_async_agent(
        "goal_extractor",
        goal_result or {"search_prompts": {"job_prompt": "find jobs", "cert_prompt": "certs"}},
    )
    factory.create_web_scraper.return_value = _make_async_agent(
        "web_scraper",
        scraper_result or {"raw_job_results": [], "raw_cert_results": []},
    )
    factory.create_data_formatter.return_value = _make_async_agent(
        "data_formatter",
        formatter_result or {
            "formatted_jobs": [],
            "formatted_certifications": [],
            "formatted_courses": [],
            "formatted_events": [],
            "formatted_groups": [],
            "formatted_trends": [],
        },
    )
    factory.create_ceo.return_value = _make_async_agent(
        "ceo",
        ceo_result or {"strategic_recommendations": [], "ceo_summary": "summary"},
    )
    factory.create_cfo.return_value = _make_async_agent(
        "cfo",
        cfo_result or {"risk_assessments": [], "cfo_summary": "risk summary"},
    )
    factory.create_cover_letter_agent.return_value = _make_async_agent(
        "cover_letter_agent",
        cover_letter_result or {"cover_letter_content": "Dear Hiring Manager..."},
    )
    return factory


# ------------------------------------------------------------------
# log.py helpers
# ------------------------------------------------------------------


class TestCallAgent:
    """Tests for call_agent which dispatches sync/async agents."""

    async def test_async_agent(self):
        agent = _make_async_agent("a", {"k": "v"})
        result = await call_agent(agent, {"run_id": "r1"})
        assert result == {"k": "v"}

    async def test_sync_agent_runs_in_thread(self):
        agent = _make_sync_agent("s", {"k": "sync"})
        result = await call_agent(agent, {"run_id": "r1"})
        assert result == {"k": "sync"}

    async def test_async_callable_class(self):
        """An object with async __call__ should be detected as async."""

        class AsyncCallable:
            agent_name = "cls_agent"

            async def __call__(self, state):
                return {"cls": True}

        agent = AsyncCallable()
        result = await call_agent(agent, {})
        assert result == {"cls": True}


class TestCheckTool:
    """Tests for check_tool policy enforcement."""

    def test_no_policy_engine_allows_all(self):
        # Should not raise
        check_tool(None, "any_agent", "any_tool")

    def test_allowed_tool_passes(self):
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = True
        check_tool(pe, "goal_extractor", "llm_structured_output")
        pe.is_tool_allowed.assert_called_once_with("goal_extractor", "llm_structured_output")

    def test_disallowed_tool_raises(self):
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = False
        with pytest.raises(PermissionError, match="Policy violation"):
            check_tool(pe, "goal_extractor", "web_search")


class TestPublishSSE:
    """Tests for _publish_sse helper."""

    async def test_publishes_when_manager_present(self):
        mgr = AsyncMock()
        await _publish_sse(mgr, "run1", {"type": "test"})
        mgr.publish.assert_awaited_once_with("run1", {"type": "test"})

    async def test_noop_when_manager_is_none(self):
        # Should not raise
        await _publish_sse(None, "run1", {"type": "test"})


class TestBuildVerificationDict:
    """Tests for _build_verification_dict helper."""

    def test_no_verifier_returns_pass(self):
        vdict, status = _build_verification_dict(None, "agent", {})
        assert vdict == {}
        assert status == "pass"

    def test_with_verifier_returns_serialized_result(self):
        mock_check = CheckResult(
            check_name="schema_check",
            status=VerificationStatus.PASS,
            message="OK",
        )
        mock_verification = AgentVerification(
            agent_name="goal_extractor",
            status=VerificationStatus.PASS,
            checks=[mock_check],
            timestamp="2026-01-01T00:00:00",
        )
        verifier = MagicMock(spec=Verifier)
        verifier.verify.return_value = mock_verification

        vdict, status = _build_verification_dict(verifier, "goal_extractor", {"some": "data"})

        assert status == "pass"
        assert vdict["agent_name"] == "goal_extractor"
        assert vdict["status"] == "pass"
        assert len(vdict["checks"]) == 1
        assert vdict["checks"][0]["check_name"] == "schema_check"

    def test_with_verifier_partial_status(self):
        mock_check = CheckResult(
            check_name="bounds_check",
            status=VerificationStatus.PARTIAL,
            message="Too many items",
        )
        mock_verification = AgentVerification(
            agent_name="web_scrapers",
            status=VerificationStatus.PARTIAL,
            checks=[mock_check],
            timestamp="2026-01-01T00:00:00",
        )
        verifier = MagicMock(spec=Verifier)
        verifier.verify.return_value = mock_verification

        vdict, status = _build_verification_dict(verifier, "web_scrapers", {})
        assert status == "partial"


class TestWriteAuditEnd:
    """Tests for _write_audit_end helper."""

    async def test_noop_when_no_audit_writer(self):
        # Should not raise
        await _write_audit_end(
            None, "r1", lambda: "ts", "agent_end", "agent", "agent", {}, {},
        )

    async def test_writes_agent_end_event(self):
        aw = AsyncMock(spec=AuditWriter)
        await _write_audit_end(
            aw, "r1", lambda: "2026-01-01",
            "agent_end", "goal_extractor", "agent",
            {"some": "data"}, {},
        )
        # Only agent_end, no verifier_result (empty dict is falsy)
        assert aw.append.await_count == 1
        call_args = aw.append.await_args_list[0]
        assert call_args[0][0] == "r1"
        event = call_args[0][1]
        assert event.event_type == "agent_end"

    async def test_writes_verifier_result_when_present(self):
        aw = AsyncMock(spec=AuditWriter)
        vdict = {"agent_name": "test", "status": "pass", "checks": []}
        await _write_audit_end(
            aw, "r1", lambda: "2026-01-01",
            "agent_end", "agent", "agent",
            {}, vdict,
        )
        assert aw.append.await_count == 2
        second_event = aw.append.await_args_list[1][0][1]
        assert second_event.event_type == "verifier_result"


class TestAccumulateVerifierResults:
    """Tests for _accumulate_verifier_results helper."""

    def test_appends_to_empty_state(self):
        state: dict[str, Any] = {}
        result: dict[str, Any] = {}
        vdict = {"agent_name": "a", "status": "pass"}
        _accumulate_verifier_results(state, result, vdict)
        assert result["verifier_results"] == [vdict]

    def test_appends_to_existing(self):
        existing = [{"agent_name": "prev"}]
        state: dict[str, Any] = {"verifier_results": existing}
        result: dict[str, Any] = {}
        vdict = {"agent_name": "new"}
        _accumulate_verifier_results(state, result, vdict)
        assert len(result["verifier_results"]) == 2

    def test_empty_dict_skipped(self):
        state: dict[str, Any] = {}
        result: dict[str, Any] = {}
        _accumulate_verifier_results(state, result, {})
        assert "verifier_results" not in result


class TestRecordTokenUsage:
    """Tests for _record_token_usage helper."""

    async def test_records_usage(self):
        tracker = AsyncMock(spec=RunTokenTracker)
        result = {
            "_token_usage": [
                {"model_name": "gpt-4", "input_tokens": 100, "output_tokens": 50},
            ],
            "other_key": "value",
        }
        await _record_token_usage(tracker, "goal_extractor", result)
        tracker.record.assert_awaited_once_with("goal_extractor", "gpt-4", 100, 50)
        # _token_usage should be popped
        assert "_token_usage" not in result
        assert result["other_key"] == "value"

    async def test_noop_when_no_tracker(self):
        result = {"_token_usage": [{"model_name": "x", "input_tokens": 1, "output_tokens": 1}]}
        await _record_token_usage(None, "agent", result)
        # Should pop _token_usage even without tracker
        assert "_token_usage" not in result

    async def test_noop_when_no_usage(self):
        tracker = AsyncMock(spec=RunTokenTracker)
        result = {"data": "value"}
        await _record_token_usage(tracker, "agent", result)
        tracker.record.assert_not_awaited()


# ------------------------------------------------------------------
# make_node factory
# ------------------------------------------------------------------


class TestMakeNode:
    """Tests for the make_node single-agent node factory."""

    async def test_returns_agent_result(self):
        agent = _make_async_agent("test", {"output": "hello"})
        node_fn = make_node("test_pipe", "test", agent, "llm_structured_output")
        result = await node_fn({"run_id": "r1"})
        assert result["output"] == "hello"

    async def test_calls_policy_check(self):
        agent = _make_async_agent("agent", {"out": 1})
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = True
        node_fn = make_node("p", "agent", agent, "web_search", policy_engine=pe)
        await node_fn({"run_id": "r1"})
        pe.is_tool_allowed.assert_called_once_with("agent", "web_search")

    async def test_raises_on_policy_violation(self):
        agent = _make_async_agent("agent", {})
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = False
        node_fn = make_node("p", "agent", agent, "web_search", policy_engine=pe)
        with pytest.raises(PermissionError, match="Policy violation"):
            await node_fn({"run_id": "r1"})

    async def test_publishes_sse_events(self):
        agent = _make_async_agent("agent", {"val": 1})
        mgr = AsyncMock()
        node_fn = make_node("p", "agent", agent, "tool", event_manager=mgr)
        await node_fn({"run_id": "r1"})
        # Should publish started + completed
        assert mgr.publish.await_count == 2
        started_event = mgr.publish.await_args_list[0][0][1]
        completed_event = mgr.publish.await_args_list[1][0][1]
        assert started_event["type"] == "agent_started"
        assert completed_event["type"] == "agent_completed"

    async def test_writes_audit_events(self):
        agent = _make_async_agent("agent", {"val": 1})
        aw = AsyncMock(spec=AuditWriter)
        node_fn = make_node("p", "agent", agent, "tool", audit_writer=aw)
        await node_fn({"run_id": "r1"})
        # Should write agent_start and agent_end
        assert aw.append.await_count >= 2

    async def test_verifier_integration(self):
        agent = _make_async_agent("goal_extractor", {"search_prompts": {}})
        mock_check = CheckResult(
            check_name="check", status=VerificationStatus.PASS, message="ok",
        )
        mock_verification = AgentVerification(
            agent_name="goal_extractor",
            status=VerificationStatus.PASS,
            checks=[mock_check],
            timestamp="ts",
        )
        verifier = MagicMock(spec=Verifier)
        verifier.verify.return_value = mock_verification

        node_fn = make_node(
            "p", "goal_extractor", agent, "llm_structured_output",
            verifier=verifier,
        )
        result = await node_fn({"run_id": "r1"})
        verifier.verify.assert_called_once()
        assert "verifier_results" in result

    async def test_custom_node_type(self):
        agent = _make_async_agent("validator", {"ok": True})
        mgr = AsyncMock()
        node_fn = make_node(
            "p", "validator", agent, "tool",
            event_manager=mgr, node_type="static_validator",
        )
        await node_fn({"run_id": "r1"})
        started_event = mgr.publish.await_args_list[0][0][1]
        assert started_event["type"] == "static_validator_started"

    async def test_token_tracking(self):
        agent = _make_async_agent(
            "agent",
            {"val": 1, "_token_usage": [{"model_name": "gpt-4", "input_tokens": 10, "output_tokens": 5}]},
        )
        tracker = AsyncMock(spec=RunTokenTracker)
        node_fn = make_node("p", "agent", agent, "tool", token_tracker=tracker)
        result = await node_fn({"run_id": "r1"})
        tracker.record.assert_awaited_once()
        assert "_token_usage" not in result


# ------------------------------------------------------------------
# make_fan_out_node factory
# ------------------------------------------------------------------


class TestMakeFanOutNode:
    """Tests for the make_fan_out_node multi-scraper factory."""

    async def test_runs_scrapers_and_merges(self):
        async def scraper(state):
            cat = state.get("search_category", "")
            return {f"raw_{cat}_results": [{"title": f"{cat} item"}]}

        scraper.agent_name = "scraper"

        categories = [("job", "job_prompt"), ("cert", "cert_prompt")]
        node_fn = make_fan_out_node("p", "web_scrapers", scraper, "web_search", categories)
        result = await node_fn({
            "run_id": "r1",
            "search_prompts": {"job_prompt": "find jobs", "cert_prompt": "find certs"},
        })
        assert len(result["raw_job_results"]) == 1
        assert len(result["raw_cert_results"]) == 1

    async def test_collects_errors(self):
        async def scraper(state):
            cat = state.get("search_category", "")
            return {f"raw_{cat}_results": [], "errors": [f"{cat} failed"]}

        scraper.agent_name = "scraper"

        categories = [("job", "job_prompt"), ("cert", "cert_prompt")]
        node_fn = make_fan_out_node("p", "scrapers", scraper, "web_search", categories)
        result = await node_fn({"run_id": "r1", "search_prompts": {}, "errors": []})
        assert "job failed" in result["errors"]
        assert "cert failed" in result["errors"]

    async def test_policy_check(self):
        scraper = _make_async_agent("scraper", {"raw_job_results": []})
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = False
        categories = [("job", "job_prompt")]
        node_fn = make_fan_out_node(
            "p", "scrapers", scraper, "web_search", categories,
            policy_engine=pe,
        )
        with pytest.raises(PermissionError):
            await node_fn({"run_id": "r1", "search_prompts": {}})

    async def test_publishes_sse_events(self):
        scraper = _make_async_agent("scraper", {"raw_job_results": []})
        mgr = AsyncMock()
        categories = [("job", "job_prompt")]
        node_fn = make_fan_out_node(
            "p", "scrapers", scraper, "web_search", categories,
            event_manager=mgr,
        )
        await node_fn({"run_id": "r1", "search_prompts": {}})
        assert mgr.publish.await_count == 2  # started + completed

    async def test_scraper_overrides(self):
        """Test that scraper_overrides replaces the default scraper for a category."""
        default_scraper = _make_async_agent("default", {"raw_job_results": [{"from": "default"}]})

        async def override_scraper(state):
            return {"raw_job_results": [{"from": "override"}]}

        override_scraper.agent_name = "override"

        categories = [("job", "job_prompt")]
        node_fn = make_fan_out_node(
            "p", "scrapers", default_scraper, "web_search", categories,
            scraper_overrides={"job": override_scraper},
        )
        result = await node_fn({"run_id": "r1", "search_prompts": {}})
        assert result["raw_job_results"][0]["from"] == "override"

    async def test_filtered_urls_collected(self):
        async def scraper(state):
            cat = state.get("search_category", "")
            return {
                f"raw_{cat}_results": [],
                f"filtered_{cat}_urls": [{"url": "http://filtered.com", "reason": "blocked"}],
            }

        scraper.agent_name = "scraper"

        categories = [("job", "job_prompt")]
        node_fn = make_fan_out_node("p", "scrapers", scraper, "web_search", categories)
        result = await node_fn({"run_id": "r1", "search_prompts": {}})
        assert len(result["filtered_job_urls"]) == 1


# ------------------------------------------------------------------
# make_url_filter_report_node
# ------------------------------------------------------------------


class TestMakeUrlFilterReportNode:
    """Tests for the URL filter report node factory."""

    async def test_empty_state_produces_zero_total(self):
        node_fn = make_url_filter_report_node("daily")
        result = await node_fn({"run_id": "r1"})
        assert result == {}

    async def test_publishes_sse_events(self):
        mgr = AsyncMock()
        node_fn = make_url_filter_report_node("daily", event_manager=mgr)
        await node_fn({"run_id": "r1"})
        assert mgr.publish.await_count == 2
        started = mgr.publish.await_args_list[0][0][1]
        completed = mgr.publish.await_args_list[1][0][1]
        assert started["type"] == "static_validator_started"
        assert completed["type"] == "static_validator_completed"

    async def test_writes_audit_with_filtered_urls(self):
        aw = AsyncMock(spec=AuditWriter)
        node_fn = make_url_filter_report_node("daily", audit_writer=aw)
        state = {
            "run_id": "r1",
            "filtered_job_urls": [{"url": "http://a.com"}],
            "filtered_cert_urls": [{"url": "http://b.com"}, {"url": "http://c.com"}],
        }
        await node_fn(state)
        # start + end = 2 audit events
        assert aw.append.await_count == 2
        end_event = aw.append.await_args_list[1][0][1]
        assert end_event.data["total_filtered"] == 3


# ------------------------------------------------------------------
# daily.py
# ------------------------------------------------------------------


class TestDailyGraph:
    """Tests for build_daily_graph and daily-specific routing."""

    def test_build_daily_graph_returns_state_graph(self):
        factory = _make_mock_factory()
        graph = build_daily_graph(factory)
        assert graph is not None
        # Should be compilable
        compiled = graph.compile()
        assert compiled is not None

    def test_build_daily_graph_with_all_options(self):
        factory = _make_mock_factory()
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = True
        aw = AsyncMock(spec=AuditWriter)
        v = MagicMock(spec=Verifier)
        mgr = AsyncMock()
        tracker = AsyncMock(spec=RunTokenTracker)

        graph = build_daily_graph(
            factory,
            policy_engine=pe,
            audit_writer=aw,
            verifier=v,
            event_manager=mgr,
            token_tracker=tracker,
        )
        compiled = graph.compile()
        assert compiled is not None

    def test_check_scraper_results_routes_to_format(self):
        state = {
            "run_id": "r1",
            "raw_job_results": [{"title": "job"}],
            "raw_cert_results": [],
            "raw_event_results": [],
            "raw_group_results": [],
            "raw_trend_results": [],
        }
        result = daily_check_scraper_results(state)
        assert result == "format"

    def test_check_scraper_results_routes_to_safe_degrade(self):
        state = {
            "run_id": "r1",
            "raw_job_results": [],
            "raw_cert_results": [],
            "raw_event_results": [],
            "raw_group_results": [],
            "raw_trend_results": [],
        }
        result = daily_check_scraper_results(state)
        assert result == "safe_degrade"

    def test_safe_degrade_node_returns_empty_lists(self):
        state = {"run_id": "r1", "errors": ["prior error"]}
        result = daily_safe_degrade_node(state)
        assert result["safe_degradation"] is True
        assert result["formatted_jobs"] == []
        assert result["formatted_certifications"] == []
        assert result["formatted_courses"] == []
        assert result["formatted_events"] == []
        assert result["formatted_groups"] == []
        assert result["formatted_trends"] == []
        assert len(result["errors"]) == 2  # prior error + degradation msg


# ------------------------------------------------------------------
# weekly.py
# ------------------------------------------------------------------


class TestWeeklyGraph:
    """Tests for build_weekly_graph and weekly-specific routing."""

    def test_build_weekly_graph_returns_state_graph(self):
        factory = _make_mock_factory()
        graph = build_weekly_graph(factory)
        compiled = graph.compile()
        assert compiled is not None

    def test_build_weekly_graph_with_all_options(self):
        factory = _make_mock_factory()
        pe = MagicMock(spec=PolicyEngine)
        pe.is_tool_allowed.return_value = True
        graph = build_weekly_graph(
            factory,
            policy_engine=pe,
            audit_writer=AsyncMock(spec=AuditWriter),
            verifier=MagicMock(spec=Verifier),
            event_manager=AsyncMock(),
            token_tracker=AsyncMock(spec=RunTokenTracker),
        )
        compiled = graph.compile()
        assert compiled is not None

    def test_weekly_check_scraper_results_routes_to_format(self):
        state = {
            "run_id": "r1",
            "raw_job_results": [],
            "raw_cert_results": [{"title": "cert"}],
            "raw_event_results": [],
            "raw_group_results": [],
            "raw_trend_results": [],
        }
        result = weekly_check_scraper_results(state)
        assert result == "format"

    def test_weekly_check_scraper_results_routes_to_safe_degrade(self):
        state = {
            "run_id": "r1",
            "raw_job_results": [],
            "raw_cert_results": [],
            "raw_event_results": [],
            "raw_group_results": [],
            "raw_trend_results": [],
        }
        result = weekly_check_scraper_results(state)
        assert result == "safe_degrade"

    def test_weekly_safe_degrade_node(self):
        state = {"run_id": "r1", "errors": []}
        result = weekly_safe_degrade_node(state)
        assert result["safe_degradation"] is True
        assert result["formatted_jobs"] == []
        assert "safe degradation active" in result["errors"][0].lower()


# ------------------------------------------------------------------
# cover_letter.py
# ------------------------------------------------------------------


class TestCoverLetterGraph:
    """Tests for build_cover_letter_graph."""

    def test_build_cover_letter_graph_returns_state_graph(self):
        factory = _make_mock_factory()
        graph = build_cover_letter_graph(factory)
        compiled = graph.compile()
        assert compiled is not None

    def test_build_cover_letter_graph_with_all_options(self):
        factory = _make_mock_factory()
        graph = build_cover_letter_graph(
            factory,
            policy_engine=MagicMock(spec=PolicyEngine),
            audit_writer=AsyncMock(spec=AuditWriter),
            verifier=MagicMock(spec=Verifier),
            event_manager=AsyncMock(),
            token_tracker=AsyncMock(spec=RunTokenTracker),
        )
        compiled = graph.compile()
        assert compiled is not None


# ------------------------------------------------------------------
# Audit node tests (daily / weekly / cover_letter)
# ------------------------------------------------------------------


class TestDailyAuditNode:
    """Tests for the daily pipeline's internal audit node."""

    async def test_audit_node_no_writer(self):
        node = daily_make_audit_node()
        result = await node({"run_id": "r1"})
        assert result == {}

    async def test_audit_node_with_writer(self):
        aw = AsyncMock(spec=AuditWriter)
        node = daily_make_audit_node(audit_writer=aw)
        state = {
            "run_id": "r1",
            "profile_id": "p1",
            "formatted_jobs": [{"title": "job"}],
            "formatted_certifications": [],
            "formatted_courses": [],
            "formatted_events": [],
            "formatted_groups": [],
            "formatted_trends": [],
            "verifier_results": [],
        }
        result = await node(state)
        assert result == {}
        assert aw.append.await_count >= 2
        aw.create_run_bundle.assert_awaited_once()


class TestWeeklyAuditNode:
    """Tests for the weekly pipeline's internal audit node."""

    async def test_audit_node_no_writer(self):
        node = weekly_make_audit_node()
        result = await node({"run_id": "r1"})
        assert result == {}

    async def test_audit_node_with_writer(self):
        aw = AsyncMock(spec=AuditWriter)
        node = weekly_make_audit_node(audit_writer=aw)
        state = {
            "run_id": "r1",
            "profile_id": "p1",
            "formatted_jobs": [],
            "formatted_certifications": [],
            "formatted_courses": [],
            "formatted_events": [],
            "formatted_groups": [],
            "formatted_trends": [],
            "strategic_recommendations": [],
            "risk_assessments": [],
            "ceo_summary": "",
            "cfo_summary": "",
            "verifier_results": [],
        }
        result = await node(state)
        assert result == {}
        aw.create_run_bundle.assert_awaited_once()


class TestCoverLetterAuditNode:
    """Tests for the cover letter pipeline's internal audit node."""

    async def test_audit_node_no_writer(self):
        node = cl_make_audit_node()
        result = await node({"run_id": "r1"})
        assert result == {}

    async def test_audit_node_with_writer(self):
        aw = AsyncMock(spec=AuditWriter)
        node = cl_make_audit_node(audit_writer=aw)
        state = {
            "run_id": "r1",
            "profile_id": "p1",
            "cover_letter_content": "Dear Manager...",
            "verifier_results": [],
        }
        result = await node(state)
        assert result == {}
        aw.create_run_bundle.assert_awaited_once()

    async def test_audit_node_with_verifier(self):
        aw = AsyncMock(spec=AuditWriter)
        v = MagicMock(spec=Verifier)
        v.build_report.return_value = {"overall": "pass", "checks": []}
        node = cl_make_audit_node(audit_writer=aw, verifier=v)
        state = {
            "run_id": "r1",
            "profile_id": "p1",
            "cover_letter_content": "content",
            "verifier_results": [
                {
                    "agent_name": "cover_letter_agent",
                    "status": "pass",
                    "checks": [
                        {"check_name": "has_content", "status": "pass", "message": "ok"},
                    ],
                    "timestamp": "2026-01-01T00:00:00",
                },
            ],
        }
        await node(state)
        v.build_report.assert_called_once()


# ------------------------------------------------------------------
# Imports for internal functions from each graph module
# ------------------------------------------------------------------

from app.graphs.daily import (
    _check_scraper_results as daily_check_scraper_results,
    _make_audit_node as daily_make_audit_node,
    _safe_degrade_node as daily_safe_degrade_node,
    build_daily_graph,
)
from app.graphs.weekly import (
    _check_scraper_results as weekly_check_scraper_results,
    _make_audit_node as weekly_make_audit_node,
    _safe_degrade_node as weekly_safe_degrade_node,
    build_weekly_graph,
)
from app.graphs.cover_letter import (
    _make_audit_node as cl_make_audit_node,
    build_cover_letter_graph,
)
