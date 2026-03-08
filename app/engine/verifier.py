"""Deterministic verifier: validates schema, evidence, confidence, policy, dedup, and bounds."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.engine.policy_engine import PolicyEngine


class VerifierStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


@dataclass
class ClaimResult:
    claim_text: str
    requires_evidence: bool
    evidence_ids: list[str]
    has_sufficient_evidence: bool
    confidence: float
    confidence_ok: bool
    status: VerifierStatus


@dataclass
class VerifierReport:
    overall_status: VerifierStatus
    claim_results: list[ClaimResult] = field(default_factory=list)
    schema_valid: bool = True
    evidence_coverage_ok: bool = True
    policy_compliant: bool = True
    dedup_ok: bool = True
    output_bounds_ok: bool = True
    errors: list[str] = field(default_factory=list)
    safe_degradation: bool = False


# ------------------------------------------------------------------
# Required-field specs for each output type
# ------------------------------------------------------------------

_OPPORTUNITY_REQUIRED_FIELDS = {"title", "source"}
_CLAIM_REQUIRED_FIELDS = {"claim_text", "requires_evidence"}
_EVIDENCE_REQUIRED_FIELDS = {"id", "url", "content_hash"}


def verify(
    *,
    opportunities: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    evidence_map: dict[str, dict[str, Any]],
    audit_events: list[dict[str, Any]] | None = None,
    policy_engine: PolicyEngine | None = None,
    safe_degradation: bool = False,
) -> VerifierReport:
    """Run all deterministic checks and return a :class:`VerifierReport`.

    Parameters
    ----------
    opportunities:
        List of opportunity dicts (must contain ``title`` and ``source``).
    claims:
        List of claim dicts (``claim_text``, ``requires_evidence``,
        ``evidence_ids``, ``confidence``).
    evidence_map:
        ``{evidence_id: evidence_dict}`` look-up table.
    audit_events:
        Optional list of audit-event dicts to check for policy violations.
    policy_engine:
        If provided, used for output-bounds and policy-compliance checks.
    safe_degradation:
        If *True* and some checks fail, return ``PARTIAL`` instead of
        ``FAIL`` (for cases where a retrieval failure is acceptable).
    """
    report = VerifierReport(overall_status=VerifierStatus.PASS, safe_degradation=safe_degradation)

    # 1. Schema validity -------------------------------------------------
    _check_schema(report, opportunities, claims, evidence_map)

    # 2. Evidence coverage -----------------------------------------------
    _check_evidence_coverage(report, claims, evidence_map)

    # 3. Confidence thresholds -------------------------------------------
    _check_confidence(report, claims, evidence_map)

    # 4. Policy compliance -----------------------------------------------
    _check_policy_compliance(report, audit_events or [], policy_engine)

    # 5. Dedup -----------------------------------------------------------
    _check_dedup(report, opportunities)

    # 6. Output bounds ---------------------------------------------------
    _check_output_bounds(report, opportunities, policy_engine)

    # Compute overall status ---------------------------------------------
    has_failure = (
        not report.schema_valid
        or not report.evidence_coverage_ok
        or not report.policy_compliant
        or not report.dedup_ok
        or not report.output_bounds_ok
    )
    has_claim_failure = any(
        cr.status == VerifierStatus.FAIL for cr in report.claim_results
    )

    if has_failure or has_claim_failure:
        report.overall_status = VerifierStatus.PARTIAL if safe_degradation else VerifierStatus.FAIL
    else:
        report.overall_status = VerifierStatus.PASS

    return report


# ======================================================================
# Internal check helpers
# ======================================================================


def _check_schema(
    report: VerifierReport,
    opportunities: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    evidence_map: dict[str, dict[str, Any]],
) -> None:
    for i, opp in enumerate(opportunities):
        missing = _OPPORTUNITY_REQUIRED_FIELDS - set(opp.keys())
        if missing:
            report.schema_valid = False
            report.errors.append(
                f"Opportunity [{i}] missing required fields: {sorted(missing)}"
            )

    for i, claim in enumerate(claims):
        missing = _CLAIM_REQUIRED_FIELDS - set(claim.keys())
        if missing:
            report.schema_valid = False
            report.errors.append(
                f"Claim [{i}] missing required fields: {sorted(missing)}"
            )

    for eid, ev in evidence_map.items():
        missing = _EVIDENCE_REQUIRED_FIELDS - set(ev.keys())
        if missing:
            report.schema_valid = False
            report.errors.append(
                f"Evidence '{eid}' missing required fields: {sorted(missing)}"
            )


def _check_evidence_coverage(
    report: VerifierReport,
    claims: list[dict[str, Any]],
    evidence_map: dict[str, dict[str, Any]],
) -> None:
    for claim in claims:
        if not claim.get("requires_evidence", False):
            continue
        evidence_ids = claim.get("evidence_ids", [])
        if not evidence_ids:
            report.evidence_coverage_ok = False
            report.errors.append(
                f"Claim '{claim.get('claim_text', '?')}' requires evidence but has none"
            )
            continue
        for eid in evidence_ids:
            if eid not in evidence_map:
                report.evidence_coverage_ok = False
                report.errors.append(
                    f"Claim '{claim.get('claim_text', '?')}' references unknown evidence '{eid}'"
                )


def _check_confidence(
    report: VerifierReport,
    claims: list[dict[str, Any]],
    evidence_map: dict[str, dict[str, Any]],
) -> None:
    confidence_threshold = 0.7
    for claim in claims:
        requires_evidence = claim.get("requires_evidence", False)
        evidence_ids = claim.get("evidence_ids", [])
        confidence = claim.get("confidence", 0.0)
        confidence_ok = confidence >= confidence_threshold

        # Determine if evidence is sufficient
        has_sufficient = True
        if requires_evidence:
            if not evidence_ids:
                has_sufficient = False
            else:
                for eid in evidence_ids:
                    if eid not in evidence_map:
                        has_sufficient = False
                        break

        status = VerifierStatus.PASS
        if not has_sufficient or not confidence_ok:
            status = VerifierStatus.FAIL

        report.claim_results.append(
            ClaimResult(
                claim_text=claim.get("claim_text", ""),
                requires_evidence=requires_evidence,
                evidence_ids=evidence_ids,
                has_sufficient_evidence=has_sufficient,
                confidence=confidence,
                confidence_ok=confidence_ok,
                status=status,
            )
        )


def _check_policy_compliance(
    report: VerifierReport,
    audit_events: list[dict[str, Any]],
    policy_engine: PolicyEngine | None,
) -> None:
    if policy_engine is None:
        return
    for event in audit_events:
        if event.get("event_type") != "tool_call":
            continue
        agent = event.get("agent", "")
        tool = (event.get("data") or {}).get("tool", "")
        if agent and tool and not policy_engine.is_tool_allowed(agent, tool):
            report.policy_compliant = False
            report.errors.append(
                f"Policy violation: agent '{agent}' used forbidden tool '{tool}'"
            )


def _check_dedup(
    report: VerifierReport,
    opportunities: list[dict[str, Any]],
) -> None:
    seen: set[str] = set()
    for opp in opportunities:
        title = opp.get("title", "")
        source = opp.get("source", "")
        fingerprint = f"{title}|{source}"
        if fingerprint in seen:
            report.dedup_ok = False
            report.errors.append(
                f"Duplicate opportunity: title='{title}', source='{source}'"
            )
        seen.add(fingerprint)


def _check_output_bounds(
    report: VerifierReport,
    opportunities: list[dict[str, Any]],
    policy_engine: PolicyEngine | None,
) -> None:
    if policy_engine is None:
        return
    global_config = policy_engine.get_global_config()
    max_items = global_config.get("max_output_items")
    if max_items is not None and len(opportunities) > max_items:
        report.output_bounds_ok = False
        report.errors.append(
            f"Output exceeds max_output_items ({len(opportunities)} > {max_items})"
        )
