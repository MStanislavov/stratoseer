"""Diff engine: structured comparison of two run bundles."""

from __future__ import annotations

from typing import Any

from app.engine.audit_writer import AuditWriter


def _fingerprint(entity_type: str, item: dict[str, Any]) -> str:
    """Build a lookup key from entity type and item title."""
    return f"{entity_type}|{item.get('title', '')}"


class DiffEngine:
    """Compare two runs and produce a structured diff report."""

    def __init__(self, audit_writer: AuditWriter) -> None:
        """Initialize the diff engine with an audit writer for loading run bundles.

        Args:
            audit_writer: Audit writer instance used to read stored run bundles.
        """
        self._audit_writer = audit_writer

    @staticmethod
    def _diff_entity_type(
        entity_type: str,
        items_a: list[dict[str, Any]],
        items_b: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, int]:
        """Compare items of a single entity type between two runs.

        Returns (additions, removals, changes, count_a, count_b).
        """
        fps_a = {_fingerprint(entity_type, o): o for o in items_a}
        fps_b = {_fingerprint(entity_type, o): o for o in items_b}

        additions = [fps_b[fp] for fp in sorted(set(fps_b) - set(fps_a))]
        removals = [fps_a[fp] for fp in sorted(set(fps_a) - set(fps_b))]

        changes: list[dict[str, Any]] = []
        for fp in sorted(set(fps_a) & set(fps_b)):
            a, b = fps_a[fp], fps_b[fp]
            diffs: dict[str, Any] = {}
            for key in ("description", "url"):
                if a.get(key) != b.get(key):
                    diffs[key] = {"old": a.get(key), "new": b.get(key)}
            if diffs:
                changes.append(
                    {
                        "title": a.get("title", ""),
                        "entity_type": entity_type,
                        "changes": diffs,
                    }
                )

        return additions, removals, changes, len(items_a), len(items_b)

    async def diff_runs(self, run_id_a: str, run_id_b: str) -> dict[str, Any]:
        """Compare two runs and return a structured diff.

        Returns a dictionary with additions, removals, changes, and a summary.
        """
        bundle_a = await self._audit_writer.read_bundle(run_id_a)
        bundle_b = await self._audit_writer.read_bundle(run_id_b)

        if bundle_a is None:
            raise ValueError(f"No bundle found for run {run_id_a}")
        if bundle_b is None:
            raise ValueError(f"No bundle found for run {run_id_b}")

        artifacts_a = bundle_a.get("final_artifacts", {})
        artifacts_b = bundle_b.get("final_artifacts", {})

        all_additions: list[dict[str, Any]] = []
        all_removals: list[dict[str, Any]] = []
        all_changes: list[dict[str, Any]] = []
        total_a = 0
        total_b = 0

        for entity_type in ("jobs", "certifications", "courses", "events", "groups", "trends"):
            additions, removals, changes, count_a, count_b = self._diff_entity_type(
                entity_type,
                artifacts_a.get(entity_type, []),
                artifacts_b.get(entity_type, []),
            )
            all_additions.extend(additions)
            all_removals.extend(removals)
            all_changes.extend(changes)
            total_a += count_a
            total_b += count_b

        return {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "additions": all_additions,
            "removals": all_removals,
            "changes": all_changes,
            "summary": {
                "items_a": total_a,
                "items_b": total_b,
                "added": len(all_additions),
                "removed": len(all_removals),
                "changed": len(all_changes),
            },
        }
