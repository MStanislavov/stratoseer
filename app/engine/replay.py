"""Replay engine: strict and refresh replay of previous runs."""

from __future__ import annotations

from typing import Any

from app.engine.audit_writer import AuditWriter


class ReplayEngine:
    """Re-execute or compare runs against stored audit bundles."""

    def __init__(self, audit_writer: AuditWriter) -> None:
        """Initialize the replay engine with an audit writer for loading run bundles.

        Args:
            audit_writer: Audit writer instance used to read stored run bundles.
        """
        self._audit_writer = audit_writer

    async def replay_strict(self, original_run_id: str, new_run_id: str) -> dict[str, Any]:
        """Replay using stored tool responses (no network calls).

        In strict mode the stored artifacts are returned verbatim as the
        result of the replay run.  No drift is possible by definition.
        """
        bundle = await self._audit_writer.read_bundle(original_run_id)
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

    async def replay_refresh(
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
        bundle = await self._audit_writer.read_bundle(original_run_id)
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

        # Compare across all entity types
        for entity_type in ("jobs", "certifications", "courses", "events", "groups", "trends"):
            orig_items = original.get(entity_type, [])
            new_items = refreshed.get(entity_type, [])

            orig_titles = {o.get("title", "") for o in orig_items}
            new_titles = {o.get("title", "") for o in new_items}

            for title in sorted(new_titles - orig_titles):
                drift_items.append({"type": "addition", "entity": entity_type, "title": title})
            for title in sorted(orig_titles - new_titles):
                drift_items.append({"type": "removal", "entity": entity_type, "title": title})

        return drift_items
