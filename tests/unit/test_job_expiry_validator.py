"""Tests for the job expiry re-validation node."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.engine.audit_writer import AuditWriter
from app.graphs.log import make_job_expiry_validator_node


def _job(title: str, url: str = "") -> dict:
    return {"title": title, "url": url, "snippet": "", "source": "test"}


@pytest.fixture()
def node():
    return make_job_expiry_validator_node("daily")


@pytest.fixture()
def node_with_audit(test_session_factory):
    writer = AuditWriter()
    return make_job_expiry_validator_node("daily", audit_writer=writer), writer


class TestJobExpiryValidator:
    @pytest.mark.asyncio
    async def test_valid_job_passes_through(self, node):
        with patch(
            "app.graphs.log._fetch_and_check_expiry", return_value=""
        ):
            state = {"run_id": "r1", "raw_job_results": [_job("SWE", "https://example.com/job/1")]}
            result = await node(state)

        assert len(result["raw_job_results"]) == 1
        assert result["raw_job_results"][0]["title"] == "SWE"

    @pytest.mark.asyncio
    async def test_expired_job_filtered_out(self, node):
        with patch(
            "app.graphs.log._fetch_and_check_expiry",
            return_value="no longer accepting applications",
        ):
            state = {
                "run_id": "r1",
                "raw_job_results": [_job("Old Job", "https://example.com/job/2")],
            }
            result = await node(state)

        assert result["raw_job_results"] == []
        assert len(result["filtered_job_urls"]) == 1
        assert "expiry recheck" in result["filtered_job_urls"][0]["reason"]

    @pytest.mark.asyncio
    async def test_empty_url_passes_through(self, node):
        with patch("app.graphs.log._fetch_and_check_expiry") as mock_fetch:
            state = {"run_id": "r1", "raw_job_results": [_job("No URL Job", "")]}
            result = await node(state)

        assert len(result["raw_job_results"]) == 1
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_error_fails_open(self, node):
        """Jobs whose URL cannot be fetched should pass through (fail-open)."""
        with patch(
            "app.graphs.log._fetch_and_check_expiry", return_value=""
        ):
            state = {"run_id": "r1", "raw_job_results": [_job("Flaky", "https://down.example.com")]}
            result = await node(state)

        assert len(result["raw_job_results"]) == 1

    @pytest.mark.asyncio
    async def test_mixed_jobs(self, node):
        def side_effect(url, phrases):
            if "expired" in url:
                return "this job has expired"
            return ""

        with patch("app.graphs.log._fetch_and_check_expiry", side_effect=side_effect):
            state = {
                "run_id": "r1",
                "raw_job_results": [
                    _job("Good Job", "https://example.com/good"),
                    _job("Expired Job", "https://example.com/expired"),
                    _job("No URL"),
                ],
            }
            result = await node(state)

        assert len(result["raw_job_results"]) == 2
        titles = [j["title"] for j in result["raw_job_results"]]
        assert "Good Job" in titles
        assert "No URL" in titles
        assert len(result["filtered_job_urls"]) == 1

    @pytest.mark.asyncio
    async def test_preserves_existing_filtered_urls(self, node):
        existing = [{"url": "https://old.com", "reason": "HTTP 404"}]
        with patch(
            "app.graphs.log._fetch_and_check_expiry",
            return_value="job expired",
        ):
            state = {
                "run_id": "r1",
                "raw_job_results": [_job("Dead", "https://example.com/dead")],
                "filtered_job_urls": existing,
            }
            result = await node(state)

        assert len(result["filtered_job_urls"]) == 2
        assert result["filtered_job_urls"][0] == existing[0]

    @pytest.mark.asyncio
    async def test_empty_raw_results(self, node):
        with patch("app.graphs.log._fetch_and_check_expiry") as mock_fetch:
            state = {"run_id": "r1", "raw_job_results": []}
            result = await node(state)

        assert result["raw_job_results"] == []
        assert result["filtered_job_urls"] == []
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_events_written(self, node_with_audit):
        node, writer = node_with_audit
        with patch("app.graphs.log._fetch_and_check_expiry", return_value=""):
            state = {"run_id": "r-audit", "raw_job_results": [_job("J", "https://x.com")]}
            await node(state)

        events = await writer.read_log("r-audit")
        types = [e["event_type"] for e in events]
        assert "static_validator_start" in types
        assert "static_validator_end" in types
