"""Deterministic inter-agent verifier.

Validates agent outputs for schema conformance, output bounds, dedup,
and policy compliance. No LLM calls -- all checks are rule-based.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.engine.policy_engine import PolicyEngine

_EXPIRY_PATTERNS = [
    r"no longer accepting applications",
    r"this job has expired",
    r"this listing has expired",
    r"position has been filled",
    r"this job is no longer available",
    r"posting has closed",
    r"applications? closed",
    r"no longer available",
    r"job has been removed",
]

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Types
# ------------------------------------------------------------------


class VerificationStatus(str, Enum):
    """Outcome of a single verification check or an aggregate result."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


@dataclass
class CheckResult:
    """Result of a single named verification check."""

    check_name: str
    status: VerificationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentVerification:
    """Aggregated verification result for a single agent's output."""

    agent_name: str
    status: VerificationStatus
    checks: list[CheckResult]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class VerificationError(Exception):
    """Raised when a hard-fail verification prevents pipeline continuation."""

    def __init__(self, verification: AgentVerification) -> None:
        """Initialize with the failed agent verification result.

        Args:
            verification: The AgentVerification that triggered the hard failure.
        """
        self.verification = verification
        super().__init__(
            f"Verification failed for {verification.agent_name}: "
            + ", ".join(
                c.message for c in verification.checks if c.status == VerificationStatus.FAIL
            )
        )


# ------------------------------------------------------------------
# Verifier
# ------------------------------------------------------------------

_ALL_CHECKS_PASSED = "All checks passed"

_EXPECTED_SEARCH_PROMPT_KEYS = {
    "job_prompt",
    "cert_prompt",
    "event_prompt",
    "group_prompt",
    "trend_prompt",
}

_RAW_RESULT_KEYS = [
    "raw_job_results",
    "raw_cert_results",
    "raw_event_results",
    "raw_group_results",
    "raw_trend_results",
]

_FORMATTED_KEYS = [
    "formatted_jobs",
    "formatted_certifications",
    "formatted_courses",
    "formatted_events",
    "formatted_groups",
    "formatted_trends",
]


