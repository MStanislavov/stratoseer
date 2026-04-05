"""LangGraph cover letter pipeline: cover_letter_agent -> audit_writer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.factory import AgentFactory
from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine
from app.engine.token_tracker import RunTokenTracker
from app.engine.verifier import Verifier
from app.graphs.log import _publish_sse, make_node, node_end, node_start
from app.graphs.state import CoverLetterState

_P = "cover_letter"


# ------------------------------------------------------------------
# Audit node (terminal, uses verifier report)
# ------------------------------------------------------------------


def _make_audit_node(
    audit_writer: AuditWriter | None = None,
    policy_engine: PolicyEngine | None = None,
    verifier: Verifier | None = None,
    event_manager: Any | None = None,
):
    """Return a graph node that writes audit events and creates the run bundle."""

    async def audit_node(state: CoverLetterState) -> dict[str, Any]:
        run_id = state.get("run_id", "unknown")
        now = datetime.now(timezone.utc).isoformat

        await _publish_sse(event_manager, run_id, {
            "type": "agent_started",
            "agent": "audit_writer",
            "timestamp": now(),
        })

        if audit_writer is None:
            node_start(_P, state, "audit_writer", skipped=True)
            await _publish_sse(event_manager, run_id, {
                "type": "agent_completed",
                "agent": "audit_writer",
                "verification_status": "pass",
                "elapsed": 0,
                "timestamp": now(),
            })
            return {}

        node_start(_P, state, "audit_writer")
        import time
        t0 = time.monotonic()

        run_id = state.get("run_id", "unknown")
        policy_hash = policy_engine.version.hash if policy_engine else ""

        await audit_writer.append(run_id, AuditEvent(
            timestamp=now(),
            event_type="agent_start",
            agent="audit_writer",
        ))

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
                verifications.append(AgentVerification(
                    agent_name=vr["agent_name"],
                    status=VerificationStatus(vr["status"]),
                    checks=checks,
                    timestamp=vr.get("timestamp", ""),
                ))
            verifier_report = verifier.build_report(verifications)

        await audit_writer.append(
            run_id,
            AuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type="output",
                agent="cover_letter_pipeline",
                data={
                    "has_content": bool(state.get("cover_letter_content")),
                },
            ),
        )

        await audit_writer.create_run_bundle(
            run_id=run_id,
            profile_hash=state.get("profile_id", "unknown"),
            policy_version_hash=policy_hash,
            verifier_report=verifier_report,
            final_artifacts={
                "cover_letter": state.get("cover_letter_content", ""),
            },
        )

        elapsed = time.monotonic() - t0
        node_end(_P, state, "audit_writer", elapsed)

        await audit_writer.append(run_id, AuditEvent(
            timestamp=now(),
            event_type="agent_end",
            agent="audit_writer",
        ))

        await _publish_sse(event_manager, run_id, {
            "type": "agent_completed",
            "agent": "audit_writer",
            "verification_status": "pass",
            "elapsed": round(elapsed, 2),
            "timestamp": now(),
        })
        return {}

    return audit_node


# ------------------------------------------------------------------
# Graph builder
# ------------------------------------------------------------------


def build_cover_letter_graph(
    agent_factory: AgentFactory,
    policy_engine: PolicyEngine | None = None,
    audit_writer: AuditWriter | None = None,
    verifier: Verifier | None = None,
    event_manager: Any | None = None,
    token_tracker: RunTokenTracker | None = None,
) -> StateGraph:
    """Construct the cover letter pipeline StateGraph.

    Nodes: cover_letter_agent -> audit_writer
    """
    cover_letter_agent = agent_factory.create_cover_letter_agent()

    graph = StateGraph(CoverLetterState)

    graph.add_node("cover_letter_agent", make_node(
        _P, "cover_letter_agent", cover_letter_agent, "llm_generate_text",
        policy_engine, audit_writer, verifier, event_manager,
        token_tracker=token_tracker,
    ))
    graph.add_node("audit_writer", _make_audit_node(audit_writer, policy_engine, verifier, event_manager))

    graph.set_entry_point("cover_letter_agent")
    graph.add_edge("cover_letter_agent", "audit_writer")
    graph.add_edge("audit_writer", END)

    return graph
