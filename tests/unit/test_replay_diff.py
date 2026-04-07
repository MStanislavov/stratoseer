"""Tests for ReplayEngine and DiffEngine."""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.audit_writer import AuditWriter
from app.engine.diff import DiffEngine
from app.engine.replay import ReplayEngine

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def writer(test_session_factory) -> AuditWriter:
    """Create an AuditWriter backed by the test database.

    Args:
        test_session_factory: Session factory fixture providing the test DB.

    Returns:
        AuditWriter: A writer ready for testing.
    """
    return AuditWriter()


@pytest.fixture()
def replay_engine(writer: AuditWriter) -> ReplayEngine:
    """Create a ReplayEngine wired to the test AuditWriter.

    Args:
        writer: The AuditWriter fixture.

    Returns:
        ReplayEngine: A replay engine for testing strict and refresh replays.
    """
    return ReplayEngine(audit_writer=writer)


@pytest.fixture()
def diff_engine(writer: AuditWriter) -> DiffEngine:
    """Create a DiffEngine wired to the test AuditWriter.

    Args:
        writer: The AuditWriter fixture.

    Returns:
        DiffEngine: A diff engine for comparing run bundles.
    """
    return DiffEngine(audit_writer=writer)


async def _make_bundle(
    writer: AuditWriter,
    run_id: str,
    jobs: list[dict[str, Any]] | None = None,
    certifications: list[dict[str, Any]] | None = None,
    courses: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
) -> None:
    """Helper to create a bundle with given entity lists."""
    if jobs is None:
        jobs = [
            {
                "title": "Software Engineer at Acme",
                "company": "Acme",
                "url": "https://example.com/job/1",
            },
            {
                "title": "Backend Developer at Globex",
                "company": "Globex",
                "url": "https://example.com/job/2",
            },
        ]
    await writer.create_run_bundle(
        run_id=run_id,
        profile_hash="profile-hash-abc",
        policy_version_hash="policy-hash-xyz",
        verifier_report={},
        final_artifacts={
            "jobs": jobs,
            "certifications": certifications or [],
            "courses": courses or [],
            "events": events or [],
            "groups": groups or [],
        },
    )


# ------------------------------------------------------------------
# ReplayEngine, strict
# ------------------------------------------------------------------


class TestReplayStrict:
    """Tests for strict replay mode which uses stored tool responses."""

    @pytest.mark.asyncio
    async def test_returns_same_artifacts_as_original(
        self, writer: AuditWriter, replay_engine: ReplayEngine
    ) -> None:
        await _make_bundle(writer, "orig-run-1")
        result = await replay_engine.replay_strict("orig-run-1", "replay-run-1")

        assert result["run_id"] == "replay-run-1"
        assert result["replay_mode"] == "strict"
        assert result["original_run_id"] == "orig-run-1"
        assert result["drift"] == []

        jobs = result["result"]["jobs"]
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Software Engineer at Acme"

    @pytest.mark.asyncio
    async def test_nonexistent_run_raises(self, replay_engine: ReplayEngine) -> None:
        with pytest.raises(ValueError, match="No bundle found"):
            await replay_engine.replay_strict("nonexistent", "new-run")


# ------------------------------------------------------------------
# ReplayEngine, refresh
# ------------------------------------------------------------------


class TestReplayRefresh:
    """Tests for refresh replay mode which re-fetches and detects drift."""

    @pytest.mark.asyncio
    async def test_no_drift_when_identical(
        self, writer: AuditWriter, replay_engine: ReplayEngine
    ) -> None:
        await _make_bundle(writer, "orig-run-3")
        original_bundle = await writer.read_bundle("orig-run-3")
        assert original_bundle is not None

        new_result = original_bundle["final_artifacts"]
        result = await replay_engine.replay_refresh("orig-run-3", "refresh-run-1", new_result)

        assert result["replay_mode"] == "refresh"
        assert result["drift"] == []

    @pytest.mark.asyncio
    async def test_detects_addition_drift(
        self, writer: AuditWriter, replay_engine: ReplayEngine
    ) -> None:
        await _make_bundle(writer, "orig-run-4")

        new_result = {
            "jobs": [
                {"title": "Software Engineer at Acme", "company": "Acme"},
                {"title": "Backend Developer at Globex", "company": "Globex"},
                {"title": "New Role at Initech", "company": "Initech"},
            ],
            "certifications": [],
            "courses": [],
            "events": [],
            "groups": [],
        }
        result = await replay_engine.replay_refresh("orig-run-4", "refresh-run-2", new_result)

        additions = [d for d in result["drift"] if d["type"] == "addition"]
        assert len(additions) == 1
        assert additions[0]["title"] == "New Role at Initech"

    @pytest.mark.asyncio
    async def test_detects_removal_drift(
        self, writer: AuditWriter, replay_engine: ReplayEngine
    ) -> None:
        await _make_bundle(writer, "orig-run-5")

        new_result = {
            "jobs": [
                {"title": "Software Engineer at Acme", "company": "Acme"},
            ],
            "certifications": [],
            "courses": [],
            "events": [],
            "groups": [],
        }
        result = await replay_engine.replay_refresh("orig-run-5", "refresh-run-3", new_result)

        removals = [d for d in result["drift"] if d["type"] == "removal"]
        assert len(removals) == 1
        assert removals[0]["title"] == "Backend Developer at Globex"

    @pytest.mark.asyncio
    async def test_nonexistent_run_raises(self, replay_engine: ReplayEngine) -> None:
        with pytest.raises(ValueError, match="No bundle found"):
            await replay_engine.replay_refresh("nonexistent", "new-run", {})