class Verifier:
    """Deterministic output validator dispatching per-agent checks."""

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        """Initialize the verifier with an optional policy engine for boundary and budget checks.

        Args:
            policy_engine: Policy engine used to read boundary rules
                and output limits. If None, defaults are used.
        """
        self._policy_engine = policy_engine
        global_cfg = policy_engine.get_global_config() if policy_engine else {}
        self._max_output_items: int = global_cfg.get("max_output_items", 50)
        self._expiry_patterns = [re.compile(p, re.IGNORECASE) for p in _EXPIRY_PATTERNS]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(self, agent_name: str, output: dict[str, Any]) -> AgentVerification:
        """Run all checks for *agent_name* and return an AgentVerification."""
        dispatch = {
            "goal_extractor": self._verify_goal_extractor,
            "web_scrapers": self._verify_web_scrapers,
            "data_formatter": self._verify_data_formatter,
            "ceo": self._verify_ceo,
            "cfo": self._verify_cfo,
            "cover_letter_agent": self._verify_cover_letter,
        }
        checker = dispatch.get(agent_name)
        if checker is None:
            return AgentVerification(
                agent_name=agent_name,
                status=VerificationStatus.PASS,
                checks=[
                    CheckResult(
                        "unknown_agent",
                        VerificationStatus.PASS,
                        f"No checks defined for {agent_name}",
                    )
                ],
            )
        checks = checker(output)
        overall = self._aggregate_status(checks)
        return AgentVerification(agent_name=agent_name, status=overall, checks=checks)

    def build_report(self, verifications: list[AgentVerification]) -> dict[str, Any]:
        """Aggregate per-agent verifications into a final verifier report."""
        all_checks = [c for v in verifications for c in v.checks]
        passed = sum(1 for c in all_checks if c.status == VerificationStatus.PASS)
        warnings = sum(1 for c in all_checks if c.status == VerificationStatus.PARTIAL)
        failures = sum(1 for c in all_checks if c.status == VerificationStatus.FAIL)

        if failures > 0:
            overall = "fail"
        elif warnings > 0:
            overall = "partial"
        else:
            overall = "pass"

        return {
            "overall_status": overall,
            "agent_results": [
                {
                    "agent_name": v.agent_name,
                    "status": v.status.value,
                    "checks": [
                        {
                            "check_name": c.check_name,
                            "status": c.status.value,
                            "message": c.message,
                            "details": c.details,
                        }
                        for c in v.checks
                    ],
                    "timestamp": v.timestamp,
                }
                for v in verifications
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_checks": len(all_checks),
            "passed": passed,
            "warnings": warnings,
            "failures": failures,
        }

    # ------------------------------------------------------------------
    # Per-agent validators
    # ------------------------------------------------------------------

    def _verify_goal_extractor(self, output: dict[str, Any]) -> list[CheckResult]:
        checks: list[CheckResult] = []

        prompts = output.get("search_prompts")
        if not isinstance(prompts, dict):
            checks.append(
                CheckResult(
                    "search_prompts_type",
                    VerificationStatus.FAIL,
                    "search_prompts must be a dict",
                )
            )
            return checks

        # Check expected keys
        missing = _EXPECTED_SEARCH_PROMPT_KEYS - set(prompts.keys())
        if missing:
            checks.append(
                CheckResult(
                    "search_prompts_keys",
                    VerificationStatus.FAIL,
                    f"Missing prompt keys: {sorted(missing)}",
                    details={"missing": sorted(missing)},
                )
            )
        else:
            checks.append(
                CheckResult(
                    "search_prompts_keys",
                    VerificationStatus.PASS,
                    "All expected prompt keys present",
                )
            )

        # Check non-empty values
        empty = [k for k, v in prompts.items() if not isinstance(v, str) or not v.strip()]
        if empty:
            checks.append(
                CheckResult(
                    "search_prompts_values",
                    VerificationStatus.PARTIAL,
                    f"Empty prompt values: {sorted(empty)}",
                    details={"empty_keys": sorted(empty)},
                )
            )
        else:
            checks.append(
                CheckResult(
                    "search_prompts_values",
                    VerificationStatus.PASS,
                    "All prompt values are non-empty strings",
                )
            )

        # Boundary compliance
        if self._policy_engine:
            try:
                boundaries = self._policy_engine.get_boundaries("goal_extractor")
                allowed_outputs = set(boundaries["outputs"])
                actual_outputs = set(output.keys())
                disallowed = actual_outputs - allowed_outputs - {"errors"}
                if disallowed:
                    checks.append(
                        CheckResult(
                            "boundary_compliance",
                            VerificationStatus.FAIL,
                            f"Output keys not in boundaries: {sorted(disallowed)}",
                            details={"disallowed": sorted(disallowed)},
                        )
                    )
                else:
                    checks.append(
                        CheckResult(
                            "boundary_compliance",
                            VerificationStatus.PASS,
                            "Output keys comply with boundaries",
                        )
                    )
            except KeyError:
                pass

        return checks

    def _verify_web_scrapers(self, output: dict[str, Any]) -> list[CheckResult]:
        checks: list[CheckResult] = []
        total_items = 0

        for key in _RAW_RESULT_KEYS:
            items = output.get(key)
            if items is None:
                continue
            valid, key_checks = self._validate_item_list(key, items)
            checks.extend(key_checks)
            if not valid:
                continue

            total_items += len(items)
            checks.extend(self._check_missing_titles(key, items, VerificationStatus.PARTIAL))
            checks.extend(self._check_duplicate_urls(key, items))

        # Bounds check
        checks.append(
            self._check_output_bounds(
                total_items,
                "Total items",
                include_soft_warning=True,
            )
        )

        # Freshness check for job results
        job_items = output.get("raw_job_results")
        if isinstance(job_items, list):
            checks.append(self._check_job_freshness(job_items))

        if not checks:
            checks.append(
                CheckResult("web_scrapers_general", VerificationStatus.PASS, _ALL_CHECKS_PASSED)
            )

        return checks

    def _verify_data_formatter(self, output: dict[str, Any]) -> list[CheckResult]:
        checks: list[CheckResult] = []
        total_items = 0

        for key in _FORMATTED_KEYS:
            items = output.get(key)
            if items is None:
                continue
            valid, key_checks = self._validate_item_list(key, items)
            checks.extend(key_checks)
            if not valid:
                continue

            total_items += len(items)
            checks.extend(self._check_missing_titles(key, items, VerificationStatus.FAIL))
            checks.extend(self._check_duplicate_titles(key, items))

        # Total bounds
        checks.append(
            self._check_output_bounds(
                total_items,
                "Total formatted items",
                include_soft_warning=False,
            )
        )

        if not checks:
            checks.append(
                CheckResult("data_formatter_general", VerificationStatus.PASS, _ALL_CHECKS_PASSED)
            )

        return checks

    def _verify_ceo(self, output: dict[str, Any]) -> list[CheckResult]:
        checks: list[CheckResult] = []

        recs = output.get("strategic_recommendations")
        if not isinstance(recs, list):
            checks.append(
                CheckResult(
                    "strategic_recommendations_type",
                    VerificationStatus.FAIL,
                    "strategic_recommendations must be a list",
                )
            )
        else:
            checks.extend(self._validate_recommendations(recs))

        summary = output.get("ceo_summary")
        if not isinstance(summary, str) or not summary.strip():
            checks.append(
                CheckResult(
                    "ceo_summary",
                    VerificationStatus.FAIL,
                    "ceo_summary must be a non-empty string",
                )
            )
        else:
            checks.append(
                CheckResult(
                    "ceo_summary",
                    VerificationStatus.PASS,
                    "ceo_summary is present",
                )
            )

        if not checks:
            checks.append(CheckResult("ceo_general", VerificationStatus.PASS, _ALL_CHECKS_PASSED))

        return checks

    def _verify_cfo(self, output: dict[str, Any]) -> list[CheckResult]:
        checks: list[CheckResult] = []

        assessments = output.get("risk_assessments")
        if not isinstance(assessments, list):
            checks.append(
                CheckResult(
                    "risk_assessments_type",
                    VerificationStatus.FAIL,
                    "risk_assessments must be a list",
                )
            )
        else:
            for i, assessment in enumerate(assessments):
                if not isinstance(assessment, dict):
                    checks.append(
                        CheckResult(
                            f"assessment_{i}_type",
                            VerificationStatus.FAIL,
                            f"Assessment {i} must be a dict",
                        )
                    )
                    continue
                missing = [f for f in ("area", "risk_level") if f not in assessment]
                if missing:
                    checks.append(
                        CheckResult(
                            f"assessment_{i}_fields",
                            VerificationStatus.PARTIAL,
                            f"Assessment {i} missing fields: {missing}",
                            details={"index": i, "missing": missing},
                        )
                    )

        summary = output.get("cfo_summary")
        if not isinstance(summary, str) or not summary.strip():
            checks.append(
                CheckResult(
                    "cfo_summary",
                    VerificationStatus.FAIL,
                    "cfo_summary must be a non-empty string",
                )
            )
        else:
            checks.append(
                CheckResult(
                    "cfo_summary",
                    VerificationStatus.PASS,
                    "cfo_summary is present",
                )
            )

        if not checks:
            checks.append(CheckResult("cfo_general", VerificationStatus.PASS, _ALL_CHECKS_PASSED))

        return checks

    def _verify_cover_letter(self, output: dict[str, Any]) -> list[CheckResult]:
        checks: list[CheckResult] = []

        content = output.get("cover_letter_content")
        if not isinstance(content, str) or not content.strip():
            checks.append(
                CheckResult(
                    "cover_letter_content",
                    VerificationStatus.FAIL,
                    "cover_letter_content must be a non-empty string",
                )
            )
            return checks

        length = len(content)
        if length < 100:
            checks.append(
                CheckResult(
                    "cover_letter_length_min",
                    VerificationStatus.PARTIAL,
                    f"Cover letter is short ({length} chars, expected >= 100)",
                    details={"length": length},
                )
            )
        elif length > 10000:
            checks.append(
                CheckResult(
                    "cover_letter_length_max",
                    VerificationStatus.FAIL,
                    f"Cover letter is too long ({length} chars, max 10000)",
                    details={"length": length},
                )
            )
        else:
            checks.append(
                CheckResult(
                    "cover_letter_length",
                    VerificationStatus.PASS,
                    f"Cover letter length ({length} chars) within bounds",
                )
            )

        return checks

    def _check_job_freshness(self, items: list[dict[str, Any]]) -> CheckResult:
        """Scan job results for expiry signals. Returns PARTIAL if any found."""
        flagged: list[int] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            text = " ".join(
                [
                    item.get("title", ""),
                    item.get("snippet", ""),
                ]
            )
            if any(p.search(text) for p in self._expiry_patterns):
                flagged.append(i)

        if flagged:
            return CheckResult(
                "job_freshness",
                VerificationStatus.PARTIAL,
                f"{len(flagged)} job result(s) contain expiry signals",
                details={"flagged_indices": flagged},
            )
        return CheckResult(
            "job_freshness",
            VerificationStatus.PASS,
            "No expiry signals in job results",
        )

    # ------------------------------------------------------------------
    # Shared item-list helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_item_list(key: str, items: Any) -> tuple[bool, list[CheckResult]]:
        """Validate that *items* is a list of dicts.

        Returns ``(valid, checks)`` where *valid* is ``False`` when the
        caller should skip further per-item checks for this key.
        """
        checks: list[CheckResult] = []
        if not isinstance(items, list):
            checks.append(
                CheckResult(
                    f"{key}_type",
                    VerificationStatus.FAIL,
                    f"{key} must be a list, got {type(items).__name__}",
                )
            )
            return False, checks

        for item in items:
            if not isinstance(item, dict):
                checks.append(
                    CheckResult(
                        f"{key}_item_type",
                        VerificationStatus.FAIL,
                        f"Items in {key} must be dicts",
                    )
                )
                break

        return True, checks

    @staticmethod
    def _check_missing_titles(
        key: str,
        items: list[dict[str, Any]],
        severity: VerificationStatus,
    ) -> list[CheckResult]:
        """Return a check if any dict item in *items* is missing a title."""
        missing_title = [
            i for i, item in enumerate(items) if isinstance(item, dict) and not item.get("title")
        ]
        if missing_title:
            return [
                CheckResult(
                    f"{key}_titles",
                    severity,
                    f"{len(missing_title)} item(s) in {key} missing title",
                    details={"indices": missing_title},
                )
            ]
        return []

    @staticmethod
    def _check_duplicate_urls(key: str, items: list[dict[str, Any]]) -> list[CheckResult]:
        """Return a PARTIAL check if duplicate URLs exist in *items*."""
        urls = [item.get("url") for item in items if isinstance(item, dict) and item.get("url")]
        dups = [u for u in set(urls) if urls.count(u) > 1]
        if dups:
            return [
                CheckResult(
                    f"{key}_dedup",
                    VerificationStatus.PARTIAL,
                    f"Duplicate URLs in {key}: {len(dups)} unique duplicates",
                    details={"duplicate_urls": dups},
                )
            ]
        return []

    @staticmethod
    def _check_duplicate_titles(key: str, items: list[dict[str, Any]]) -> list[CheckResult]:
        """Return a PARTIAL check if true duplicates exist in *items*.

        Two items with the same title but different company/provider/platform
        are NOT duplicates (e.g. "Software Engineer III" at two companies).
        """

        def _dedup_key(item: dict[str, Any]) -> str:
            title = item.get("title", "")
            for attr in ("company", "provider", "platform", "organizer", "url"):
                val = item.get(attr)
                if val:
                    return f"{title}||{val}"
            return title

        keys = [_dedup_key(item) for item in items if isinstance(item, dict) and item.get("title")]
        dup_keys = [k for k in set(keys) if keys.count(k) > 1]
        if dup_keys:
            dup_titles = [k.split("||")[0] for k in dup_keys]
            return [
                CheckResult(
                    f"{key}_dedup",
                    VerificationStatus.PARTIAL,
                    f"Duplicate titles in {key}: {len(dup_keys)} unique duplicates",
                    details={"duplicate_titles": dup_titles},
                )
            ]
        return []

    def _check_output_bounds(
        self,
        total_items: int,
        label: str,
        *,
        include_soft_warning: bool,
    ) -> CheckResult:
        """Return a single bounds check for *total_items* against the policy limit.

        When *include_soft_warning* is ``True`` a PARTIAL result is returned
        for counts between ``limit`` and ``2 * limit`` (used by web_scrapers).
        Otherwise only the hard 2x fail and pass branches apply.
        """
        limit = self._max_output_items
        if total_items > limit * 2:
            return CheckResult(
                "output_bounds",
                VerificationStatus.FAIL,
                f"{label} ({total_items}) exceeds 2x limit ({limit * 2})",
                details={"total": total_items, "limit": limit},
            )
        if include_soft_warning and total_items > limit:
            return CheckResult(
                "output_bounds",
                VerificationStatus.PARTIAL,
                f"{label} ({total_items}) exceeds limit ({limit})",
                details={"total": total_items, "limit": limit},
            )
        return CheckResult(
            "output_bounds",
            VerificationStatus.PASS,
            f"{label} ({total_items}) within limit"
            + (f" ({limit})" if include_soft_warning else ""),
        )

    @staticmethod
    def _validate_recommendations(recs: list[Any]) -> list[CheckResult]:
        """Validate a list of CEO strategic recommendation dicts."""
        checks: list[CheckResult] = []
        for i, rec in enumerate(recs):
            if not isinstance(rec, dict):
                checks.append(
                    CheckResult(
                        f"recommendation_{i}_type",
                        VerificationStatus.FAIL,
                        f"Recommendation {i} must be a dict",
                    )
                )
                continue
            missing = [f for f in ("area", "recommendation", "priority") if f not in rec]
            if missing:
                checks.append(
                    CheckResult(
                        f"recommendation_{i}_fields",
                        VerificationStatus.PARTIAL,
                        f"Recommendation {i} missing fields: {missing}",
                        details={"index": i, "missing": missing},
                    )
                )
            priority = rec.get("priority", "")
            if isinstance(priority, str) and priority not in ("high", "medium", "low"):
                checks.append(
                    CheckResult(
                        f"recommendation_{i}_priority",
                        VerificationStatus.PARTIAL,
                        f"Recommendation {i} has invalid priority: '{priority}'",
                        details={"index": i, "priority": priority},
                    )
                )
        return checks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_status(checks: list[CheckResult]) -> VerificationStatus:
        if any(c.status == VerificationStatus.FAIL for c in checks):
            return VerificationStatus.FAIL
        if any(c.status == VerificationStatus.PARTIAL for c in checks):
            return VerificationStatus.PARTIAL
        return VerificationStatus.PASS
