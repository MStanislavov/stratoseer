"""Tests for the AuditWriter (PostgreSQL-backed)."""

from __future__ import annotations

import json

import pytest
import yaml

from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def writer(test_session_factory) -> AuditWriter:
    """Create an AuditWriter instance backed by the test database.

    Args:
        test_session_factory: Session factory fixture providing the test DB.

    Returns:
        AuditWriter: A writer ready for testing.
    """
    return AuditWriter()


@pytest.fixture()
def policy_dir(tmp_path):
    """Create a temporary policy directory with a redaction.yaml file.

    Args:
        tmp_path: Pytest built-in temporary path fixture.

    Returns:
        Path: The path to the policy directory.
    """
    pd = tmp_path / "policy"
    pd.mkdir()
    redaction = {
        "rules": [
            {
                "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "replacement": "[REDACTED_EMAIL]",
                "applies_to": ["audit_log"],
            },
            {
                "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                "replacement": "[REDACTED_SSN]",
                "applies_to": ["audit_log", "run_bundle"],
            },
        ]
    }
    (pd / "redaction.yaml").write_text(yaml.dump(redaction), encoding="utf-8")
    return pd


@pytest.fixture()
def writer_with_redaction(test_session_factory, policy_dir) -> AuditWriter:
    """Create an AuditWriter with PII redaction rules loaded from the policy engine.

    Args:
        test_session_factory: Session factory fixture providing the test DB.
        policy_dir: Path to the temporary policy directory.

    Returns:
        AuditWriter: A writer with redaction enabled.
    """
    pe = PolicyEngine(policy_dir)
    return AuditWriter(policy_engine=pe)


# ------------------------------------------------------------------
# AuditEvent
# ------------------------------------------------------------------


class TestAuditEvent:
    """Tests for AuditEvent serialization via to_dict."""

    def test_to_dict_excludes_none(self) -> None:
        event = AuditEvent(timestamp="2025-01-01T00:00:00Z", event_type="agent_start")
        d = event.to_dict()
        assert "agent" not in d
        assert "data" not in d
        assert d["timestamp"] == "2025-01-01T00:00:00Z"
        assert d["event_type"] == "agent_start"

    def test_to_dict_includes_all_fields(self) -> None:
        event = AuditEvent(
            timestamp="2025-01-01T00:00:00Z",
            event_type="tool_call",
            agent="retriever",
            data={"tool": "web_search"},
        )
        d = event.to_dict()
        assert d["agent"] == "retriever"
        assert d["data"]["tool"] == "web_search"


# ------------------------------------------------------------------
# Append & read (DB-backed)
# ------------------------------------------------------------------


