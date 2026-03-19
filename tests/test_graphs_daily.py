"""End-to-end tests for the daily pipeline with mock agents."""

import pytest

from app.agents.factory import AgentFactory
from app.engine.audit_writer import AuditWriter
from app.graphs.daily import build_daily_graph


@pytest.fixture()
def mock_factory():
    return AgentFactory()


class TestDailyPipeline:
    @pytest.mark.asyncio
    async def test_daily_pipeline_produces_results(self, mock_factory):
        graph = build_daily_graph(agent_factory=mock_factory)
        compiled = graph.compile()

        initial_state = {
            "profile_id": "test-profile",
            "profile_targets": ["cloud", "devops"],
            "profile_skills": ["python", "aws"],
            "run_id": "test-run-daily",
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        }

        result = await compiled.ainvoke(initial_state)

        # GoalExtractor should produce search prompts
        assert "search_prompts" in result
        assert "job_prompt" in result["search_prompts"]
        assert "trend_prompt" in result["search_prompts"]

        # DataFormatter should produce formatted results
        assert "formatted_jobs" in result
        assert "formatted_certifications" in result
        assert "formatted_courses" in result
        assert "formatted_events" in result
        assert "formatted_groups" in result
        assert "formatted_trends" in result

        # Should have actual results from mock agents
        assert len(result["formatted_jobs"]) > 0
        assert len(result["formatted_trends"]) > 0

    @pytest.mark.asyncio
    async def test_daily_pipeline_no_errors(self, mock_factory):
        graph = build_daily_graph(agent_factory=mock_factory)
        compiled = graph.compile()

        result = await compiled.ainvoke({
            "profile_id": "test-profile",
            "profile_targets": ["python"],
            "profile_skills": [],
            "run_id": "test-run-daily-2",
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        })

        assert result.get("errors", []) == []

    @pytest.mark.asyncio
    async def test_daily_pipeline_with_audit_writer(self, mock_factory, tmp_path):
        audit_writer = AuditWriter(artifacts_dir=tmp_path / "artifacts")
        graph = build_daily_graph(
            audit_writer=audit_writer, agent_factory=mock_factory,
        )
        compiled = graph.compile()

        run_id = "test-run-audit"
        result = await compiled.ainvoke({
            "profile_id": "test-profile",
            "profile_targets": ["python"],
            "profile_skills": [],
            "run_id": run_id,
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        })

        # Audit bundle should be created
        bundle = audit_writer.read_bundle(run_id)
        assert bundle is not None
        assert "jobs" in bundle["final_artifacts"]
