"""Replay engine: strict and refresh replay of previous runs."""

from __future__ import annotations

from typing import Any, Literal

from app.engine.audit_writer import AuditWriter


class ReplayEngine:
    """Re-execute or compare runs against stored audit bundles."""

    def __init__(self, audit_writer: AuditWriter) -> None:
        self._audit_writer = audit_writer

    def replay_strict(self, original_run_id: str, new_run_id: str) -> dict[str, Any]:
        """Replay using stored tool responses (no network calls).

        In strict mode the stored artifacts are returned verbatim as the
        result of the replay run.  No drift is possible by definition.
        """
        bundle = self._audit_writer.read_bundle(original_run_id)
        if bundle is None:
            raise ValueError(f"No bundle found for run {original_run_id}")

        return {
            "run_id": new_run_id,
            "replay_mode": "strict",
            "original_run_id": original_run_id,
            "result": bundle.get("final_artifacts", {}),
            "verifier_report": bundle.get("verifier_report", {}),
            "drift": [],  # No drift in strict mode (by definition)
        }

    def replay_refresh(
        self,
        original_run_id: str,
        new_run_id: str,
        new_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare a fresh execution against stored data and flag drift.

        The caller is responsible for executing the graph and passing the
        fresh ``new_result`` dictionary.  This method loads the original
        bundle and compares the two.
        """
        bundle = self._audit_writer.read_bundle(original_run_id)
        if bundle is None:
            raise ValueError(f"No bundle found for run {original_run_id}")

        original_artifacts = bundle.get("final_artifacts", {})
        drift = self._detect_drift(original_artifacts, new_result)

        return {
            "run_id": new_run_id,
            "replay_mode": "refresh",
            "original_run_id": original_run_id,
            "result": new_result,
            "verifier_report": new_result.get("verifier_report", {}),
            "drift": drift,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_drift(
        original: dict[str, Any],
        refreshed: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Compare original and refreshed results for content drift."""
        drift_items: list[dict[str, Any]] = []

        orig_opps = original.get("opportunities", [])
        new_opps = refreshed.get(
            "opportunities", refreshed.get("ranked_opportunities", [])
        )

        orig_titles = {o.get("title", "") for o in orig_opps}
        new_titles = {o.get("title", "") for o in new_opps}

        for title in sorted(new_titles - orig_titles):
            drift_items.append(
                {"type": "addition", "entity": "opportunity", "title": title}
            )
        for title in sorted(orig_titles - new_titles):
            drift_items.append(
                {"type": "removal", "entity": "opportunity", "title": title}
            )

        # Evidence hash drift (compare by evidence id)
        orig_evidence = {
            e.get("id", ""): e.get("content_hash", "")
            for e in original.get("evidence_items", [])
        }
        new_evidence = {
            e.get("id", ""): e.get("content_hash", "")
            for e in refreshed.get("evidence_items", [])
        }
        for eid in sorted(set(orig_evidence) & set(new_evidence)):
            if orig_evidence[eid] != new_evidence[eid]:
                drift_items.append(
                    {
                        "type": "hash_changed",
                        "entity": "evidence",
                        "evidence_id": eid,
                        "old_hash": orig_evidence[eid],
                        "new_hash": new_evidence[eid],
                    }
                )

        return drift_items