class TestAppendAndRead:
    """Tests for appending and reading audit events from the database."""

    @pytest.mark.asyncio
    async def test_append_and_read_single_event(self, writer: AuditWriter) -> None:
        event = AuditEvent(timestamp="t1", event_type="agent_start", agent="scout")
        await writer.append("run-001", event)
        events = await writer.read_log("run-001")
        assert len(events) == 1
        assert events[0]["event_type"] == "agent_start"

    @pytest.mark.asyncio
    async def test_multiple_appends_in_order(self, writer: AuditWriter) -> None:
        for i in range(5):
            event = AuditEvent(timestamp=f"t{i}", event_type="agent_start", agent=f"agent_{i}")
            await writer.append("run-002", event)
        events = await writer.read_log("run-002")
        assert len(events) == 5
        assert [e["agent"] for e in events] == [f"agent_{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_read_log_nonexistent_run_returns_empty(self, writer: AuditWriter) -> None:
        events = await writer.read_log("nonexistent-run")
        assert events == []

    @pytest.mark.asyncio
    async def test_each_event_is_valid_json(self, writer: AuditWriter) -> None:
        for i in range(3):
            event = AuditEvent(timestamp=f"t{i}", event_type="output", data={"value": i})
            await writer.append("run-003", event)
        events = await writer.read_log("run-003")
        assert len(events) == 3
        for ev in events:
            assert "timestamp" in ev


# ------------------------------------------------------------------
# Bundle creation & reading
# ------------------------------------------------------------------


class TestBundle:
    """Tests for creating and reading run bundles in the database."""

    @pytest.mark.asyncio
    async def test_create_bundle_stores_in_db(self, writer: AuditWriter) -> None:
        await writer.create_run_bundle(
            run_id="run-100",
            profile_hash="ph123",
            policy_version_hash="pv456",
            verifier_report={"overall_status": "pass"},
            final_artifacts={"opportunities": []},
        )
        bundle = await writer.read_bundle("run-100")
        assert bundle is not None
        assert bundle["run_id"] == "run-100"

    @pytest.mark.asyncio
    async def test_read_bundle_returns_contents(self, writer: AuditWriter) -> None:
        await writer.create_run_bundle(
            run_id="run-101",
            profile_hash="ph123",
            policy_version_hash="pv456",
            verifier_report={"overall_status": "pass"},
            final_artifacts={"opportunities": [{"title": "SWE"}]},
            intermediate_outputs=[{"step": 1}],
        )
        bundle = await writer.read_bundle("run-101")
        assert bundle is not None
        assert bundle["run_id"] == "run-101"
        assert bundle["profile_hash"] == "ph123"
        assert bundle["policy_version_hash"] == "pv456"
        assert bundle["verifier_report"]["overall_status"] == "pass"
        assert len(bundle["final_artifacts"]["opportunities"]) == 1
        assert len(bundle["intermediate_outputs"]) == 1
        assert "created_at" in bundle

    @pytest.mark.asyncio
    async def test_read_bundle_nonexistent_returns_none(self, writer: AuditWriter) -> None:
        result = await writer.read_bundle("nonexistent-run")
        assert result is None

    @pytest.mark.asyncio
    async def test_bundle_intermediate_defaults_empty(self, writer: AuditWriter) -> None:
        await writer.create_run_bundle(
            run_id="run-102",
            profile_hash="ph",
            policy_version_hash="pv",
            verifier_report={},
            final_artifacts={},
        )
        bundle = await writer.read_bundle("run-102")
        assert bundle["intermediate_outputs"] == []


# ------------------------------------------------------------------
# PII redaction in audit log
# ------------------------------------------------------------------


class TestRedaction:
    """Tests for PII redaction when writing audit events and bundles."""

    @pytest.mark.asyncio
    async def test_email_redacted_in_audit_log(self, writer_with_redaction: AuditWriter) -> None:
        event = AuditEvent(
            timestamp="t1",
            event_type="output",
            data={"contact": "user@example.com"},
        )
        await writer_with_redaction.append("run-redact-1", event)
        events = await writer_with_redaction.read_log("run-redact-1")
        raw = json.dumps(events[0])
        assert "user@example.com" not in raw
        assert "[REDACTED_EMAIL]" in raw

    @pytest.mark.asyncio
    async def test_ssn_redacted_in_audit_log(self, writer_with_redaction: AuditWriter) -> None:
        event = AuditEvent(
            timestamp="t1",
            event_type="output",
            data={"ssn": "123-45-6789"},
        )
        await writer_with_redaction.append("run-redact-2", event)
        events = await writer_with_redaction.read_log("run-redact-2")
        raw = json.dumps(events[0])
        assert "123-45-6789" not in raw
        assert "[REDACTED_SSN]" in raw

    @pytest.mark.asyncio
    async def test_ssn_redacted_in_bundle(self, writer_with_redaction: AuditWriter) -> None:
        await writer_with_redaction.create_run_bundle(
            run_id="run-redact-3",
            profile_hash="ph",
            policy_version_hash="pv",
            verifier_report={},
            final_artifacts={"note": "SSN is 123-45-6789"},
        )
        bundle = await writer_with_redaction.read_bundle("run-redact-3")
        raw = json.dumps(bundle)
        assert "123-45-6789" not in raw
        assert "[REDACTED_SSN]" in raw

    @pytest.mark.asyncio
    async def test_no_redaction_without_policy_engine(self, writer: AuditWriter) -> None:
        event = AuditEvent(
            timestamp="t1",
            event_type="output",
            data={"contact": "user@example.com"},
        )
        await writer.append("run-no-redact", event)
        events = await writer.read_log("run-no-redact")
        raw = json.dumps(events[0])
        assert "user@example.com" in raw


# ------------------------------------------------------------------
# hash_content
# ------------------------------------------------------------------


class TestHashContent:
    """Tests for the static hash_content SHA-256 helper."""

    def test_deterministic(self) -> None:
        h1 = AuditWriter.hash_content("hello world")
        h2 = AuditWriter.hash_content("hello world")
        assert h1 == h2

    def test_different_inputs_different_hashes(self) -> None:
        h1 = AuditWriter.hash_content("hello")
        h2 = AuditWriter.hash_content("world")
        assert h1 != h2

    def test_returns_hex_string(self) -> None:
        h = AuditWriter.hash_content("test")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest
        int(h, 16)  # should not raise
