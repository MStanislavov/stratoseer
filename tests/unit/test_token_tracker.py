"""Tests for the RunTokenTracker."""

from __future__ import annotations

import pytest

from app.engine.token_tracker import AgentTokenUsage, RunTokenTracker


@pytest.fixture()
def tracker() -> RunTokenTracker:
    """Create a RunTokenTracker for a test run.

    Returns:
        RunTokenTracker: A fresh tracker with no recorded usage.
    """
    return RunTokenTracker(run_id="test-run-001")


class TestAgentTokenUsage:
    """Tests for AgentTokenUsage dataclass serialization."""

    def test_to_dict(self) -> None:
        usage = AgentTokenUsage(
            agent_name="ceo",
            model="gpt-5.4-mini",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            call_count=1,
        )
        d = usage.to_dict()
        assert d["agent_name"] == "ceo"
        assert d["model"] == "gpt-5.4-mini"
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["total_tokens"] == 150
        assert d["call_count"] == 1


class TestRunTokenTracker:
    """Tests for recording and querying token usage across agents in a run."""

    @pytest.mark.asyncio
    async def test_record_single_agent(self, tracker: RunTokenTracker) -> None:
        await tracker.record("goal_extractor", "gpt-5.4", 200, 100)
        usage = tracker.get_agent_usage("goal_extractor")
        assert usage is not None
        assert usage.input_tokens == 200
        assert usage.output_tokens == 100
        assert usage.total_tokens == 300
        assert usage.call_count == 1
        assert usage.model == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_record_accumulates_multiple_calls(self, tracker: RunTokenTracker) -> None:
        await tracker.record("web_scrapers/job", "gpt-5.4", 500, 200)
        await tracker.record("web_scrapers/job", "gpt-5.4", 300, 150)
        usage = tracker.get_agent_usage("web_scrapers/job")
        assert usage is not None
        assert usage.input_tokens == 800
        assert usage.output_tokens == 350
        assert usage.total_tokens == 1150
        assert usage.call_count == 2

    @pytest.mark.asyncio
    async def test_get_total(self, tracker: RunTokenTracker) -> None:
        await tracker.record("goal_extractor", "gpt-5.4", 200, 100)
        await tracker.record("ceo", "gpt-5.4-mini", 400, 200)
        totals = tracker.get_total()
        assert totals["input_tokens"] == 600
        assert totals["output_tokens"] == 300
        assert totals["total_tokens"] == 900
        assert totals["total_calls"] == 2

    @pytest.mark.asyncio
    async def test_to_dict_serialization(self, tracker: RunTokenTracker) -> None:
        await tracker.record("goal_extractor", "gpt-5.4", 200, 100)
        d = tracker.to_dict()
        assert d["run_id"] == "test-run-001"
        assert "goal_extractor" in d["agents"]
        assert d["totals"]["total_tokens"] == 300

    def test_empty_tracker(self, tracker: RunTokenTracker) -> None:
        assert tracker.get_agent_usage("anything") is None
        totals = tracker.get_total()
        assert totals["total_tokens"] == 0
        assert totals["total_calls"] == 0
        d = tracker.to_dict()
        assert d["agents"] == {}

    @pytest.mark.asyncio
    async def test_model_updated_on_latest_call(self, tracker: RunTokenTracker) -> None:
        await tracker.record("ceo", "", 100, 50)
        await tracker.record("ceo", "gpt-5.4-mini", 100, 50)
        usage = tracker.get_agent_usage("ceo")
        assert usage is not None
        assert usage.model == "gpt-5.4-mini"
