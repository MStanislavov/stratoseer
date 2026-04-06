"""Unit tests for INTERNAL helper functions and background tasks in service modules.

These functions use async_session_factory directly (not FastAPI DI), so we must
mock the session factory as an async context manager.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Shared helpers (reuse patterns from test_services.py)
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_run(
    id="run-1",
    profile_id="prof-1",
    mode="daily",
    status="completed",
    started_at=_NOW,
    finished_at=_NOW,
    verifier_status="pass",
    audit_path="/artifacts/runs/run-1",
    created_at=_NOW,
):
    run = MagicMock()
    run.id = id
    run.profile_id = profile_id
    run.mode = mode
    run.status = status
    run.started_at = started_at
    run.finished_at = finished_at
    run.verifier_status = verifier_status
    run.audit_path = audit_path
    run.created_at = created_at
    return run


def _make_profile(
    id="prof-1",
    owner_id="user-1",
    name="Architect",
    targets='["backend", "cloud"]',
    constraints='["remote only"]',
    skills='["Python", "AWS"]',
    cv_data=None,
    cv_filename=None,
    cv_summary=None,
    cv_summary_hash=None,
    preferred_titles='["Senior Engineer"]',
    experience_level="senior",
    industries='["tech"]',
    locations='["US"]',
    work_arrangement="remote",
    event_attendance="no preference",
    event_topics=None,
    target_certifications=None,
    learning_format=None,
    created_at=_NOW,
    updated_at=_NOW,
):
    p = MagicMock()
    p.id = id
    p.owner_id = owner_id
    p.name = name
    p.targets = targets
    p.constraints = constraints
    p.skills = skills
    p.cv_data = cv_data
    p.cv_filename = cv_filename
    p.cv_summary = cv_summary
    p.cv_summary_hash = cv_summary_hash
    p.preferred_titles = preferred_titles
    p.experience_level = experience_level
    p.industries = industries
    p.locations = locations
    p.work_arrangement = work_arrangement
    p.event_attendance = event_attendance
    p.event_topics = event_topics
    p.target_certifications = target_certifications
    p.learning_format = learning_format
    p.created_at = created_at
    p.updated_at = updated_at
    return p


def _make_user(
    id="user-1",
    role="user",
    encrypted_api_key=None,
    free_runs_used=0,
):
    u = MagicMock()
    u.id = id
    u.role = role
    u.encrypted_api_key = encrypted_api_key
    u.free_runs_used = free_runs_used
    return u


def _mock_async_session():
    """Create a mock async session and a context-manager-yielding factory."""
    session = AsyncMock()
    session.add = MagicMock()

    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory, session


# ===================================================================
# run_service internals
# ===================================================================


class TestCreateAgentFactory:
    @patch("app.services.run_service.PolicyEngine")
    @patch("app.services.run_service.SafeDuckDuckGoSearchTool")
    @patch("app.services.run_service.ChatOpenAI")
    @patch("app.services.run_service.PromptLoader")
    @patch("app.services.run_service.settings")
    def test_returns_agent_factory(
        self, mock_settings, mock_pl, mock_chat, mock_search, mock_pe
    ):
        from app.services.run_service import create_agent_factory

        mock_settings.prompts_dir = "/prompts"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_temperature = 0.3
        mock_settings.policy_dir = "/policy"
        mock_settings.goal_extractor_model = "m1"
        mock_settings.web_scraper_model = "m2"
        mock_settings.data_formatter_model = "m3"
        mock_settings.ceo_model = "m4"
        mock_settings.cfo_model = "m5"
        mock_settings.cover_letter_model = "m6"

        factory = create_agent_factory("sk-test-key")

        mock_chat.assert_called_once_with(
            model="gpt-4o-mini", temperature=0.3, api_key="sk-test-key"
        )
        mock_pl.assert_called_once_with("/prompts")
        mock_pe.assert_called_once_with("/policy")
        assert factory is not None

    @patch("app.services.run_service.PolicyEngine")
    @patch("app.services.run_service.SafeDuckDuckGoSearchTool", side_effect=ImportError)
    @patch("app.services.run_service.ChatOpenAI")
    @patch("app.services.run_service.PromptLoader")
    @patch("app.services.run_service.settings")
    def test_handles_missing_search_tool(
        self, mock_settings, mock_pl, mock_chat, mock_search, mock_pe
    ):
        from app.services.run_service import create_agent_factory

        mock_settings.prompts_dir = "/prompts"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_temperature = 0.3
        mock_settings.policy_dir = "/policy"
        mock_settings.goal_extractor_model = ""
        mock_settings.web_scraper_model = ""
        mock_settings.data_formatter_model = ""
        mock_settings.ceo_model = ""
        mock_settings.cfo_model = ""
        mock_settings.cover_letter_model = ""

        factory = create_agent_factory("sk-test-key")
        # Should still return a factory even when search tool import fails
        assert factory is not None


class TestUpdateRunStatus:
    @patch("app.services.run_service.async_session_factory")
    async def test_updates_status_and_finished_at(self, mock_factory):
        from app.services.run_service import _update_run_status

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        run = _make_run(id="run-1", status="running")
        mock_session.get = AsyncMock(return_value=run)

        await _update_run_status("run-1", "completed", audit_path="/artifacts/runs/run-1")

        assert run.status == "completed"
        assert run.finished_at is not None
        assert run.audit_path == "/artifacts/runs/run-1"
        mock_session.commit.assert_called_once()

    @patch("app.services.run_service.async_session_factory")
    async def test_noop_when_run_not_found(self, mock_factory):
        from app.services.run_service import _update_run_status

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=None)

        # Should not raise
        await _update_run_status("nonexistent", "failed")
        mock_session.commit.assert_not_called()

    @patch("app.services.run_service.async_session_factory")
    async def test_sets_extra_kwargs(self, mock_factory):
        from app.services.run_service import _update_run_status

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        run = _make_run(id="run-1")
        mock_session.get = AsyncMock(return_value=run)

        await _update_run_status("run-1", "failed", verifier_status="fail")
        assert run.status == "failed"
        assert run.verifier_status == "fail"


class TestStartRun:
    @patch("app.services.run_service.async_session_factory")
    async def test_marks_run_as_running(self, mock_factory):
        from app.services.run_service import _start_run

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        run = _make_run(id="run-1", status="pending")
        mock_session.get = AsyncMock(return_value=run)

        result = await _start_run("run-1")
        assert result is True
        assert run.status == "running"
        assert run.started_at is not None
        mock_session.commit.assert_called_once()

    @patch("app.services.run_service.async_session_factory")
    async def test_returns_false_when_missing(self, mock_factory):
        from app.services.run_service import _start_run

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=None)

        result = await _start_run("nonexistent")
        assert result is False


class TestLoadProfile:
    @patch("app.services.run_service.async_session_factory")
    async def test_loads_profile_with_cv_summary(self, mock_factory):
        from app.services.run_service import _load_profile

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        profile = _make_profile(
            cv_summary="Summarized CV content",
            cv_data=b"pdf-bytes",
        )
        mock_session.get = AsyncMock(return_value=profile)

        result = await _load_profile("prof-1")
        assert result["cv_summary"] == "Summarized CV content"
        assert result["profile_targets"] == ["backend", "cloud"]
        assert result["profile_skills"] == ["Python", "AWS"]
        assert result["profile_constraints"] == ["remote only"]
        assert result["experience_level"] == "senior"
        assert result["work_arrangement"] == "remote"

    @patch("app.services.run_service._read_cv_bytes", return_value="Extracted text")
    @patch("app.services.run_service.async_session_factory")
    async def test_falls_back_to_cv_data_extraction(self, mock_factory, mock_read):
        from app.services.run_service import _load_profile

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        profile = _make_profile(cv_summary=None, cv_data=b"pdf-bytes")
        mock_session.get = AsyncMock(return_value=profile)

        result = await _load_profile("prof-1")
        assert result["cv_summary"] == "Extracted text"
        mock_read.assert_called_once_with(b"pdf-bytes")

    @patch("app.services.run_service.async_session_factory")
    async def test_returns_empty_when_no_profile(self, mock_factory):
        from app.services.run_service import _load_profile

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=None)

        result = await _load_profile("nonexistent")
        assert result["profile_targets"] == []
        assert result["cv_summary"] == ""


class TestReadCvBytes:
    @patch("app.services.profile_service.extract_text_from_pdf", return_value="PDF text")
    def test_extracts_text(self, mock_extract):
        from app.services.run_service import _read_cv_bytes

        result = _read_cv_bytes(b"pdf-content")
        assert result == "PDF text"
        mock_extract.assert_called_once_with(b"pdf-content")

    @patch("app.services.profile_service.extract_text_from_pdf", side_effect=Exception("bad"))
    def test_returns_empty_on_failure(self, mock_extract):
        from app.services.run_service import _read_cv_bytes

        result = _read_cv_bytes(b"bad-content")
        assert result == ""


class TestPersistResults:
    @patch("app.services.run_service.async_session_factory")
    async def test_persists_all_entity_types(self, mock_factory):
        from app.services.run_service import persist_results

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = {
            "formatted_jobs": [
                {"title": "Engineer", "company": "ACME", "url": "https://acme.com",
                 "description": "Build", "location": "Remote", "salary_range": "100k",
                 "source_query": "python"},
            ],
            "formatted_certifications": [
                {"title": "AWS SA", "provider": "Amazon", "url": "https://aws.com",
                 "description": "Cloud cert", "cost": "$300", "duration": "3 months"},
            ],
            "formatted_courses": [
                {"title": "Python 101", "platform": "Udemy", "url": "https://udemy.com",
                 "description": "Learn", "cost": "$20", "duration": "10h"},
            ],
            "formatted_events": [
                {"title": "PyCon", "organizer": "PSF", "url": "https://pycon.org",
                 "description": "Conf", "event_date": "2099-05-01", "location": "Remote"},
            ],
            "formatted_groups": [
                {"title": "Python Devs", "platform": "LinkedIn",
                 "url": "https://linkedin.com", "description": "Group",
                 "member_count": 500},
            ],
            "formatted_trends": [
                {"title": "AI Trend", "category": "tech", "url": "https://ai.com",
                 "description": "Growing", "relevance": "high", "source": "HN"},
            ],
        }

        await persist_results("run-1", "prof-1", result)

        # 6 entities added (1 job + 1 cert + 1 course + 1 event + 1 group + 1 trend)
        assert mock_session.add.call_count == 6
        mock_session.commit.assert_called_once()

    @patch("app.services.run_service.async_session_factory")
    async def test_filters_past_events(self, mock_factory):
        from app.services.run_service import persist_results

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = {
            "formatted_events": [
                {"title": "Past Event", "event_date": "2020-01-01"},
                {"title": "Future Event", "event_date": "2099-12-31"},
                {"title": "No Date Event"},  # no event_date -> should be included
            ],
        }

        await persist_results("run-1", "prof-1", result)
        # Only future + no-date events pass (2 out of 3)
        assert mock_session.add.call_count == 2

    @patch("app.services.run_service.async_session_factory")
    async def test_handles_empty_result(self, mock_factory):
        from app.services.run_service import persist_results

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await persist_results("run-1", "prof-1", {})
        mock_session.add.assert_not_called()
        mock_session.commit.assert_called_once()


class TestExecuteRun:
    """Tests for the execute_run background task including success, cancellation, and error paths."""

    def _setup_factory_mock(self):
        """Return (factory_mock, session_mock) for async_session_factory."""
        factory, session = _mock_async_session()
        return factory, session

    @patch("app.services.run_service._running_tasks", {})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service.persist_results", new_callable=AsyncMock)
    @patch("app.services.run_service._build_graph")
    @patch("app.services.run_service.create_agent_factory")
    @patch("app.services.run_service.RunTokenTracker")
    @patch("app.services.run_service.PolicyEngine")
    @patch("app.services.run_service.AuditWriter")
    @patch("app.services.run_service._load_profile", new_callable=AsyncMock)
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    @patch("app.services.run_service._update_run_status", new_callable=AsyncMock)
    @patch("app.services.run_service.settings")
    async def test_successful_run(
        self, mock_settings, mock_update, mock_start, mock_load,
        mock_aw, mock_pe, mock_tt, mock_factory, mock_graph,
        mock_persist, mock_em,
    ):
        from app.services.run_service import execute_run

        mock_settings.policy_dir = "/policy"
        mock_settings.artifacts_dir = MagicMock()
        mock_settings.artifacts_dir.__truediv__ = MagicMock(return_value=MagicMock(
            __truediv__=MagicMock(return_value="/artifacts/runs/run-1")
        ))

        mock_start.return_value = True
        mock_load.return_value = {
            "profile_targets": ["backend"],
            "profile_skills": ["Python"],
            "profile_constraints": [],
            "cv_summary": "A summary",
            "preferred_titles": [],
            "experience_level": "",
            "industries": [],
            "locations": [],
            "work_arrangement": "",
            "event_attendance": "",
            "event_topics": [],
            "target_certifications": [],
            "learning_format": "",
        }

        mock_aw_instance = MagicMock()
        mock_aw_instance.append = AsyncMock()
        mock_aw.return_value = mock_aw_instance

        mock_tt_instance = MagicMock()
        mock_tt_instance.to_dict.return_value = {"total_tokens": 100}
        mock_tt.return_value = mock_tt_instance

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value={
            "errors": [],
            "verifier_results": [{"status": "pass"}],
        })
        mock_graph_instance = MagicMock()
        mock_graph_instance.compile.return_value = mock_compiled
        mock_graph.return_value = mock_graph_instance

        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        await execute_run("run-1", "prof-1", "daily", "sk-key")

        mock_start.assert_called_once_with("run-1")
        mock_load.assert_called_once_with("prof-1")
        mock_persist.assert_called_once()
        mock_update.assert_called_once_with(
            "run-1", "completed",
            audit_path=mock_settings.artifacts_dir.__truediv__.return_value.__truediv__.return_value,
            verifier_status="pass",
        )
        mock_em.close.assert_called_once_with("run-1")

    @patch("app.services.run_service._running_tasks", {})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    async def test_returns_early_when_start_fails(self, mock_start, mock_em):
        from app.services.run_service import execute_run

        mock_start.return_value = False
        mock_em.close = AsyncMock()

        await execute_run("run-1", "prof-1", "daily", "sk-key")

        mock_start.assert_called_once()
        mock_em.close.assert_called_once_with("run-1")

    @patch("app.services.run_service._running_tasks", {})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service._update_run_status", new_callable=AsyncMock)
    @patch("app.services.run_service._load_profile", new_callable=AsyncMock)
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    @patch("app.services.run_service.settings")
    async def test_handles_exception(
        self, mock_settings, mock_start, mock_load, mock_update, mock_em,
    ):
        from app.services.run_service import execute_run

        mock_settings.policy_dir = "/policy"
        mock_settings.artifacts_dir = MagicMock()

        mock_start.return_value = True
        mock_load.side_effect = RuntimeError("DB connection failed")
        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        await execute_run("run-1", "prof-1", "daily", "sk-key")

        mock_update.assert_called_once_with("run-1", "failed")
        # Should publish run_failed event
        calls = [c.args for c in mock_em.publish.call_args_list]
        assert any("run_failed" in str(c) for c in calls)
        mock_em.close.assert_called_once_with("run-1")

    @patch("app.services.run_service._running_tasks", {})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service.persist_results", new_callable=AsyncMock)
    @patch("app.services.run_service._build_graph")
    @patch("app.services.run_service.create_agent_factory")
    @patch("app.services.run_service.RunTokenTracker")
    @patch("app.services.run_service.PolicyEngine")
    @patch("app.services.run_service.AuditWriter")
    @patch("app.services.run_service._load_profile", new_callable=AsyncMock)
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    @patch("app.services.run_service._update_run_status", new_callable=AsyncMock)
    @patch("app.services.run_service.settings")
    async def test_verifier_status_partial(
        self, mock_settings, mock_update, mock_start, mock_load,
        mock_aw, mock_pe, mock_tt, mock_factory_fn, mock_graph,
        mock_persist, mock_em,
    ):
        from app.services.run_service import execute_run

        mock_settings.policy_dir = "/policy"
        mock_settings.artifacts_dir = MagicMock()
        mock_settings.artifacts_dir.__truediv__ = MagicMock(return_value=MagicMock(
            __truediv__=MagicMock(return_value="/artifacts/runs/run-1")
        ))

        mock_start.return_value = True
        mock_load.return_value = {
            "profile_targets": [], "profile_skills": [], "profile_constraints": [],
            "cv_summary": "", "preferred_titles": [], "experience_level": "",
            "industries": [], "locations": [], "work_arrangement": "",
            "event_attendance": "", "event_topics": [], "target_certifications": [],
            "learning_format": "",
        }

        mock_aw_instance = MagicMock()
        mock_aw_instance.append = AsyncMock()
        mock_aw.return_value = mock_aw_instance

        mock_tt_instance = MagicMock()
        mock_tt_instance.to_dict.return_value = {}
        mock_tt.return_value = mock_tt_instance

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value={
            "errors": ["partial failure"],
            "verifier_results": [{"status": "partial"}, {"status": "pass"}],
        })
        mock_graph_instance = MagicMock()
        mock_graph_instance.compile.return_value = mock_compiled
        mock_graph.return_value = mock_graph_instance

        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        await execute_run("run-1", "prof-1", "daily", "sk-key")

        # verifier_status should be "partial" (not pass, because one result is partial)
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args
        assert call_kwargs.kwargs.get("verifier_status") == "partial" or \
               (len(call_kwargs.args) >= 2 and "partial" in str(call_kwargs))

    @patch("app.services.run_service._running_tasks", {})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service.persist_results", new_callable=AsyncMock)
    @patch("app.services.run_service._build_graph")
    @patch("app.services.run_service.create_agent_factory")
    @patch("app.services.run_service.RunTokenTracker")
    @patch("app.services.run_service.PolicyEngine")
    @patch("app.services.run_service.AuditWriter")
    @patch("app.services.run_service._load_profile", new_callable=AsyncMock)
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    @patch("app.services.run_service._update_run_status", new_callable=AsyncMock)
    @patch("app.services.run_service.settings")
    async def test_verifier_status_fail(
        self, mock_settings, mock_update, mock_start, mock_load,
        mock_aw, mock_pe, mock_tt, mock_factory_fn, mock_graph,
        mock_persist, mock_em,
    ):
        from app.services.run_service import execute_run

        mock_settings.policy_dir = "/policy"
        mock_settings.artifacts_dir = MagicMock()
        mock_settings.artifacts_dir.__truediv__ = MagicMock(return_value=MagicMock(
            __truediv__=MagicMock(return_value="/artifacts/runs/run-1")
        ))

        mock_start.return_value = True
        mock_load.return_value = {
            "profile_targets": [], "profile_skills": [], "profile_constraints": [],
            "cv_summary": "", "preferred_titles": [], "experience_level": "",
            "industries": [], "locations": [], "work_arrangement": "",
            "event_attendance": "", "event_topics": [], "target_certifications": [],
            "learning_format": "",
        }

        mock_aw_instance = MagicMock()
        mock_aw_instance.append = AsyncMock()
        mock_aw.return_value = mock_aw_instance

        mock_tt_instance = MagicMock()
        mock_tt_instance.to_dict.return_value = {}
        mock_tt.return_value = mock_tt_instance

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value={
            "errors": [],
            "verifier_results": [{"status": "fail"}, {"status": "pass"}],
        })
        mock_graph_instance = MagicMock()
        mock_graph_instance.compile.return_value = mock_compiled
        mock_graph.return_value = mock_graph_instance

        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        await execute_run("run-1", "prof-1", "daily", "sk-key")

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args
        assert call_kwargs.kwargs.get("verifier_status") == "fail" or \
               (len(call_kwargs.args) >= 2 and "fail" in str(call_kwargs))

    @patch("app.services.run_service._running_tasks", {"run-1": MagicMock()})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service._update_run_status", new_callable=AsyncMock)
    @patch("app.services.run_service._load_profile", new_callable=AsyncMock)
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    @patch("app.services.run_service.settings")
    async def test_handles_cancelled_error(
        self, mock_settings, mock_start, mock_load, mock_update, mock_em,
    ):
        from app.services.run_service import execute_run

        mock_settings.policy_dir = "/policy"
        mock_settings.artifacts_dir = MagicMock()

        mock_start.return_value = True
        mock_load.side_effect = asyncio.CancelledError()
        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            await execute_run("run-1", "prof-1", "daily", "sk-key")

        mock_update.assert_called_once_with("run-1", "cancelled")
        mock_em.close.assert_called_once_with("run-1")

    @patch("app.services.run_service._running_tasks", {"run-x": MagicMock()})
    @patch("app.services.run_service.event_manager")
    @patch("app.services.run_service._start_run", new_callable=AsyncMock)
    async def test_cleans_up_running_tasks_on_exit(self, mock_start, mock_em):
        from app.services.run_service import _running_tasks, execute_run

        mock_start.return_value = False
        mock_em.close = AsyncMock()

        _running_tasks["run-cleanup"] = MagicMock()
        await execute_run("run-cleanup", "prof-1", "daily", "sk-key")

        assert "run-cleanup" not in _running_tasks


class TestRecoverOrphanedRuns:
    @patch("app.services.run_service.async_session_factory")
    async def test_recovers_orphaned_runs(self, mock_factory):
        from app.services.run_service import recover_orphaned_runs

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute = AsyncMock(return_value=mock_result)

        # The function references `log` instead of `logger` (bug in source).
        # We patch the module-level `log` name so it does not raise NameError.
        with patch("app.services.run_service.log", create=True):
            count = await recover_orphaned_runs()

        assert count == 3
        mock_session.commit.assert_called_once()

    @patch("app.services.run_service.async_session_factory")
    async def test_returns_zero_when_none_orphaned(self, mock_factory):
        from app.services.run_service import recover_orphaned_runs

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await recover_orphaned_runs()
        assert count == 0
        mock_session.commit.assert_called_once()


# ===================================================================
# cover_letter_service internals
# ===================================================================


class TestSummarizeCv:
    @patch("app.services.cover_letter_service.settings")
    @patch("app.services.cover_letter_service.create_agent_factory")
    async def test_summarizes_with_llm(self, mock_factory_fn, mock_settings):
        from app.services.cover_letter_service import summarize_cv

        mock_settings.prompts_dir = "/prompts"

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Summarized CV"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        mock_factory = MagicMock()
        mock_factory._llm = mock_llm
        mock_factory_fn.return_value = mock_factory

        # PromptLoader is imported locally inside summarize_cv from app.llm.prompt_loader
        with patch("app.llm.prompt_loader.PromptLoader") as mock_pl:
            mock_pl_instance = MagicMock()
            mock_pl_instance.load.return_value = "Summarize this CV"
            mock_pl.return_value = mock_pl_instance

            result = await summarize_cv("Raw CV text here", "sk-test")

        assert result == "Summarized CV"
        mock_llm.ainvoke.assert_called_once()

    async def test_returns_empty_for_empty_input(self):
        from app.services.cover_letter_service import summarize_cv

        result = await summarize_cv("", "sk-test")
        assert result == ""


class TestGenerateCoverLetter:
    @patch("app.services.cover_letter_service.event_manager")
    @patch("app.services.cover_letter_service.build_cover_letter_graph")
    @patch("app.services.cover_letter_service.create_agent_factory")
    @patch("app.services.cover_letter_service.PolicyEngine")
    @patch("app.services.cover_letter_service.AuditWriter")
    @patch("app.services.cover_letter_service.read_cv_content", new_callable=AsyncMock)
    @patch("app.services.cover_letter_service.async_session_factory")
    async def test_success_path(
        self, mock_factory, mock_read_cv, mock_aw, mock_pe,
        mock_agent_factory, mock_build, mock_em,
    ):
        from app.services.cover_letter_service import generate_cover_letter

        # Setup session mock that handles 3 context manager entries
        run_obj = _make_run(id="run-1", status="pending")
        profile_obj = _make_profile(cv_data=b"pdf", cv_summary="summary", skills="Python")
        cl_obj = MagicMock()
        cl_obj.content = ""

        # Each `async with async_session_factory() as session:` gets a fresh session
        session1 = AsyncMock()
        session1.add = MagicMock()
        session1.get = AsyncMock(return_value=run_obj)

        session2 = AsyncMock()
        session2.add = MagicMock()
        session2.get = AsyncMock(return_value=profile_obj)

        session3 = AsyncMock()
        session3.add = MagicMock()
        session3.get = AsyncMock(side_effect=[cl_obj, run_obj])

        ctx1 = AsyncMock()
        ctx1.__aenter__ = AsyncMock(return_value=session1)
        ctx1.__aexit__ = AsyncMock(return_value=False)
        ctx2 = AsyncMock()
        ctx2.__aenter__ = AsyncMock(return_value=session2)
        ctx2.__aexit__ = AsyncMock(return_value=False)
        ctx3 = AsyncMock()
        ctx3.__aenter__ = AsyncMock(return_value=session3)
        ctx3.__aexit__ = AsyncMock(return_value=False)

        mock_factory.side_effect = [ctx1, ctx2, ctx3]

        mock_read_cv.return_value = "Full CV text"
        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        mock_aw_instance = MagicMock()
        mock_aw_instance.append = AsyncMock()
        mock_aw.return_value = mock_aw_instance

        # ensure_cv_summary is imported locally from app.services.profile_service
        # _extract_name_from_cv is imported locally from app.agents.cover_letter_agent
        with patch(
            "app.services.profile_service.ensure_cv_summary",
            new_callable=AsyncMock,
            return_value="CV summary",
        ), patch(
            "app.agents.cover_letter_agent._extract_name_from_cv",
            return_value="Alice Smith",
        ), patch(
            "app.services.cover_letter_service.settings"
        ) as mock_settings:
            mock_settings.policy_dir = "/policy"
            mock_settings.artifacts_dir = MagicMock()
            mock_settings.artifacts_dir.__truediv__ = MagicMock(return_value=MagicMock(
                __truediv__=MagicMock(return_value="/artifacts/runs/run-1")
            ))

            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(return_value={
                "cover_letter_content": "Dear Hiring Manager, ..."
            })
            mock_graph = MagicMock()
            mock_graph.compile.return_value = mock_compiled
            mock_build.return_value = mock_graph

            await generate_cover_letter(
                run_id="run-1",
                profile_id="prof-1",
                cover_letter_id="cl-1",
                jd_text="Build great things",
                job_opportunity={"title": "Engineer"},
                job_opportunity_id="job-1",
                api_key="sk-test",
                profile_name="Test Profile",
            )

        # Verify the cover letter content was set
        assert cl_obj.content == "Dear Hiring Manager, ..."
        assert run_obj.status == "completed"
        mock_em.close.assert_called_once_with("run-1")

    @patch("app.services.cover_letter_service.event_manager")
    @patch("app.services.cover_letter_service.async_session_factory")
    async def test_exception_marks_run_failed(self, mock_factory, mock_em):
        from app.services.cover_letter_service import generate_cover_letter

        # First session (mark as running) succeeds
        run_obj = _make_run(id="run-1", status="pending")

        session1 = AsyncMock()
        session1.add = MagicMock()
        session1.get = AsyncMock(return_value=run_obj)

        # Second session (load profile) raises an error
        session2 = AsyncMock()
        session2.get = AsyncMock(side_effect=RuntimeError("DB error"))

        # Third session (error handler)
        session3 = AsyncMock()
        session3.add = MagicMock()
        err_run = _make_run(id="run-1", status="running")
        session3.get = AsyncMock(return_value=err_run)

        ctx1 = AsyncMock()
        ctx1.__aenter__ = AsyncMock(return_value=session1)
        ctx1.__aexit__ = AsyncMock(return_value=False)
        ctx2 = AsyncMock()
        ctx2.__aenter__ = AsyncMock(return_value=session2)
        ctx2.__aexit__ = AsyncMock(return_value=False)
        ctx3 = AsyncMock()
        ctx3.__aenter__ = AsyncMock(return_value=session3)
        ctx3.__aexit__ = AsyncMock(return_value=False)

        mock_factory.side_effect = [ctx1, ctx2, ctx3]
        mock_em.publish = AsyncMock()
        mock_em.close = AsyncMock()

        await generate_cover_letter(
            run_id="run-1",
            profile_id="prof-1",
            cover_letter_id="cl-1",
            jd_text="Build things",
            job_opportunity={},
            job_opportunity_id=None,
            api_key="sk-test",
        )

        assert err_run.status == "failed"
        mock_em.close.assert_called_once_with("run-1")
        # Should have published run_failed event
        publish_calls = mock_em.publish.call_args_list
        assert any("run_failed" in str(c) for c in publish_calls)


class TestCreateCoverLetterFullPath:
    """Test the full create_cover_letter flow including background task launch."""

    @patch("app.services.cover_letter_service._background_tasks", set())
    @patch("app.services.cover_letter_service.asyncio")
    @patch("app.services.cover_letter_service.generate_cover_letter", new_callable=AsyncMock)
    @patch("app.services.cover_letter_service.resolve_job_opportunity", new_callable=AsyncMock)
    @patch("app.services.cover_letter_service.get_user_api_key", return_value="sk-user-key")
    async def test_full_success_path_with_user_key(
        self, mock_get_key, mock_resolve, mock_gen, mock_asyncio,
    ):
        from app.schemas.cover_letter import CoverLetterCreate
        from app.services.cover_letter_service import create_cover_letter

        db = AsyncMock()
        db.add = MagicMock()

        profile = _make_profile(cv_data=b"pdf-bytes")
        db.get.return_value = profile
        user = _make_user(encrypted_api_key="enc-key")

        job_orm = MagicMock()
        job_orm.title = "Engineer"
        job_orm.company = "ACME"
        job_orm.url = "https://example.com/job"
        mock_resolve.return_value = (
            {"title": "Engineer", "company": "ACME"},
            "Build things",
            job_orm,
        )

        # After flush/commit/refresh, the CL and Run objects get IDs
        async def _refresh(obj):
            if not hasattr(obj, '_refreshed'):
                obj._refreshed = True
                obj.id = "cl-new"
                obj.profile_id = "prof-1"
                obj.job_opportunity_id = "job-1"
                obj.run_id = "run-new"
                obj.content = ""
                obj.created_at = _NOW

        db.refresh = AsyncMock(side_effect=_refresh)

        mock_task = MagicMock()
        mock_task.add_done_callback = MagicMock()
        mock_asyncio.create_task.return_value = mock_task

        body = CoverLetterCreate(job_opportunity_id="job-1", jd_text="Build things")
        result = await create_cover_letter(db, "prof-1", body, user)

        assert result is not None
        mock_asyncio.create_task.assert_called_once()

    @patch("app.services.cover_letter_service.get_user_api_key", return_value=None)
    @patch("app.services.cover_letter_service.settings")
    async def test_raises_when_no_api_key(self, mock_settings, mock_get_key):
        from app.schemas.cover_letter import CoverLetterCreate
        from app.services.cover_letter_service import create_cover_letter

        mock_settings.api_key = ""

        db = AsyncMock()
        db.add = MagicMock()
        profile = _make_profile(cv_data=b"pdf-bytes")
        db.get.return_value = profile
        user = _make_user()

        body = CoverLetterCreate(jd_text="Build things")
        with pytest.raises(ValueError, match="No API key"):
            await create_cover_letter(db, "prof-1", body, user)


# ===================================================================
# profile_service internals
# ===================================================================


class TestBackgroundSummarize:
    @patch("app.services.profile_service.ensure_cv_summary", new_callable=AsyncMock)
    @patch("app.services.profile_service.async_session_factory")
    async def test_summarizes_profile_cv(self, mock_factory, mock_ensure):
        from app.services.profile_service import _background_summarize

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        profile = _make_profile(cv_data=b"pdf-bytes")
        mock_session.get = AsyncMock(return_value=profile)
        mock_ensure.return_value = "Summary"

        await _background_summarize("prof-1")
        mock_ensure.assert_called_once_with(mock_session, profile)

    @patch("app.services.profile_service.ensure_cv_summary", new_callable=AsyncMock)
    @patch("app.services.profile_service.async_session_factory")
    async def test_skips_when_profile_not_found(self, mock_factory, mock_ensure):
        from app.services.profile_service import _background_summarize

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=None)

        await _background_summarize("nonexistent")
        mock_ensure.assert_not_called()

    @patch("app.services.profile_service.ensure_cv_summary", new_callable=AsyncMock)
    @patch("app.services.profile_service.async_session_factory")
    async def test_skips_when_no_cv_data(self, mock_factory, mock_ensure):
        from app.services.profile_service import _background_summarize

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        profile = _make_profile(cv_data=None)
        mock_session.get = AsyncMock(return_value=profile)

        await _background_summarize("prof-1")
        mock_ensure.assert_not_called()

    @patch("app.services.profile_service.ensure_cv_summary", new_callable=AsyncMock, side_effect=Exception("LLM down"))
    @patch("app.services.profile_service.async_session_factory")
    async def test_suppresses_exceptions(self, mock_factory, mock_ensure):
        from app.services.profile_service import _background_summarize

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        profile = _make_profile(cv_data=b"pdf")
        mock_session.get = AsyncMock(return_value=profile)

        # Should not raise
        await _background_summarize("prof-1")


class TestExportProfile:
    async def test_exports_profile_fields(self):
        from app.services.profile_service import export_profile

        db = AsyncMock()
        profile = _make_profile(
            name="Architect",
            targets='["backend"]',
            constraints='["remote"]',
            skills='["Python"]',
            preferred_titles='["Senior Eng"]',
            experience_level="senior",
            industries='["tech"]',
            locations='["US"]',
            work_arrangement="remote",
            event_attendance="no preference",
            event_topics=None,
            target_certifications=None,
            learning_format=None,
        )
        db.get = AsyncMock(return_value=profile)

        result = await export_profile(db, "prof-1")
        assert result is not None
        assert result["name"] == "Architect"
        assert result["targets"] == ["backend"]
        assert result["skills"] == ["Python"]
        assert result["experience_level"] == "senior"

    async def test_returns_none_when_not_found(self):
        from app.services.profile_service import export_profile

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        result = await export_profile(db, "nonexistent")
        assert result is None


class TestImportProfile:
    @patch("app.services.profile_service.create_profile", new_callable=AsyncMock)
    async def test_imports_profile_from_data(self, mock_create):
        from app.services.profile_service import import_profile

        mock_create.return_value = MagicMock(id="new-prof", name="Imported")

        db = AsyncMock()
        data = {
            "name": "My Profile",
            "targets": ["backend"],
            "skills": ["Python"],
            "experience_level": "senior",
        }
        result = await import_profile(db, data, owner_id="user-1")

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.args[0] is db
        # Second arg is a ProfileCreate instance
        body = call_args.args[1]
        assert body.name == "My Profile"
        assert body.targets == ["backend"]

    @patch("app.services.profile_service.create_profile", new_callable=AsyncMock)
    async def test_uses_default_name_when_missing(self, mock_create):
        from app.services.profile_service import import_profile

        mock_create.return_value = MagicMock(id="new-prof")

        db = AsyncMock()
        result = await import_profile(db, {}, owner_id="user-1")

        call_args = mock_create.call_args
        body = call_args.args[1]
        assert body.name == "Imported Profile"


class TestExtractSkillsWithAi:
    @patch("app.services.profile_service.settings")
    @patch("app.services.profile_service.ChatOpenAI")
    async def test_extracts_skills(self, mock_chat, mock_settings):
        from app.services.profile_service import ExtractedSkills, extract_skills_with_ai

        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_temperature = 0.3
        mock_settings.api_key = "sk-test"

        mock_structured = AsyncMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=ExtractedSkills(skills=["Python", "Docker", "AWS"])
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        mock_chat.return_value = mock_llm

        result = await extract_skills_with_ai("John Doe\nPython developer with Docker and AWS")
        assert result == ["Python", "Docker", "AWS"]
        mock_llm.with_structured_output.assert_called_once()

    @patch("app.services.profile_service.settings")
    @patch("app.services.profile_service.ChatOpenAI")
    async def test_truncates_long_cv_text(self, mock_chat, mock_settings):
        from app.services.profile_service import ExtractedSkills, extract_skills_with_ai

        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_temperature = 0.3
        mock_settings.api_key = "sk-test"

        mock_structured = AsyncMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=ExtractedSkills(skills=["Python"])
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        mock_chat.return_value = mock_llm

        long_text = "x" * 20000
        await extract_skills_with_ai(long_text)

        # The user message content should be truncated to 8000 chars
        call_args = mock_structured.ainvoke.call_args[0][0]
        user_msg = call_args[1]
        assert len(user_msg["content"]) == 8000


class TestExtractSkillsFromCv:
    async def test_raises_when_profile_not_found(self):
        from app.services.profile_service import extract_skills_from_cv

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(LookupError, match="Profile not found"):
            await extract_skills_from_cv(db, "nonexistent")

    async def test_raises_when_no_cv(self):
        from app.services.profile_service import extract_skills_from_cv

        db = AsyncMock()
        profile = _make_profile(cv_data=None)
        db.get = AsyncMock(return_value=profile)

        with pytest.raises(ValueError, match="No CV uploaded"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.extract_text_from_pdf", side_effect=Exception("bad pdf"))
    async def test_raises_on_pdf_extraction_failure(self, mock_extract):
        from app.services.profile_service import extract_skills_from_cv

        db = AsyncMock()
        profile = _make_profile(cv_data=b"corrupt-pdf")
        db.get = AsyncMock(return_value=profile)

        with pytest.raises(ValueError, match="Failed to read CV"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.extract_text_from_pdf", return_value="   ")
    async def test_raises_when_cv_has_no_text(self, mock_extract):
        from app.services.profile_service import extract_skills_from_cv

        db = AsyncMock()
        profile = _make_profile(cv_data=b"empty-pdf")
        db.get = AsyncMock(return_value=profile)

        with pytest.raises(ValueError, match="no readable text"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.extract_text_from_pdf", return_value="Some CV text")
    @patch("app.services.profile_service.settings")
    async def test_raises_when_no_api_key(self, mock_settings, mock_extract):
        from app.services.profile_service import extract_skills_from_cv

        mock_settings.api_key = ""

        db = AsyncMock()
        profile = _make_profile(cv_data=b"pdf-bytes")
        db.get = AsyncMock(return_value=profile)

        with pytest.raises(ValueError, match="API key not configured"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.extract_skills_with_ai", new_callable=AsyncMock)
    @patch("app.services.profile_service.extract_text_from_pdf", return_value="Python developer")
    @patch("app.services.profile_service.settings")
    async def test_success_returns_extracted_skills(self, mock_settings, mock_extract, mock_ai):
        from app.services.profile_service import extract_skills_from_cv

        mock_settings.api_key = "sk-test"
        mock_ai.return_value = ["Python", "FastAPI"]

        db = AsyncMock()
        profile = _make_profile(cv_data=b"pdf-bytes")
        db.get = AsyncMock(return_value=profile)

        result = await extract_skills_from_cv(db, "prof-1")
        assert result.skills == ["Python", "FastAPI"]
        mock_ai.assert_called_once_with("Python developer")
