"""Tests for agent modules: base, goal_extractor, cover_letter, data_formatter, ceo, cfo, factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import LLMAgent, _extract_first_json, _get_raw_json_content
from app.agents.ceo_agent import CEOAgent
from app.agents.cfo_agent import CFOAgent
from app.agents.cover_letter_agent import (
    CoverLetterAgent,
    _extract_name_from_cv,
    _strip_markdown,
)
from app.agents.data_formatter import DataFormatterAgent, _dedup
from app.agents.factory import AgentFactory, AgentModelConfig
from app.agents.goal_extractor import GoalExtractorAgent
from app.agents.schemas import (
    CEOOutput,
    CFOOutput,
    DataFormatterOutput,
    FormattedCertification,
    FormattedCourse,
    FormattedEvent,
    FormattedGroup,
    FormattedJob,
    FormattedTrend,
    GoalExtractorOutput,
    RiskAssessment,
    StrategicRecommendation,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_mock_llm(model_name: str = "gpt-4o-mini") -> MagicMock:
    """Create a mock LLM with standard attributes."""
    llm = MagicMock()
    llm.model_name = model_name
    llm.model = model_name
    llm.temperature = 0.7
    llm.openai_api_key = "sk-test-key"
    return llm


def _make_structured_result(parsed: Any, raw_content: str = "", usage: dict | None = None):
    """Build a dict mimicking with_structured_output(include_raw=True) results."""
    raw = MagicMock()
    raw.content = raw_content
    if usage is not None:
        raw.usage_metadata = usage
    else:
        raw.usage_metadata = None
    return {"raw": raw, "parsed": parsed, "parsing_error": None}


# ------------------------------------------------------------------
# base.py
# ------------------------------------------------------------------


class TestExtractFirstJson:
    """Tests for _extract_first_json."""

    def test_valid_json_object(self):
        from app.agents.schemas import GoalExtractorOutput

        text = '{"cert_prompt": "a", "course_prompt": "b", "event_prompt": "c", "group_prompt": "d", "trend_prompt": "e"}'
        result = _extract_first_json(text, GoalExtractorOutput)
        assert result is not None
        assert result.cert_prompt == "a"

    def test_json_with_trailing_text(self):
        from app.agents.schemas import GoalExtractorOutput

        text = '{"cert_prompt": "a", "course_prompt": "b", "event_prompt": "c", "group_prompt": "d", "trend_prompt": "e"} some trailing garbage'
        result = _extract_first_json(text, GoalExtractorOutput)
        assert result is not None
        assert result.trend_prompt == "e"

    def test_invalid_json_returns_none(self):
        result = _extract_first_json("not json at all", GoalExtractorOutput)
        assert result is None

    def test_empty_string_returns_none(self):
        result = _extract_first_json("", GoalExtractorOutput)
        assert result is None


class TestGetRawJsonContent:
    """Tests for _get_raw_json_content."""

    def test_none_raw_returns_empty(self):
        assert _get_raw_json_content(None) == ""

    def test_content_from_content_attr(self):
        raw = MagicMock()
        raw.content = '{"key": "val"}'
        assert _get_raw_json_content(raw) == '{"key": "val"}'

    def test_content_from_tool_calls(self):
        raw = MagicMock()
        raw.content = ""
        raw.additional_kwargs = {
            "tool_calls": [{"function": {"arguments": '{"a": 1}'}}],
        }
        assert _get_raw_json_content(raw) == '{"a": 1}'

    def test_content_from_function_call(self):
        raw = MagicMock()
        raw.content = ""
        raw.additional_kwargs = {"function_call": {"arguments": '{"b": 2}'}}
        assert _get_raw_json_content(raw) == '{"b": 2}'

    def test_no_content_anywhere(self):
        raw = MagicMock()
        raw.content = ""
        raw.additional_kwargs = {}
        assert _get_raw_json_content(raw) == ""


class TestLLMAgent:
    """Tests for the LLMAgent base class."""

    def test_init_stores_llm_and_prompt_loader(self):
        llm = _make_mock_llm()
        loader = MagicMock()
        agent = LLMAgent(llm=llm, prompt_loader=loader)
        assert agent._llm is llm
        assert agent._prompt_loader is loader

    def test_model_name_from_model_name_attr(self):
        llm = _make_mock_llm("gpt-4o")
        agent = LLMAgent(llm=llm)
        assert agent._model_name == "gpt-4o"

    def test_model_name_fallback_to_model(self):
        llm = MagicMock(spec=[])
        llm.model = "gpt-3.5-turbo"
        agent = LLMAgent(llm=llm)
        # model_name attr does not exist, falls through to .model
        assert agent._model_name == "gpt-3.5-turbo"

    def test_get_system_prompt_without_loader(self):
        agent = LLMAgent(llm=_make_mock_llm(), prompt_loader=None)
        agent.agent_name = "test_agent"
        prompt = agent._get_system_prompt()
        assert "test_agent" in prompt

    def test_get_system_prompt_with_loader(self):
        loader = MagicMock()
        loader.load.return_value = "Custom prompt for {today}"
        agent = LLMAgent(llm=_make_mock_llm(), prompt_loader=loader)
        agent.agent_name = "goal_extractor"
        prompt = agent._get_system_prompt(today="2026-01-01")
        loader.load.assert_called_once_with("goal_extractor", today="2026-01-01")

    async def test_try_structured_methods_succeeds_on_first_try(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        expected_result = {"raw": MagicMock(), "parsed": MagicMock(), "parsing_error": None}
        structured_llm = AsyncMock()
        structured_llm.ainvoke.return_value = expected_result
        llm.with_structured_output.return_value = structured_llm

        result = await agent._try_structured_methods(GoalExtractorOutput, [])
        assert result is expected_result

    async def test_try_structured_methods_falls_back_on_failure(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        # First call (json_schema) raises, second (function_calling) succeeds
        expected = {"raw": MagicMock(), "parsed": MagicMock(), "parsing_error": None}
        failing_llm = AsyncMock()
        failing_llm.ainvoke.side_effect = ValueError("json_schema not supported")
        succeeding_llm = AsyncMock()
        succeeding_llm.ainvoke.return_value = expected

        llm.with_structured_output.side_effect = [failing_llm, succeeding_llm]
        result = await agent._try_structured_methods(GoalExtractorOutput, [])
        assert result is expected

    async def test_try_structured_methods_all_fail_raises(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        failing_llm = AsyncMock()
        failing_llm.ainvoke.side_effect = ValueError("nope")
        llm.with_structured_output.return_value = failing_llm

        with pytest.raises(ValueError, match="nope"):
            await agent._try_structured_methods(GoalExtractorOutput, [])

    async def test_try_structured_methods_all_return_none_raises(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        none_llm = AsyncMock()
        none_llm.ainvoke.return_value = None
        llm.with_structured_output.return_value = none_llm

        with pytest.raises(ValueError, match="Structured output returned None"):
            await agent._try_structured_methods(GoalExtractorOutput, [])

    def test_recover_parsed_output_success(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        parsed = GoalExtractorOutput(
            cert_prompt="a", course_prompt="b", event_prompt="c",
            group_prompt="d", trend_prompt="e",
        )
        usage_meta = {"input_tokens": 100, "output_tokens": 50}
        result = _make_structured_result(parsed, usage=usage_meta)

        out, usage = agent._recover_parsed_output(result, GoalExtractorOutput)
        assert out is parsed
        assert usage is not None
        assert usage["model_name"] == "gpt-4o-mini"
        assert usage["input_tokens"] == 100

    def test_recover_parsed_output_no_usage(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        parsed = MagicMock()
        result = _make_structured_result(parsed, usage=None)

        out, usage = agent._recover_parsed_output(result, GoalExtractorOutput)
        assert out is parsed
        assert usage is None

    def test_recover_parsed_output_fallback_raw_decode(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        json_str = '{"cert_prompt":"a","course_prompt":"b","event_prompt":"c","group_prompt":"d","trend_prompt":"e"}'
        raw = MagicMock()
        raw.content = json_str
        raw.usage_metadata = None
        result = {"raw": raw, "parsed": None, "parsing_error": ValueError("parse failed")}

        out, usage = agent._recover_parsed_output(result, GoalExtractorOutput)
        assert out is not None
        assert out.cert_prompt == "a"

    def test_recover_parsed_output_raises_when_unrecoverable(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        raw = MagicMock()
        raw.content = "not json"
        raw.usage_metadata = None
        err = ValueError("original parse error")
        result = {"raw": raw, "parsed": None, "parsing_error": err}

        with pytest.raises(ValueError, match="original parse error"):
            agent._recover_parsed_output(result, GoalExtractorOutput)

    async def test_invoke_structured_builds_messages_and_delegates(self):
        llm = _make_mock_llm()
        agent = LLMAgent(llm=llm)

        parsed = MagicMock()
        usage_meta = {"input_tokens": 10, "output_tokens": 5}

        structured_llm = AsyncMock()
        structured_llm.ainvoke.return_value = _make_structured_result(parsed, usage=usage_meta)
        llm.with_structured_output.return_value = structured_llm

        out, usage = await agent._invoke_structured(
            GoalExtractorOutput, "system prompt", "user content",
        )
        assert out is parsed
        # Verify messages structure
        call_args = structured_llm.ainvoke.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert call_args[1]["role"] == "user"


# ------------------------------------------------------------------
# goal_extractor.py
# ------------------------------------------------------------------


class TestGoalExtractorAgent:
    """Tests for GoalExtractorAgent."""

    def test_build_job_prompt_basic(self):
        prompt = GoalExtractorAgent._build_job_prompt(
            preferred_titles=["Software Engineer"],
        )
        assert "Software Engineer" in prompt
        assert "job openings" in prompt
        assert "Search LinkedIn for" in prompt

    def test_build_job_prompt_with_all_fields(self):
        prompt = GoalExtractorAgent._build_job_prompt(
            preferred_titles=["Data Scientist", "ML Engineer"],
            experience_level="senior",
            industries=["tech", "finance"],
            locations=["New York", "London"],
            work_arrangement="hybrid",
            constraints=["No travel", "Visa sponsorship"],
        )
        assert "Data Scientist and ML Engineer" in prompt
        assert "senior" in prompt
        assert "tech and finance" in prompt
        assert "New York, London" in prompt
        assert "no travel" in prompt
        assert "hybrid" in prompt

    def test_build_job_prompt_remote_skips_location(self):
        prompt = GoalExtractorAgent._build_job_prompt(
            preferred_titles=["Developer"],
            locations=["SF"],
            work_arrangement="remote",
        )
        assert "SF" not in prompt
        assert "remote" in prompt

    def test_build_job_prompt_no_constraints(self):
        prompt = GoalExtractorAgent._build_job_prompt(
            preferred_titles=["Analyst"],
        )
        assert "with" not in prompt

    async def test_call_returns_search_prompts(self):
        llm = _make_mock_llm()
        agent = GoalExtractorAgent(llm=llm)

        parsed = GoalExtractorOutput(
            cert_prompt="Find AWS certs",
            course_prompt="Find ML courses",
            event_prompt="Find AI conferences",
            group_prompt="Find dev communities",
            trend_prompt="Find tech trends",
        )
        usage = {"input_tokens": 50, "output_tokens": 30}

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, usage)
            state = {
                "profile_targets": ["become ML engineer"],
                "preferred_titles": ["ML Engineer"],
            }
            result = await agent(state)

        assert "search_prompts" in result
        prompts = result["search_prompts"]
        assert prompts["cert_prompt"] == "Find AWS certs"
        assert prompts["course_prompt"] == "Find ML courses"
        # job_prompt is built deterministically, not from LLM
        assert "ML Engineer" in prompts["job_prompt"]
        assert result["_token_usage"] == [usage]

    async def test_call_no_usage(self):
        llm = _make_mock_llm()
        agent = GoalExtractorAgent(llm=llm)

        parsed = GoalExtractorOutput(
            cert_prompt="a", course_prompt="b", event_prompt="c",
            group_prompt="d", trend_prompt="e",
        )

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, None)
            result = await agent({"preferred_titles": ["Dev"]})

        assert result["_token_usage"] == []

    async def test_call_includes_cv_summary_in_prompt(self):
        llm = _make_mock_llm()
        agent = GoalExtractorAgent(llm=llm)

        parsed = GoalExtractorOutput(
            cert_prompt="a", course_prompt="b", event_prompt="c",
            group_prompt="d", trend_prompt="e",
        )

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, None)
            state = {
                "preferred_titles": ["Eng"],
                "cv_summary": "Experienced developer with 10 years",
                "profile_constraints": ["No relocation"],
                "experience_level": "senior",
                "industries": ["tech"],
                "locations": ["NYC"],
                "work_arrangement": "hybrid",
                "event_attendance": "virtual",
                "event_topics": ["AI"],
                "target_certifications": ["AWS SAA"],
                "learning_format": "self-paced",
            }
            result = await agent(state)

        # Verify _invoke_structured was called with proper user_content
        call_args = mock_invoke.call_args
        user_content = call_args[0][2]  # third positional arg
        assert "CV summary:" in user_content
        assert "Experienced developer" in user_content
        assert "No relocation" in user_content
        assert "senior" in user_content
        assert "tech" in user_content
        assert "NYC" in user_content
        assert "hybrid" in user_content
        assert "virtual" in user_content
        assert "AI" in user_content
        assert "AWS SAA" in user_content
        assert "self-paced" in user_content


# ------------------------------------------------------------------
# cover_letter_agent.py
# ------------------------------------------------------------------


class TestStripMarkdown:
    """Tests for _strip_markdown pure function."""

    def test_removes_headers(self):
        assert _strip_markdown("### Title") == "Title"
        assert _strip_markdown("# H1") == "H1"

    def test_removes_bold_italic(self):
        assert _strip_markdown("**bold**") == "bold"
        assert _strip_markdown("*italic*") == "italic"
        assert _strip_markdown("***both***") == "both"

    def test_removes_bullets(self):
        result = _strip_markdown("- item1\n- item2")
        assert "item1" in result
        assert "item2" in result
        assert "-" not in result

    def test_collapses_newlines(self):
        result = _strip_markdown("line1\n\n\nline2")
        assert "\n" not in result
        assert "line1" in result

    def test_collapses_spaces(self):
        result = _strip_markdown("a    b")
        assert result == "a b"

    def test_empty_string(self):
        assert _strip_markdown("") == ""


class TestExtractNameFromCv:
    """Tests for _extract_name_from_cv."""

    def test_simple_name(self):
        assert _extract_name_from_cv("John Doe\nProfessional Summary\n...") == "John Doe"

    def test_three_word_name(self):
        assert _extract_name_from_cv("Mary Jane Watson") == "Mary Jane Watson"

    def test_four_word_name(self):
        assert _extract_name_from_cv("Mary Jane Watson Smith") == "Mary Jane Watson Smith"

    def test_skips_section_headers(self):
        # "Professional Summary" is skipped, but "Some text" is 2 alpha words, so it's treated as a name
        # Only a CV with headers followed by non-name content returns None
        assert _extract_name_from_cv("Professional Summary\n12345") is None

    def test_section_header_alone(self):
        assert _extract_name_from_cv("Summary") is None

    def test_returns_none_for_empty(self):
        assert _extract_name_from_cv("") is None
        assert _extract_name_from_cv("   ") is None

    def test_returns_none_for_non_name(self):
        # Single word is not a name (< 2 words)
        assert _extract_name_from_cv("Administrator") is None

    def test_strips_markdown_from_name(self):
        assert _extract_name_from_cv("### John Doe") == "John Doe"
        assert _extract_name_from_cv("**Jane Smith**") == "Jane Smith"

    def test_name_with_numbers_returns_none(self):
        # "Phone: 123" has non-alpha words
        assert _extract_name_from_cv("Phone 1234567") is None

    def test_five_word_line_returns_none(self):
        # More than 4 words
        assert _extract_name_from_cv("This Is Not A Name Really") is None


class TestCoverLetterAgent:
    """Tests for CoverLetterAgent.__call__."""

    async def test_call_generates_cover_letter(self):
        llm = _make_mock_llm()
        response = MagicMock()
        response.content = "Dear Hiring Manager, I am writing to apply..."
        response.usage_metadata = {"input_tokens": 200, "output_tokens": 150}
        llm.ainvoke = AsyncMock(return_value=response)

        agent = CoverLetterAgent(llm=llm)
        state = {
            "cv_content": "John Doe, Software Engineer...",
            "jd_text": "We need a senior engineer...",
            "profile_name": "Dev Profile",
            "profile_targets": ["Sr Engineer"],
            "profile_skills": ["Python", "AWS"],
            "profile_constraints": ["Remote only"],
            "job_opportunity": {"title": "Senior Engineer"},
        }
        result = await agent(state)

        assert "cover_letter_content" in result
        assert "Dear Hiring Manager" in result["cover_letter_content"]
        assert result["_token_usage"][0]["input_tokens"] == 200
        assert result["_token_usage"][0]["model_name"] == "gpt-4o-mini"

    async def test_call_replaces_em_dashes(self):
        llm = _make_mock_llm()
        response = MagicMock()
        response.content = "strong skills \u2014 leadership \u2013 teamwork"
        response.usage_metadata = None
        llm.ainvoke = AsyncMock(return_value=response)

        agent = CoverLetterAgent(llm=llm)
        result = await agent({"cv_content": "cv", "jd_text": "jd"})

        assert "\u2014" not in result["cover_letter_content"]
        assert "\u2013" not in result["cover_letter_content"]

    async def test_call_no_usage_metadata(self):
        llm = _make_mock_llm()
        response = MagicMock()
        response.content = "Letter content"
        response.usage_metadata = None
        llm.ainvoke = AsyncMock(return_value=response)

        agent = CoverLetterAgent(llm=llm)
        result = await agent({"cv_content": "cv", "jd_text": "jd"})

        assert result["_token_usage"] == []

    async def test_call_builds_user_content_sections(self):
        llm = _make_mock_llm()
        response = MagicMock()
        response.content = "Letter"
        response.usage_metadata = None
        llm.ainvoke = AsyncMock(return_value=response)

        agent = CoverLetterAgent(llm=llm)
        state = {
            "cv_content": "My CV",
            "jd_text": "Job desc",
            "profile_name": "Test",
            "profile_targets": ["Target1"],
            "profile_skills": ["Skill1"],
            "profile_constraints": ["Constraint1"],
            "job_opportunity": {},
        }
        await agent(state)

        call_args = llm.ainvoke.call_args[0][0]
        user_msg = call_args[1]["content"]
        assert "## Candidate Name" in user_msg
        assert "Test" in user_msg
        assert "## Career Targets" in user_msg
        assert "## Key Skills" in user_msg
        assert "## Constraints/Preferences" in user_msg
        assert "## CV Summary" in user_msg
        assert "## Job Description" in user_msg


# ------------------------------------------------------------------
# data_formatter.py
# ------------------------------------------------------------------


class TestDedup:
    """Tests for _dedup pure function."""

    def test_removes_duplicates(self):
        items = [
            FormattedJob(title="Engineer", company="A"),
            FormattedJob(title="Engineer", company="B"),
            FormattedJob(title="Manager", company="C"),
        ]
        result = _dedup(items)
        assert len(result) == 2
        assert result[0]["title"] == "Engineer"
        assert result[0]["company"] == "A"
        assert result[1]["title"] == "Manager"

    def test_empty_list(self):
        assert _dedup([]) == []

    def test_no_duplicates(self):
        items = [
            FormattedCertification(title="AWS SAA"),
            FormattedCertification(title="GCP ACE"),
        ]
        result = _dedup(items)
        assert len(result) == 2

    def test_all_duplicates(self):
        items = [
            FormattedTrend(title="AI Trend"),
            FormattedTrend(title="AI Trend"),
            FormattedTrend(title="AI Trend"),
        ]
        result = _dedup(items)
        assert len(result) == 1


class TestDataFormatterAgent:
    """Tests for DataFormatterAgent.__call__."""

    async def test_call_formats_all_categories(self):
        llm = _make_mock_llm()
        agent = DataFormatterAgent(llm=llm)

        parsed = DataFormatterOutput(
            jobs=[FormattedJob(title="Dev", company="Co")],
            certifications=[FormattedCertification(title="AWS")],
            courses=[FormattedCourse(title="ML 101")],
            events=[FormattedEvent(title="PyCon")],
            groups=[FormattedGroup(title="Python Users")],
            trends=[FormattedTrend(title="AI Boom")],
        )
        usage = {"input_tokens": 100, "output_tokens": 80}

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, usage)
            state = {
                "raw_job_results": [{"title": "Dev"}],
                "raw_cert_results": [],
                "raw_course_results": [],
                "raw_event_results": [],
                "raw_group_results": [],
                "raw_trend_results": [],
            }
            result = await agent(state)

        assert len(result["formatted_jobs"]) == 1
        assert result["formatted_jobs"][0]["title"] == "Dev"
        assert len(result["formatted_certifications"]) == 1
        assert len(result["formatted_courses"]) == 1
        assert len(result["formatted_events"]) == 1
        assert len(result["formatted_groups"]) == 1
        assert len(result["formatted_trends"]) == 1
        assert result["_token_usage"] == [usage]

    async def test_call_deduplicates_results(self):
        llm = _make_mock_llm()
        agent = DataFormatterAgent(llm=llm)

        parsed = DataFormatterOutput(
            jobs=[
                FormattedJob(title="Same Job", company="A"),
                FormattedJob(title="Same Job", company="B"),
            ],
        )

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, None)
            result = await agent({})

        assert len(result["formatted_jobs"]) == 1
        assert result["_token_usage"] == []

    async def test_call_empty_state(self):
        llm = _make_mock_llm()
        agent = DataFormatterAgent(llm=llm)

        parsed = DataFormatterOutput()

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, None)
            result = await agent({})

        assert result["formatted_jobs"] == []
        assert result["formatted_certifications"] == []


# ------------------------------------------------------------------
# ceo_agent.py
# ------------------------------------------------------------------


class TestCEOAgent:
    """Tests for CEOAgent.__call__."""

    async def test_call_returns_recommendations_and_summary(self):
        llm = _make_mock_llm()
        agent = CEOAgent(llm=llm)

        rec = StrategicRecommendation(
            area="career move", recommendation="Apply to ML roles", priority="high",
        )
        parsed = CEOOutput(
            strategic_recommendations=[rec],
            ceo_summary="Focus on ML transitions",
        )
        usage = {"input_tokens": 120, "output_tokens": 90}

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, usage)
            state = {
                "profile_targets": ["ML engineer"],
                "formatted_jobs": [{"title": "ML Eng"}],
                "formatted_certifications": [],
                "formatted_courses": [],
                "formatted_events": [],
                "formatted_groups": [],
                "formatted_trends": [],
            }
            result = await agent(state)

        assert len(result["strategic_recommendations"]) == 1
        assert result["strategic_recommendations"][0]["area"] == "career move"
        assert result["ceo_summary"] == "Focus on ML transitions"
        assert result["_token_usage"] == [usage]

    async def test_call_no_usage(self):
        llm = _make_mock_llm()
        agent = CEOAgent(llm=llm)

        parsed = CEOOutput(strategic_recommendations=[], ceo_summary="None")

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, None)
            result = await agent({})

        assert result["_token_usage"] == []


# ------------------------------------------------------------------
# cfo_agent.py
# ------------------------------------------------------------------


class TestCFOAgent:
    """Tests for CFOAgent.__call__."""

    async def test_call_returns_risk_assessments_and_summary(self):
        llm = _make_mock_llm()
        agent = CFOAgent(llm=llm)

        ra = RiskAssessment(
            area="certifications", risk_level="low",
            time_investment="2 months", roi_estimate="high",
        )
        parsed = CFOOutput(
            risk_assessments=[ra],
            cfo_summary="Low risk, high ROI",
        )
        usage = {"input_tokens": 100, "output_tokens": 70}

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, usage)
            state = {
                "profile_targets": ["Get AWS cert"],
                "formatted_jobs": [],
                "formatted_certifications": [{"title": "AWS SAA"}],
                "formatted_courses": [],
                "formatted_events": [],
                "formatted_groups": [],
                "formatted_trends": [],
            }
            result = await agent(state)

        assert len(result["risk_assessments"]) == 1
        assert result["risk_assessments"][0]["risk_level"] == "low"
        assert result["cfo_summary"] == "Low risk, high ROI"
        assert result["_token_usage"] == [usage]

    async def test_call_no_usage(self):
        llm = _make_mock_llm()
        agent = CFOAgent(llm=llm)

        parsed = CFOOutput(risk_assessments=[], cfo_summary="Nothing")

        with patch.object(agent, "_invoke_structured", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = (parsed, None)
            result = await agent({})

        assert result["_token_usage"] == []


# ------------------------------------------------------------------
# factory.py
# ------------------------------------------------------------------


@dataclass
class _FakeBudget:
    """Lightweight stand-in for app.engine.policy_engine.Budget."""

    max_steps: int = 5
    max_input_tokens: int | None = 4000
    max_output_tokens: int | None = 2000
    min_searches: int = 2
    min_results: int = 3
    agent_type: str = "llm"


class TestAgentFactory:
    """Tests for AgentFactory."""

    def _make_factory(
        self,
        llm: Any = None,
        policy_engine: Any = None,
        agent_models: AgentModelConfig | None = None,
    ) -> AgentFactory:
        if llm is None:
            llm = _make_mock_llm()
        return AgentFactory(
            llm=llm,
            prompt_loader=MagicMock(),
            search_tool=MagicMock(),
            policy_engine=policy_engine,
            agent_models=agent_models,
        )

    def test_init_defaults(self):
        factory = self._make_factory()
        assert factory._goal_extractor is None
        assert factory._web_scraper is None
        assert factory._data_formatter is None
        assert factory._ceo is None
        assert factory._cfo is None
        assert factory._cover_letter is None

    def test_get_llm_no_override_returns_default(self):
        factory = self._make_factory()
        result = factory._get_llm("")
        assert result is factory._llm

    def test_get_llm_same_model_returns_default(self):
        llm = _make_mock_llm("gpt-4o-mini")
        factory = self._make_factory(llm=llm)
        result = factory._get_llm("gpt-4o-mini")
        assert result is llm

    def test_get_llm_with_override_creates_new(self):
        mock_new_llm = MagicMock()
        factory = self._make_factory()

        with patch("langchain_openai.ChatOpenAI", return_value=mock_new_llm) as mock_chat_cls:
            result = factory._get_llm("gpt-4o")

        assert result is mock_new_llm
        mock_chat_cls.assert_called_once()
        call_kwargs = mock_chat_cls.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_get_llm_with_max_tokens(self):
        mock_new_llm = MagicMock()
        factory = self._make_factory()

        with patch("langchain_openai.ChatOpenAI", return_value=mock_new_llm) as mock_chat_cls:
            factory._get_llm("", max_tokens=1024)

        call_kwargs = mock_chat_cls.call_args[1]
        assert call_kwargs["max_tokens"] == 1024

    def test_get_llm_caches_instances(self):
        factory = self._make_factory()

        with patch("langchain_openai.ChatOpenAI", return_value=MagicMock()) as mock_chat_cls:
            first = factory._get_llm("gpt-4o")
            second = factory._get_llm("gpt-4o")

        assert first is second
        assert mock_chat_cls.call_count == 1

    def test_get_budget_output_tokens_with_policy(self):
        pe = MagicMock()
        pe.get_budget.return_value = _FakeBudget(max_output_tokens=4096)
        factory = self._make_factory(policy_engine=pe)

        tokens = factory._get_budget_output_tokens("goal_extractor")
        assert tokens == 4096
        pe.get_budget.assert_called_with("goal_extractor")

    def test_get_budget_output_tokens_no_policy(self):
        factory = self._make_factory(policy_engine=None)
        assert factory._get_budget_output_tokens("goal_extractor") is None

    def test_get_budget_output_tokens_key_error(self):
        pe = MagicMock()
        pe.get_budget.side_effect = KeyError("no such budget")
        factory = self._make_factory(policy_engine=pe)

        assert factory._get_budget_output_tokens("nonexistent") is None

    def test_create_goal_extractor(self):
        factory = self._make_factory()
        agent = factory.create_goal_extractor()
        assert isinstance(agent, GoalExtractorAgent)
        assert agent is factory.create_goal_extractor()  # singleton

    def test_create_data_formatter(self):
        factory = self._make_factory()
        agent = factory.create_data_formatter()
        assert isinstance(agent, DataFormatterAgent)
        assert agent is factory.create_data_formatter()  # singleton

    def test_create_ceo(self):
        factory = self._make_factory()
        agent = factory.create_ceo()
        assert isinstance(agent, CEOAgent)
        assert agent is factory.create_ceo()  # singleton

    def test_create_cfo(self):
        factory = self._make_factory()
        agent = factory.create_cfo()
        assert isinstance(agent, CFOAgent)
        assert agent is factory.create_cfo()  # singleton

    def test_create_cover_letter_agent(self):
        factory = self._make_factory()
        agent = factory.create_cover_letter_agent()
        assert isinstance(agent, CoverLetterAgent)
        assert agent is factory.create_cover_letter_agent()  # singleton

    @patch("app.agents.factory.URLFetchTool", create=True)
    def test_create_web_scraper_without_policy(self, mock_fetch_cls):
        mock_fetch_cls.return_value = MagicMock()
        factory = self._make_factory(policy_engine=None)

        with patch("app.agents.factory.URLFetchTool", mock_fetch_cls):
            agent = factory.create_web_scraper()

        from app.agents.web_scraper import WebScraperAgent

        assert isinstance(agent, WebScraperAgent)
        assert agent is factory.create_web_scraper()  # singleton

    @patch("app.agents.factory.URLFetchTool", create=True)
    def test_create_web_scraper_with_policy(self, mock_fetch_cls):
        mock_fetch_cls.return_value = MagicMock()
        pe = MagicMock()
        pe.get_budget.return_value = _FakeBudget(max_steps=10, max_output_tokens=8000)
        factory = self._make_factory(policy_engine=pe)

        with patch("app.agents.factory.URLFetchTool", mock_fetch_cls):
            agent = factory.create_web_scraper()

        from app.agents.web_scraper import WebScraperAgent

        assert isinstance(agent, WebScraperAgent)

    @patch("app.agents.factory.URLFetchTool", create=True)
    def test_create_web_scraper_budget_key_error(self, mock_fetch_cls):
        mock_fetch_cls.return_value = MagicMock()
        pe = MagicMock()
        pe.get_budget.side_effect = KeyError("no budget")
        factory = self._make_factory(policy_engine=pe)

        with patch("app.agents.factory.URLFetchTool", mock_fetch_cls):
            agent = factory.create_web_scraper()

        from app.agents.web_scraper import WebScraperAgent

        assert isinstance(agent, WebScraperAgent)

    def test_create_goal_extractor_with_model_override(self):
        models = AgentModelConfig(goal_extractor="gpt-4o")
        factory = self._make_factory(agent_models=models)

        with patch.object(factory, "_get_llm", return_value=_make_mock_llm("gpt-4o")) as mock_get:
            agent = factory.create_goal_extractor()

        assert isinstance(agent, GoalExtractorAgent)
        mock_get.assert_called_once()

    # -- _resolve_single_budget --

    def test_resolve_single_budget_mode_specific(self):
        pe = MagicMock()
        pe.get_budget.return_value = _FakeBudget(max_steps=8, min_searches=3, min_results=5)
        factory = self._make_factory(policy_engine=pe)

        result = factory._resolve_single_budget("daily", "job")
        assert result is not None
        assert result["max_steps"] == 8
        assert result["min_searches"] == 3
        assert result["min_results"] == 5
        pe.get_budget.assert_called_once_with("web_scraper_job_daily")

    def test_resolve_single_budget_fallback_to_category(self):
        pe = MagicMock()

        def side_effect(name):
            if name == "web_scraper_job_daily":
                raise KeyError("not found")
            return _FakeBudget(max_steps=4, min_searches=1, min_results=2)

        pe.get_budget.side_effect = side_effect
        factory = self._make_factory(policy_engine=pe)

        result = factory._resolve_single_budget("daily", "job")
        assert result is not None
        assert result["max_steps"] == 4

    def test_resolve_single_budget_neither_exists(self):
        pe = MagicMock()
        pe.get_budget.side_effect = KeyError("not found")
        factory = self._make_factory(policy_engine=pe)

        result = factory._resolve_single_budget("daily", "job")
        assert result is None

    # -- _resolve_mode_category_budgets --

    def test_resolve_mode_category_budgets_no_policy(self):
        factory = self._make_factory(policy_engine=None)
        assert factory._resolve_mode_category_budgets() == {}

    def test_resolve_mode_category_budgets_with_policy(self):
        pe = MagicMock()
        pe.get_budget.return_value = _FakeBudget(max_steps=6, min_searches=2, min_results=4)
        factory = self._make_factory(policy_engine=pe)

        result = factory._resolve_mode_category_budgets()
        # 2 modes x 6 categories = 12 entries
        assert len(result) == 12
        assert "daily:job" in result
        assert "weekly:trend" in result
        assert result["daily:job"]["max_steps"] == 6

    def test_resolve_mode_category_budgets_some_missing(self):
        pe = MagicMock()
        call_count = 0

        def side_effect(name):
            nonlocal call_count
            call_count += 1
            # Only return budgets for job categories
            if "job" in name:
                return _FakeBudget(max_steps=3, min_searches=1, min_results=1)
            raise KeyError("not found")

        pe.get_budget.side_effect = side_effect
        factory = self._make_factory(policy_engine=pe)

        result = factory._resolve_mode_category_budgets()
        # Only job budgets should exist (daily:job and weekly:job)
        assert "daily:job" in result
        assert "weekly:job" in result
        assert "daily:cert" not in result

    def test_agent_model_config_defaults(self):
        config = AgentModelConfig()
        assert config.goal_extractor == ""
        assert config.web_scraper == ""
        assert config.data_formatter == ""
        assert config.ceo == ""
        assert config.cfo == ""
        assert config.cover_letter == ""
