"""Unified pipeline logging helpers and shared node factories.

All pipeline-internal logs use DEBUG level, so they only appear when
the caller (or root logger) is configured at DEBUG.  Warnings (e.g.,
safe degradation, verifier errors) use WARNING.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Generator

from app.agents.base import AgentProtocol
from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine
from app.engine.token_tracker import RunTokenTracker
from app.engine.verifier import Verifier

logger = logging.getLogger("app.graphs.pipeline")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@contextmanager
def _timed() -> Generator[dict[str, float], None, None]:
    ctx: dict[str, float] = {"start": time.monotonic()}
    yield ctx
    ctx["elapsed"] = time.monotonic() - ctx["start"]


def _rid(state: dict[str, Any]) -> str:
    return state.get("run_id", "?")


def node_start(pipeline: str, state: dict[str, Any], node: str, **kw: Any) -> None:
    """Log the start of a graph node execution at DEBUG level."""
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    logger.debug("[%s:%s] %s -> start %s", pipeline, _rid(state), node, extra)


def node_end(pipeline: str, state: dict[str, Any], node: str, elapsed: float, **kw: Any) -> None:
    """Log the completion of a graph node execution with elapsed time."""
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    logger.debug("[%s:%s] %s -> done %.2fs %s", pipeline, _rid(state), node, elapsed, extra)


def agent_result(
    pipeline: str, state: dict[str, Any], agent_name: str, elapsed: float, **kw: Any
) -> None:
    """Log an individual agent's return with elapsed time."""
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    logger.debug("[%s:%s]   %s returned %.2fs %s", pipeline, _rid(state), agent_name, elapsed, extra)


def route(pipeline: str, state: dict[str, Any], dest: str, **kw: Any) -> None:
    """Log a conditional routing decision at DEBUG level."""
    extra = " ".join(f"{k}={v}" for k, v in kw.items())
    logger.debug("[%s:%s] route -> %s %s", pipeline, _rid(state), dest, extra)


def warn(pipeline: str, state: dict[str, Any], msg: str) -> None:
    """Log a pipeline warning (e.g. safe degradation)."""
    logger.warning("[%s:%s] %s", pipeline, _rid(state), msg)


# ------------------------------------------------------------------
# Shared async agent caller
# ------------------------------------------------------------------


async def call_agent(agent: AgentProtocol, state: dict[str, Any]) -> dict[str, Any]:
    """Call an agent, running sync agents in a thread to avoid blocking the event loop."""
    if asyncio.iscoroutinefunction(agent) or asyncio.iscoroutinefunction(
        getattr(agent, "__call__", None)
    ):
        return await agent(state)
    return await asyncio.to_thread(agent, state)


# ------------------------------------------------------------------
# Policy check (shared across all graphs)
# ------------------------------------------------------------------


def check_tool(policy_engine: PolicyEngine | None, agent_name: str, tool: str) -> None:
    """Raise if the policy engine denies this tool for the agent."""
    if policy_engine is None:
        return
    if not policy_engine.is_tool_allowed(agent_name, tool):
        raise PermissionError(
            f"Policy violation: agent '{agent_name}' is not allowed tool '{tool}'"
        )


# ------------------------------------------------------------------
# SSE helper (lazy import to avoid circular dependency)
# ------------------------------------------------------------------


async def _publish_sse(
    event_manager: Any | None,
    run_id: str,
    event: dict[str, Any],
) -> None:
    if event_manager is not None:
        await event_manager.publish(run_id, event)


# ------------------------------------------------------------------
# make_node: shared single-agent node factory
# ------------------------------------------------------------------


def make_node(
    pipeline: str,
    agent_name: str,
    agent: AgentProtocol,
    tool_name: str,
    policy_engine: PolicyEngine | None = None,
    audit_writer: AuditWriter | None = None,
    verifier: Verifier | None = None,
    event_manager: Any | None = None,
    node_type: str = "agent",
    token_tracker: RunTokenTracker | None = None,
) -> Callable[..., Any]:
    """Create a graph node that runs a single agent with full lifecycle:

    1. Policy tool check
    2. SSE ``agent_started`` event
    3. Audit ``agent_start`` event
    4. Execute agent
    5. Verify output
    6. Audit ``agent_end`` + ``verifier_result`` events
    7. SSE ``agent_completed`` event
    8. Accumulate ``verifier_results`` in state
    """

    # Derive event type prefixes from node_type
    # "agent" -> "agent_start"/"agent_end"/"agent_started"/"agent_completed"
    # "static_validator" -> "static_validator_start"/"static_validator_end"/...
    evt_start = f"{node_type}_start"
    evt_end = f"{node_type}_end"
    sse_started = f"{node_type}_started"
    sse_completed = f"{node_type}_completed"

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        check_tool(policy_engine, agent_name, tool_name)
        run_id = state.get("run_id", "unknown")
        now = datetime.now(timezone.utc).isoformat

        # SSE: started
        await _publish_sse(event_manager, run_id, {
            "type": sse_started,
            "agent": agent_name,
            "node_type": node_type,
            "timestamp": now(),
        })

        node_start(pipeline, state, agent_name)

        # Audit: start
        if audit_writer:
            await audit_writer.append(run_id, AuditEvent(
                timestamp=now(),
                event_type=evt_start,
                agent=agent_name,
                node_type=node_type,
            ))

        t0 = time.monotonic()
        result = await call_agent(agent, state)
        elapsed = time.monotonic() - t0

        # Extract and record token usage
        for usage in result.pop("_token_usage", []):
            if token_tracker and usage:
                await token_tracker.record(
                    agent_name,
                    usage.get("model_name", ""),
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                )

        node_end(pipeline, state, agent_name, elapsed)

        # Verify
        verification_dict: dict[str, Any] = {}
        verification_status = "pass"
        if verifier:
            verification = verifier.verify(agent_name, result)
            verification_status = verification.status.value
            verification_dict = {
                "agent_name": verification.agent_name,
                "status": verification.status.value,
                "checks": [
                    {
                        "check_name": c.check_name,
                        "status": c.status.value,
                        "message": c.message,
                    }
                    for c in verification.checks
                ],
                "timestamp": verification.timestamp,
            }

        # Audit: end
        if audit_writer:
            await audit_writer.append(run_id, AuditEvent(
                timestamp=now(),
                event_type=evt_end,
                agent=agent_name,
                node_type=node_type,
                data=result,
            ))
            if verification_dict:
                await audit_writer.append(run_id, AuditEvent(
                    timestamp=now(),
                    event_type="verifier_result",
                    agent=agent_name,
                    node_type=node_type,
                    data=verification_dict,
                ))

        # SSE: completed
        await _publish_sse(event_manager, run_id, {
            "type": sse_completed,
            "agent": agent_name,
            "node_type": node_type,
            "verification_status": verification_status,
            "elapsed": round(elapsed, 2),
            "timestamp": now(),
        })

        # Accumulate verifier results
        if verification_dict:
            prev = list(state.get("verifier_results", []))
            prev.append(verification_dict)
            result["verifier_results"] = prev

        return result

    return _node


