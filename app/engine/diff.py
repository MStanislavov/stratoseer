"""Diff engine: structured comparison of two run bundles."""

from __future__ import annotations

from typing import Any

from app.engine.audit_writer import AuditWriter


class DiffEngine:
    """Compare two runs and produce a structured diff report."""

    def __init__(self, audit_writer: AuditWriter) -> None:
        self._audit_writer = audit_writer

    def diff_runs(self, run_id_a: str, run_id_b: str) -> dict[str, Any]:
        """Compare two runs and return structured diff.

        Returns a dictionary with additions, removals, changes to
        opportunities, and a summary section.
        """
        bundle_a = self._audit_writer.read_bundle(run_id_a)
        bundle_b = self._audit_writer.read_bundle(run_id_b)

        if bundle_a is None:
            raise ValueError(f"No bundle found for run {run_id_a}")
        if bundle_b is None:
            raise ValueError(f"No bundle found for run {run_id_b}")

        artifacts_a = bundle_a.get("final_artifacts", {})
        artifacts_b = bundle_b.get("final_artifacts", {})

        opps_a = artifacts_a.get("opportunities", [])
        opps_b = artifacts_b.get("opportunities", [])

        # Build lookup by title+source fingerprint
        def fingerprint(opp: dict[str, Any]) -> str:
            return f"{opp.get('title', '')}|{opp.get('source', '')}"

        fps_a = {fingerprint(o): o for o in opps_a}
        fps_b = {fingerprint(o): o for o in opps_b}

        additions = [fps_b[fp] for fp in sorted(set(fps_b) - set(fps_a))]
        removals = [fps_a[fp] for fp in sorted(set(fps_a) - set(fps_b))]

        # Check for changes in shared opportunities
        changes: list[dict[str, Any]] = []
        for fp in sorted(set(fps_a) & set(fps_b)):
            a, b = fps_a[fp], fps_b[fp]
            diffs: dict[str, Any] = {}
            for key in ("description", "url", "opportunity_type"):
                if a.get(key) != b.get(key):
                    diffs[key] = {"old": a.get(key), "new": b.get(key)}
            if diffs:
                changes.append({"title": a.get("title", ""), "changes": diffs})

        # Verifier status comparison
        verifier_a = bundle_a.get("verifier_report", {}).get(
            "overall_status", "unknown"
        )
        verifier_b = bundle_b.get("verifier_report", {}).get(
            "overall_status", "unknown"
        )

        return {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "additions": additions,
            "removals": removals,
            "changes": changes,
            "summary": {
                "opportunities_a": len(opps_a),
                "opportunities_b": len(opps_b),
                "added": len(additions),
                "removed": len(removals),
                "changed": len(changes),
                "verifier_a": verifier_a,
                "verifier_b": verifier_b,
            },
        }
