"""Weekly pipeline: goal_extractor -> web_scrapers -> data_formatter -> ceo -> cfo -> audit."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.factory import AgentFactory
from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine
from app.engine.token_tracker import RunTokenTracker
from app.engine.verifier import Verifier
from app.graphs.log import (
    _publish_sse,
    make_fan_out_node,
    make_job_expiry_validator_node,
    make_node,
    make_url_filter_report_node,
    node_end,
    node_start,
    route,
    warn,
)
from app.graphs.state import WeeklyState

_P = "weekly"

_SCRAPER_CATEGORIES = [
    ("job", "job_prompt"),
    ("cert", "cert_prompt"),
    ("course", "course_prompt"),
    ("event", "event_prompt"),
    ("group", "group_prompt"),
    ("trend", "trend_prompt"),
]


# ------------------------------------------------------------------
# Audit node (terminal, uses verifier report)
# ------------------------------------------------------------------


def _make_audit_node(
    audit_writer: AuditWriter | None = None,
    policy_engine: PolicyEngine | None = None,
    verifier: Verifier | None = None,
    event_manager: Any | None = None,
):
    async def audit_node(state: WeeklyState) -> dict[str, Any]:
        run_id = state.get("run_id", "unknown")
        now = datetime.now(timezone.utc).isoformat

        await _publish_sse(
            event_manager,
            run_id,
            {
                "type": "agent_started",
                "agent": "audit_writer",
                "timestamp": now(),
            },
        )

        if audit_writer is None:
            node_start(_P, state, "audit_writer", skipped=True)
            await _publish_sse(
                event_manager,
                run_id,
                {
                    "type": "agent_completed",
                    "agent": "audit_writer",
                    "verification_status": "pass",
                    "elapsed": 0,
                    "timestamp": now(),
                },
            )
            return {}

        node_start(_P, state, "audit_writer")
        import time

        t0 = time.monotonic()

        run_id = state.get("run_id", "unknown")
        policy_hash = policy_engine.version.hash if policy_engine else ""

        await audit_writer.append(
            run_id,
            AuditEvent(
                timestamp=now(),
                event_type="agent_start",
                agent="audit_writer",
            ),
        )

        # Build verifier report from accumulated results
        verifier_report: dict[str, Any] = {}
        if verifier:
            from app.engine.verifier import AgentVerification, CheckResult, VerificationStatus

            verifications: list[AgentVerification] = []
            for vr in state.get("verifier_results", []):
                checks = [
                    CheckResult(
                        check_name=c["check_name"],
                        status=VerificationStatus(c["status"]),
                        message=c["message"],
                    )
                    for c in vr.get("checks", [])
                ]
                verifications.append(
                    AgentVerification(
                        agent_name=vr["agent_name"],
                        status=VerificationStatus(vr["status"]),
                        checks=checks,
                        timestamp=vr.get("timestamp", ""),
                    )
                )
            verifier_report = verifier.build_report(verifications)

        await audit_writer.append(
            run_id,
            AuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type="output",
                agent="weekly_pipeline",
                data={
                    "job_count": len(state.get("formatted_jobs", [])),
                    "cert_count": len(state.get("formatted_certifications", [])),
                    "course_count": len(state.get("formatted_courses", [])),
                    "event_count": len(state.get("formatted_events", [])),
                    "group_count": len(state.get("formatted_groups", [])),
                    "trend_count": len(state.get("formatted_trends", [])),
                    "recommendation_count": len(state.get("strategic_recommendations", [])),
                    "assessment_count": len(state.get("risk_assessments", [])),
                },
            ),
        )
        await audit_writer.create_run_bundle(
            run_id=run_id,
            profile_hash=state.get("profile_id", "unknown"),
            policy_version_hash=policy_hash,
            verifier_report=verifier_report,
            final_artifacts={
                "jobs": state.get("formatted_jobs", []),
                "certifications": state.get("formatted_certifications", []),
                "courses": state.get("formatted_courses", []),
                "events": state.get("formatted_events", []),
                "groups": state.get("formatted_groups", []),
                "trends": state.get("formatted_trends", []),
                "strategic_recommendations": state.get("strategic_recommendations", []),
                "ceo_summary": state.get("ceo_summary", ""),
                "risk_assessments": state.get("risk_assessments", []),
                "cfo_summary": state.get("cfo_summary", ""),
            },
        )

        elapsed = time.monotonic() - t0
        node_end(_P, state, "audit_writer", elapsed)

        await audit_writer.append(
            run_id,
            AuditEvent(
                timestamp=now(),
                event_type="agent_end",
                agent="audit_writer",
            ),
        )

        await _publish_sse(
            event_manager,
            run_id,
            {
                "type": "agent_completed",
                "agent": "audit_writer",
                "verification_status": "pass",
                "elapsed": round(elapsed, 2),
                "timestamp": now(),
            },
        )
        return {}

    return audit_node


# ------------------------------------------------------------------
# Conditional routing
# ------------------------------------------------------------------


def _check_scraper_results(state: WeeklyState) -> str:
    raw_jobs = state.get("raw_job_results", [])
    raw_certs = state.get("raw_cert_results", [])
    raw_events = state.get("raw_event_results", [])
    raw_groups = state.get("raw_group_results", [])
    raw_trends = state.get("raw_trend_results", [])
    if not raw_jobs and not raw_certs and not raw_events and not raw_groups and not raw_trends:
        warn(_P, state, "all web scrapers returned empty, entering safe degradation")
        return "safe_degrade"
    route(
        _P,
        state,
        "data_formatter",
        jobs=len(raw_jobs),
        certs=len(raw_certs),
        events=len(raw_events),
        groups=len(raw_groups),
        trends=len(raw_trends),
    )
    return "format"


def _safe_degrade_node(state: WeeklyState) -> dict[str, Any]:
    warn(_P, state, "safe_degrade activated")
    return {
        "safe_degradation": True,
        "formatted_jobs": [],
        "formatted_certifications": [],
        "formatted_courses": [],
        "formatted_events": [],
        "formatted_groups": [],
        "formatted_trends": [],
        "errors": state.get("errors", [])
        + ["All web scrapers returned no results; safe degradation active"],
    }


# ------------------------------------------------------------------
# Graph builder
# ------------------------------------------------------------------


def build_weekly_graph(
    agent_factory: AgentFactory,
    policy_engine: PolicyEngine | None = None,
    audit_writer: AuditWriter | None = None,
    verifier: Verifier | None = None,
    event_manager: Any | None = None,
    token_tracker: RunTokenTracker | None = None,
) -> StateGraph:
    """Construct the weekly pipeline StateGraph."""
    goal_extractor = agent_factory.create_goal_extractor()
    web_scraper = agent_factory.create_web_scraper()
    data_formatter = agent_factory.create_data_formatter()
    ceo = agent_factory.create_ceo()
    cfo = agent_factory.create_cfo()

    graph = StateGraph(WeeklyState)

    graph.add_node(
        "goal_extractor",
        make_node(
            _P,
            "goal_extractor",
            goal_extractor,
            "llm_structured_output",
            policy_engine,
            audit_writer,
            verifier,
            event_manager,
            token_tracker=token_tracker,
        ),
    )
    graph.add_node(
        "web_scrapers",
        make_fan_out_node(
            _P,
            "web_scrapers",
            web_scraper,
            "web_search",
            _SCRAPER_CATEGORIES,
            policy_engine,
            audit_writer,
            verifier,
            event_manager,
            token_tracker=token_tracker,
        ),
    )
    graph.add_node(
        "data_formatter",
        make_node(
            _P,
            "data_formatter",
            data_formatter,
            "llm_structured_output",
            policy_engine,
            audit_writer,
            verifier,
            event_manager,
            token_tracker=token_tracker,
        ),
    )
    graph.add_node(
        "ceo",
        make_node(
            _P,
            "ceo",
            ceo,
            "llm_structured_output",
            policy_engine,
            audit_writer,
            verifier,
            event_manager,
            token_tracker=token_tracker,
        ),
    )
    graph.add_node(
        "cfo",
        make_node(
            _P,
            "cfo",
            cfo,
            "llm_structured_output",
            policy_engine,
            audit_writer,
            verifier,
            event_manager,
            token_tracker=token_tracker,
        ),
    )
    graph.add_node(
        "job_expiry_check", make_job_expiry_validator_node(_P, audit_writer, event_manager)
    )
    graph.add_node(
        "url_filter_report", make_url_filter_report_node(_P, audit_writer, event_manager)
    )
    graph.add_node(
        "audit_writer", _make_audit_node(audit_writer, policy_engine, verifier, event_manager)
    )
    graph.add_node("safe_degrade", _safe_degrade_node)

    graph.set_entry_point("goal_extractor")
    graph.add_edge("goal_extractor", "web_scrapers")
    graph.add_edge("web_scrapers", "job_expiry_check")
    graph.add_edge("job_expiry_check", "url_filter_report")
    graph.add_conditional_edges(
        "url_filter_report",
        _check_scraper_results,
        {"format": "data_formatter", "safe_degrade": "safe_degrade"},
    )
    graph.add_edge("data_formatter", "ceo")
    graph.add_edge("safe_degrade", "ceo")
    graph.add_edge("ceo", "cfo")
    graph.add_edge("cfo", "audit_writer")
    graph.add_edge("audit_writer", END)

    return graph