# ------------------------------------------------------------------
# DiffEngine
# ------------------------------------------------------------------


class TestDiffIdentical:
    """Tests for diff output when both runs have identical artifacts."""

    @pytest.mark.asyncio
    async def test_no_changes_for_identical_runs(
        self, writer: AuditWriter, diff_engine: DiffEngine
    ) -> None:
        jobs = [{"title": "SWE", "company": "Acme", "description": "code"}]
        await _make_bundle(writer, "run-a", jobs=jobs)
        await _make_bundle(writer, "run-b", jobs=jobs)

        result = await diff_engine.diff_runs("run-a", "run-b")

        assert result["additions"] == []
        assert result["removals"] == []
        assert result["changes"] == []
        assert result["summary"]["added"] == 0
        assert result["summary"]["removed"] == 0
        assert result["summary"]["changed"] == 0


class TestDiffAdditionsRemovals:
    """Tests for detecting additions, removals, and changes between two runs."""

    @pytest.mark.asyncio
    async def test_detects_additions(self, writer: AuditWriter, diff_engine: DiffEngine) -> None:
        jobs_a = [{"title": "SWE", "company": "Acme"}]
        jobs_b = [
            {"title": "SWE", "company": "Acme"},
            {"title": "DevOps", "company": "Globex"},
        ]
        await _make_bundle(writer, "diff-a-1", jobs=jobs_a)
        await _make_bundle(writer, "diff-b-1", jobs=jobs_b)

        result = await diff_engine.diff_runs("diff-a-1", "diff-b-1")

        assert result["summary"]["added"] == 1
        assert result["additions"][0]["title"] == "DevOps"
        assert result["summary"]["removed"] == 0

    @pytest.mark.asyncio
    async def test_detects_removals(self, writer: AuditWriter, diff_engine: DiffEngine) -> None:
        jobs_a = [
            {"title": "SWE", "company": "Acme"},
            {"title": "DevOps", "company": "Globex"},
        ]
        jobs_b = [{"title": "SWE", "company": "Acme"}]
        await _make_bundle(writer, "diff-a-2", jobs=jobs_a)
        await _make_bundle(writer, "diff-b-2", jobs=jobs_b)

        result = await diff_engine.diff_runs("diff-a-2", "diff-b-2")

        assert result["summary"]["removed"] == 1
        assert result["removals"][0]["title"] == "DevOps"
        assert result["summary"]["added"] == 0

    @pytest.mark.asyncio
    async def test_detects_changes(self, writer: AuditWriter, diff_engine: DiffEngine) -> None:
        jobs_a = [
            {
                "title": "SWE",
                "company": "Acme",
                "description": "Build things",
                "url": "https://example.com/1",
            }
        ]
        jobs_b = [
            {
                "title": "SWE",
                "company": "Acme",
                "description": "Build awesome things",
                "url": "https://example.com/1-updated",
            }
        ]
        await _make_bundle(writer, "diff-a-3", jobs=jobs_a)
        await _make_bundle(writer, "diff-b-3", jobs=jobs_b)

        result = await diff_engine.diff_runs("diff-a-3", "diff-b-3")

        assert result["summary"]["changed"] == 1
        assert result["summary"]["added"] == 0
        assert result["summary"]["removed"] == 0

        change = result["changes"][0]
        assert change["title"] == "SWE"
        assert change["changes"]["description"]["old"] == "Build things"
        assert change["changes"]["description"]["new"] == "Build awesome things"


class TestDiffErrors:
    """Tests for diff error handling when runs do not exist."""

    @pytest.mark.asyncio
    async def test_nonexistent_run_a_raises(
        self, writer: AuditWriter, diff_engine: DiffEngine
    ) -> None:
        await _make_bundle(writer, "exists-run")
        with pytest.raises(ValueError, match="No bundle found for run nonexistent"):
            await diff_engine.diff_runs("nonexistent", "exists-run")

    @pytest.mark.asyncio
    async def test_nonexistent_run_b_raises(
        self, writer: AuditWriter, diff_engine: DiffEngine
    ) -> None:
        await _make_bundle(writer, "exists-run-2")
        with pytest.raises(ValueError, match="No bundle found for run nonexistent"):
            await diff_engine.diff_runs("exists-run-2", "nonexistent")


class TestDiffSummary:
    """Tests for the diff summary item counts."""

    @pytest.mark.asyncio
    async def test_item_counts(self, writer: AuditWriter, diff_engine: DiffEngine) -> None:
        jobs_a = [{"title": "A", "company": "X"}]
        jobs_b = [{"title": "B", "company": "Y"}, {"title": "C", "company": "Z"}]
        await _make_bundle(writer, "count-a", jobs=jobs_a)
        await _make_bundle(writer, "count-b", jobs=jobs_b)

        result = await diff_engine.diff_runs("count-a", "count-b")

        assert result["summary"]["items_a"] == 1
        assert result["summary"]["items_b"] == 2
