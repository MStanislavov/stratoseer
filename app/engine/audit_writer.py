"""Audit writer: append-only JSONL log and run-bundle creation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.engine.policy_engine import PolicyEngine


@dataclass
class AuditEvent:
    """A single event in the audit trail."""

    timestamp: str
    event_type: str  # agent_start, agent_end, tool_call, tool_response, output, verifier_result, error
    agent: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


class AuditWriter:
    """Manages append-only JSONL audit logs and run bundles under ``artifacts/runs/<run_id>/``."""

    def __init__(
        self,
        artifacts_dir: Path | str = "artifacts",
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self._artifacts_dir = Path(artifacts_dir)
        self._policy_engine = policy_engine

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _run_dir(self, run_id: str) -> Path:
        return self._artifacts_dir / "runs" / run_id

    def _log_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "audit.jsonl"

    # ------------------------------------------------------------------
    # Redaction
    # ------------------------------------------------------------------

    def _redact(self, text: str, context: str = "audit_log") -> str:
        if self._policy_engine is not None:
            return self._policy_engine.apply_redaction(text, context)
        return text

    # ------------------------------------------------------------------
    # JSONL append
    # ------------------------------------------------------------------

    def append(self, run_id: str, event: AuditEvent) -> None:
        """Append a single event (with PII redaction) to the run's JSONL log."""
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_path(run_id)
        raw_line = json.dumps(event.to_dict())
        redacted_line = self._redact(raw_line, "audit_log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(redacted_line + "\n")

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def read_log(self, run_id: str) -> list[dict[str, Any]]:
        """Return all events from the run's JSONL log, in order."""
        log_path = self._log_path(run_id)
        if not log_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    # ------------------------------------------------------------------
    # Bundle creation
    # ------------------------------------------------------------------

    def create_run_bundle(
        self,
        run_id: str,
        profile_hash: str,
        policy_version_hash: str,
        verifier_report: dict[str, Any],
        final_artifacts: dict[str, Any],
        intermediate_outputs: list[dict[str, Any]] | None = None,
    ) -> Path:
        """Write the full run bundle to ``bundle.json`` with PII redaction."""
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        bundle = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profile_hash": profile_hash,
            "policy_version_hash": policy_version_hash,
            "verifier_report": verifier_report,
            "final_artifacts": final_artifacts,
            "intermediate_outputs": intermediate_outputs or [],
        }

        raw_json = json.dumps(bundle, indent=2)
        redacted_json = self._redact(raw_json, "run_bundle")

        bundle_path = run_dir / "bundle.json"
        with open(bundle_path, "w", encoding="utf-8") as f:
            f.write(redacted_json)

        return bundle_path

    def read_bundle(self, run_id: str) -> dict[str, Any] | None:
        """Read and return the bundle, or *None* if it does not exist."""
        bundle_path = self._run_dir(run_id) / "bundle.json"
        if not bundle_path.exists():
            return None
        with open(bundle_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def hash_content(content: str) -> str:
        """SHA-256 hex-digest of *content*."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
