"""Audit writer: append-only audit log and run-bundle storage in PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.engine.policy_engine import PolicyEngine


@dataclass
class AuditEvent:
    """A single event in the audit trail."""

    timestamp: str
    event_type: (
        str  # agent_start, agent_end, tool_call, tool_response, output, verifier_result, error
    )
    agent: str | None = None
    node_type: str | None = None  # "agent" or "static_validator"
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict, omitting fields that are None."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class AuditWriter:
    """Manages append-only audit events and run bundles in PostgreSQL."""

    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        **_kwargs: Any,
    ) -> None:
        """Initialize the audit writer with an optional policy engine for PII redaction.

        Args:
            policy_engine: Policy engine used to apply redaction rules.
                If None, no redaction is applied.
        """
        self._policy_engine = policy_engine

    # ------------------------------------------------------------------
    # Redaction
    # ------------------------------------------------------------------

    def _redact(self, text: str, context: str = "audit_log") -> str:
        if self._policy_engine is not None:
            return self._policy_engine.apply_redaction(text, context)
        return text

    # ------------------------------------------------------------------
    # Audit event append
    # ------------------------------------------------------------------

    async def append(self, run_id: str, event: AuditEvent) -> None:
        """Append a single event (with PII redaction) to the run's audit log in Postgres."""
        from app.db import async_session_factory
        from app.models.audit_event import AuditEventRecord

        raw_line = json.dumps(event.to_dict())
        redacted_line = self._redact(raw_line, "audit_log")

        async with async_session_factory() as session:
            next_seq = await session.scalar(
                select(func.coalesce(func.max(AuditEventRecord.sequence), 0)).where(
                    AuditEventRecord.run_id == run_id
                )
            )
            record = AuditEventRecord(
                run_id=run_id,
                sequence=(next_seq or 0) + 1,
                data=redacted_line,
            )
            session.add(record)
            await session.commit()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def read_log(self, run_id: str) -> list[dict[str, Any]]:
        """Return all events from the run's audit log, in order."""
        from app.db import async_session_factory
        from app.models.audit_event import AuditEventRecord

        async with async_session_factory() as session:
            result = await session.execute(
                select(AuditEventRecord.data)
                .where(AuditEventRecord.run_id == run_id)
                .order_by(AuditEventRecord.sequence)
            )
            rows = result.scalars().all()
        return [json.loads(row) for row in rows]

    # ------------------------------------------------------------------
    # Bundle creation
    # ------------------------------------------------------------------

    async def create_run_bundle(
        self,
        run_id: str,
        profile_hash: str,
        policy_version_hash: str,
        verifier_report: dict[str, Any],
        final_artifacts: dict[str, Any],
        intermediate_outputs: list[dict[str, Any]] | None = None,
    ) -> None:
        """Write the full run bundle to the database with PII redaction."""
        from app.db import async_session_factory
        from app.models.run_bundle import RunBundle

        bundle = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profile_hash": profile_hash,
            "policy_version_hash": policy_version_hash,
            "verifier_report": verifier_report,
            "final_artifacts": final_artifacts,
            "intermediate_outputs": intermediate_outputs or [],
        }

        raw_json = json.dumps(bundle)
        redacted_json = self._redact(raw_json, "run_bundle")

        async with async_session_factory() as session:
            record = RunBundle(run_id=run_id, data=redacted_json)
            session.add(record)
            await session.commit()

    async def read_bundle(self, run_id: str) -> dict[str, Any] | None:
        """Read and return the bundle, or *None* if it does not exist."""
        from app.db import async_session_factory
        from app.models.run_bundle import RunBundle

        async with async_session_factory() as session:
            result = await session.execute(select(RunBundle.data).where(RunBundle.run_id == run_id))
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def hash_content(content: str) -> str:
        """SHA-256 hex-digest of *content*."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
