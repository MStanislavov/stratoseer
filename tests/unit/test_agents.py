"""Unit tests for each agent in mock mode (no LLM)."""

import pytest

from app.agents.ceo_agent import CEOAgent
from app.agents.cfo_agent import CFOAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.data_formatter import DataFormatterAgent
from app.agents.goal_extractor import GoalExtractorAgent
from app.agents.web_scraper import WebScraperAgent


class TestGoalExtractor:
    @pytest.mark.asyncio
    async def test_mock_returns_search_prompts(self):
        agent = GoalExtractorAgent()
        result = await agent({"profile_targets": ["cloud", "devops"], "profile_skills": ["python"]})
        assert "search_prompts" in result
        prompts = result["search_prompts"]
        assert "cert_prompt" in prompts
        assert "event_prompt" in prompts
        assert "job_prompt" in prompts
        assert "trend_prompt" in prompts

    @pytest.mark.asyncio
    async def test_mock_with_empty_targets(self):
        agent = GoalExtractorAgent()
        result = await agent({"profile_targets": [], "profile_skills": []})
        assert "search_prompts" in result


class TestWebScraper:
    @pytest.mark.asyncio
    async def test_mock_returns_job_results(self):
        agent = WebScraperAgent()
        result = await agent({"search_prompt": "python jobs", "search_category": "job"})
        assert "raw_job_results" in result
        assert len(result["raw_job_results"]) > 0

    @pytest.mark.asyncio
    async def test_mock_returns_cert_results(self):
        agent = WebScraperAgent()
        result = await agent({"search_prompt": "aws certs", "search_category": "cert"})
        assert "raw_cert_results" in result
        assert len(result["raw_cert_results"]) > 0

    @pytest.mark.asyncio
    async def test_mock_returns_event_results(self):
        agent = WebScraperAgent()
        result = await agent({"search_prompt": "python conferences", "search_category": "event"})
        assert "raw_event_results" in result
        assert len(result["raw_event_results"]) > 0

    @pytest.mark.asyncio
    async def test_mock_returns_trend_results(self):
        agent = WebScraperAgent()
        result = await agent({"search_prompt": "AI trends", "search_category": "trend"})
        assert "raw_trend_results" in result
        assert len(result["raw_trend_results"]) > 0

    @pytest.mark.asyncio
    async def test_mock_unknown_category_returns_empty(self):
        agent = WebScraperAgent()
        result = await agent({"search_prompt": "test", "search_category": "unknown"})
        assert result["raw_unknown_results"] == []


class TestDataFormatter:
    @pytest.mark.asyncio
    async def test_mock_formats_raw_results(self):
        agent = DataFormatterAgent()
        state = {
            "raw_job_results": [
                {"title": "SWE at Acme", "url": "https://example.com/1", "snippet": "Python"},
            ],
            "raw_cert_results": [
                {"title": "AWS SA", "url": "https://example.com/2", "snippet": "Cloud"},
            ],
            "raw_event_results": [
                {"title": "PyCon", "url": "https://example.com/3", "snippet": "Conference"},
            ],
            "raw_trend_results": [
                {"title": "AI Boom", "url": "https://example.com/4", "snippet": "AI is trending"},
            ],
        }
        result = await agent(state)
        assert len(result["formatted_jobs"]) == 1
        assert result["formatted_jobs"][0]["title"] == "SWE at Acme"
        assert len(result["formatted_certifications"]) == 1
        assert len(result["formatted_events"]) == 1
        assert result["formatted_courses"] == []
        assert result["formatted_groups"] == []
        assert len(result["formatted_trends"]) == 1
        assert result["formatted_trends"][0]["title"] == "AI Boom"

    @pytest.mark.asyncio
    async def test_mock_handles_empty_results(self):
        agent = DataFormatterAgent()
        result = await agent({"raw_job_results": [], "raw_cert_results": [], "raw_event_results": [], "raw_trend_results": []})
        assert result["formatted_jobs"] == []
        assert result["formatted_certifications"] == []
        assert result["formatted_events"] == []
        assert result["formatted_trends"] == []


class TestCEOAgent:
    @pytest.mark.asyncio
    async def test_mock_returns_recommendations(self):
        agent = CEOAgent()
        result = await agent({"profile_targets": ["cloud"], "formatted_jobs": []})
        assert "strategic_recommendations" in result
        assert "ceo_summary" in result
        assert len(result["strategic_recommendations"]) > 0


class TestCFOAgent:
    @pytest.mark.asyncio
    async def test_mock_returns_assessments(self):
        agent = CFOAgent()
        result = await agent({"profile_targets": ["cloud"], "formatted_jobs": []})
        assert "risk_assessments" in result
        assert "cfo_summary" in result
        assert len(result["risk_assessments"]) > 0


class TestCoverLetterAgent:
    @pytest.mark.asyncio
    async def test_mock_returns_content(self):
        agent = CoverLetterAgent()
        result = await agent({
            "cv_content": "Python developer with 5 years experience",
            "jd_text": "Looking for a senior Python developer",
            "job_opportunity": {"title": "Senior Python Dev"},
        })
        assert "cover_letter_content" in result
        assert "Senior Python Dev" in result["cover_letter_content"]
        assert len(result["cover_letter_content"]) > 50