# ------------------------------------------------------------------
# make_fan_out_node: shared multi-scraper node factory
# ------------------------------------------------------------------


def make_fan_out_node(
    pipeline: str,
    agent_name: str,
    scraper: AgentProtocol,
    tool_name: str,
    categories: list[tuple[str, str]],
    policy_engine: PolicyEngine | None = None,
    audit_writer: AuditWriter | None = None,
    verifier: Verifier | None = None,
    event_manager: Any | None = None,
    scraper_overrides: dict[str, AgentProtocol] | None = None,
    token_tracker: RunTokenTracker | None = None,
) -> Callable[..., Any]:
    """Create a fan-out node that runs scrapers concurrently, then verifies the merged output.

    Use ``scraper_overrides`` to substitute a different callable for specific
    categories (e.g. a validated job scraper wrapper for the ``"job"`` category).
    """

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        check_tool(policy_engine, agent_name, tool_name)
        run_id = state.get("run_id", "unknown")
        prompts = state.get("search_prompts", {})
        now = datetime.now(timezone.utc).isoformat

        # SSE: agent started
        await _publish_sse(event_manager, run_id, {
            "type": "agent_started",
            "agent": agent_name,
            "timestamp": now(),
        })

        node_start(pipeline, state, agent_name, prompts=len(prompts))

        # Audit: agent start
        if audit_writer:
            await audit_writer.append(run_id, AuditEvent(
                timestamp=now(),
                event_type="agent_start",
                agent=agent_name,
                data={"prompts": prompts},
            ))

        t0 = time.monotonic()

        async def _run_scraper(category: str, prompt_key: str) -> dict[str, Any]:
            agent = (scraper_overrides or {}).get(category, scraper)
            search_state = {
                **state,
                "search_prompt": prompts.get(prompt_key, ""),
                "search_category": category,
            }
            return await call_agent(agent, search_state)

        returns = await asyncio.gather(
            *[_run_scraper(cat, pk) for cat, pk in categories]
        )

        all_errors: list[str] = []
        results: dict[str, Any] = {}
        for (category, _), ret in zip(categories, returns):
            # Extract and record token usage from each scraper
            for usage in ret.pop("_token_usage", []):
                if token_tracker and usage:
                    await token_tracker.record(
                        f"{agent_name}/{category}",
                        usage.get("model_name", ""),
                        usage.get("input_tokens", 0),
                        usage.get("output_tokens", 0),
                    )
            result_key = f"raw_{category}_results"
            results[result_key] = ret.get(result_key, [])
            filtered_key = f"filtered_{category}_urls"
            if ret.get(filtered_key):
                results[filtered_key] = ret[filtered_key]
            all_errors.extend(ret.get("errors", []))

        elapsed = time.monotonic() - t0

        node_end(
            pipeline, state, agent_name, elapsed,
            **{cat: len(results.get(f"raw_{cat}_results", [])) for cat, _ in categories},
        )

        # Verify merged output
        verification_dict: dict[str, Any] = {}
        verification_status = "pass"
        if verifier:
            verification = verifier.verify(agent_name, results)
            verification_status = verification.status.value
            verification_dict = {
                "agent_name": verification.agent_name,
                "status": verification.status.value,
                "checks": [
                    {
                        "check_name": c.check_name,
                        "status": c.status.value,
                        "message": c.message,
                    }
                    for c in verification.checks
                ],
                "timestamp": verification.timestamp,
            }

        # Audit: agent end
        if audit_writer:
            await audit_writer.append(run_id, AuditEvent(
                timestamp=now(),
                event_type="agent_end",
                agent=agent_name,
                data=results,
            ))
            if verification_dict:
                await audit_writer.append(run_id, AuditEvent(
                    timestamp=now(),
                    event_type="verifier_result",
                    agent=agent_name,
                    data=verification_dict,
                ))

        # SSE: agent completed
        await _publish_sse(event_manager, run_id, {
            "type": "agent_completed",
            "agent": agent_name,
            "verification_status": verification_status,
            "elapsed": round(elapsed, 2),
            "timestamp": now(),
        })

        # Accumulate verifier results
        merged = {
            **results,
            "errors": state.get("errors", []) + all_errors,
        }
        if verification_dict:
            prev = list(state.get("verifier_results", []))
            prev.append(verification_dict)
            merged["verifier_results"] = prev

        return merged

    return _node
