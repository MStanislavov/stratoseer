"""Audit business logic: audit trail, verifier report, replay, diff."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.audit_writer import AuditWriter
from app.engine.diff import DiffEngine
from app.engine.replay import ReplayEngine
from app.models.run import Run

_NO_AUDIT_BUNDLE = "No audit bundle found for this run"


async def _get_run_or_raise(db: AsyncSession, run_id: str, profile_id: str) -> Run:
    """Fetch a run and verify it belongs to the given profile.

    Raises LookupError if not found.
    """
    run = await db.get(Run, run_id)
    if run is None or run.profile_id != profile_id:
        raise LookupError("Run not found")
    return run


async def get_audit_trail(db: AsyncSession, profile_id: str, run_id: str) -> dict:
    """Return the full audit event log for a run."""
    await _get_run_or_raise(db, run_id, profile_id)
    writer = AuditWriter()
    events = await writer.read_log(run_id)
    return {"run_id": run_id, "events": events}


async def get_verifier_report(db: AsyncSession, profile_id: str, run_id: str) -> dict:
    """Return the verifier report from the run bundle.

    Raises LookupError if run or bundle not found.
    """
    await _get_run_or_raise(db, run_id, profile_id)
    writer = AuditWriter()
    bundle = await writer.read_bundle(run_id)
    if bundle is None:
        raise LookupError(_NO_AUDIT_BUNDLE)
    return bundle.get("verifier_report", {})


async def replay_run(db: AsyncSession, profile_id: str, run_id: str, mode: str) -> dict:
    """Replay a previous run in strict or refresh mode.

    Raises LookupError if run or bundle not found, ValueError on other errors.
    """
    await _get_run_or_raise(db, run_id, profile_id)
    writer = AuditWriter()
    replay_engine = ReplayEngine(audit_writer=writer)

    new_run_id = str(uuid.uuid4())

    if mode == "strict":
        result = await replay_engine.replay_strict(
            original_run_id=run_id,
            new_run_id=new_run_id,
        )
    else:
        bundle = await writer.read_bundle(run_id)
        if bundle is None:
            raise LookupError(_NO_AUDIT_BUNDLE)
        new_result = bundle.get("final_artifacts", {})
        result = await replay_engine.replay_refresh(
            original_run_id=run_id,
            new_run_id=new_run_id,
            new_result=new_result,
        )

    # Persist the replay bundle
    await writer.create_run_bundle(
        run_id=new_run_id,
        profile_hash=profile_id,
        policy_version_hash="",
        verifier_report=result.get("verifier_report", {}),
        final_artifacts=result.get("result", {}),
    )

    return result


async def get_executive_insights(db: AsyncSession, profile_id: str, run_id: str) -> dict:
    """Return CEO/CFO insights from a weekly run's audit bundle.

    Raises LookupError if run or bundle not found.
    """
    await _get_run_or_raise(db, run_id, profile_id)
    writer = AuditWriter()
    bundle = await writer.read_bundle(run_id)
    if bundle is None:
        raise LookupError(_NO_AUDIT_BUNDLE)
    artifacts = bundle.get("final_artifacts", {})
    return {
        "strategic_recommendations": artifacts.get("strategic_recommendations", []),
        "ceo_summary": artifacts.get("ceo_summary", ""),
        "risk_assessments": artifacts.get("risk_assessments", []),
        "cfo_summary": artifacts.get("cfo_summary", ""),
    }


async def get_token_usage(db: AsyncSession, profile_id: str, run_id: str) -> dict:
    """Return per-agent token usage for a run.

    Reads the audit log and extracts the token_usage_summary event.
    Raises LookupError if run not found or no usage data recorded.
    """
    await _get_run_or_raise(db, run_id, profile_id)
    writer = AuditWriter()
    events = await writer.read_log(run_id)
    for event in reversed(events):
        if event.get("event_type") == "token_usage_summary":
            return event.get("data", {})
    raise LookupError("No token usage data found for this run")


async def diff_runs(db: AsyncSession, profile_id: str, run_id: str, other_run_id: str) -> dict:
    """Return a structured diff between two runs.

    Raises LookupError if either run not found.
    """
    await _get_run_or_raise(db, run_id, profile_id)
    await _get_run_or_raise(db, other_run_id, profile_id)
    writer = AuditWriter()
    diff_engine = DiffEngine(audit_writer=writer)
    return await diff_engine.diff_runs(run_id, other_run_id)
