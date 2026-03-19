"""End-to-end tests for the weekly pipeline with mock agents."""

import pytest

from app.agents.factory import AgentFactory
from app.engine.audit_writer import AuditWriter
from app.graphs.weekly import build_weekly_graph


@pytest.fixture()
def mock_factory():
    return AgentFactory()


class TestWeeklyPipeline:
    @pytest.mark.asyncio
    async def test_weekly_pipeline_produces_results_with_ceo_cfo(self, mock_factory):
        graph = build_weekly_graph(agent_factory=mock_factory)
        compiled = graph.compile()

        result = await compiled.ainvoke({
            "profile_id": "test-profile",
            "profile_targets": ["cloud", "devops"],
            "profile_skills": ["python", "aws"],
            "run_id": "test-run-weekly",
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        })

        # Should have all daily results
        assert "formatted_jobs" in result
        assert "formatted_certifications" in result
        assert "formatted_trends" in result

        # Plus CEO/CFO outputs
        assert "strategic_recommendations" in result
        assert "ceo_summary" in result
        assert "risk_assessments" in result
        assert "cfo_summary" in result

        assert len(result["strategic_recommendations"]) > 0
        assert len(result["risk_assessments"]) > 0

    @pytest.mark.asyncio
    async def test_weekly_pipeline_no_errors(self, mock_factory):
        graph = build_weekly_graph(agent_factory=mock_factory)
        compiled = graph.compile()

        result = await compiled.ainvoke({
            "profile_id": "test-profile",
            "profile_targets": ["python"],
            "profile_skills": [],
            "run_id": "test-run-weekly-2",
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        })

        assert result.get("errors", []) == []

    @pytest.mark.asyncio
    async def test_weekly_pipeline_with_audit(self, mock_factory, tmp_path):
        audit_writer = AuditWriter(artifacts_dir=tmp_path / "artifacts")
        graph = build_weekly_graph(
            audit_writer=audit_writer, agent_factory=mock_factory,
        )
        compiled = graph.compile()

        run_id = "test-run-weekly-audit"
        result = await compiled.ainvoke({
            "profile_id": "test-profile",
            "profile_targets": ["python"],
            "profile_skills": [],
            "run_id": run_id,
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        })

        bundle = await audit_writer.read_bundle(run_id)
        assert bundle is not None
        assert "jobs" in bundle["final_artifacts"]
        assert "strategic_recommendations" in bundle["final_artifacts"]
        assert "risk_assessments" in bundle["final_artifacts"]
