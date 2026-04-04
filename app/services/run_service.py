"""Run business logic: execution, result persistence, task management."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from typing import Any

from app.llm.search_tool import SafeDuckDuckGoSearchTool
from langchain_openai import ChatOpenAI
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.factory import AgentFactory, AgentModelConfig
from app.config import settings
from app.db import async_session_factory
from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine
from app.graphs.cover_letter import build_cover_letter_graph
from app.graphs.daily import build_daily_graph
from app.graphs.weekly import build_weekly_graph
from app.llm.prompt_loader import PromptLoader
from app.models.certification import Certification
from app.models.course import Course
from app.models.cover_letter import CoverLetter
from app.models.event import Event
from app.models.group import Group
from app.models.job_opportunity import JobOpportunity
from app.models.trend import Trend
from app.models.profile import UserProfile
from app.models.run import Run
from app.schemas.run import RunCreate, RunRead
from app.sse import event_manager

logger = logging.getLogger(__name__)

# In-memory store for background tasks (for cancellation)
_running_tasks: dict[str, asyncio.Task] = {}

_agent_factory: Any = None


def run_to_read(run: Run) -> RunRead:
    """Convert a Run ORM instance to a RunRead schema."""
    return RunRead(
        id=run.id,
        profile_id=run.profile_id,
        mode=run.mode,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        verifier_status=run.verifier_status,
        audit_path=run.audit_path,
    )




def get_agent_factory() -> Any:
    """Return a shared AgentFactory singleton, created on the first call."""
    global _agent_factory
    if _agent_factory is not None:
        return _agent_factory

    prompt_loader = PromptLoader(settings.prompts_dir)

    agent_models = AgentModelConfig(
        goal_extractor=settings.goal_extractor_model,
        web_scraper=settings.web_scraper_model,
        data_formatter=settings.data_formatter_model,
        ceo=settings.ceo_model,
        cfo=settings.cfo_model,
        cover_letter=settings.cover_letter_model,
    )

    if not settings.api_key:
        raise RuntimeError("API_KEY is required. Set it in your .env file.")

    llm = ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.api_key,
    )

    search_tool = None
    try:
        search_tool = SafeDuckDuckGoSearchTool(timelimit="m")
    except ImportError:
        logger.warning("duckduckgo-search not installed, web scraper search tool unavailable")

    _agent_factory = AgentFactory(
        llm=llm,
        prompt_loader=prompt_loader,
        search_tool=search_tool,
        agent_models=agent_models,
    )
    return _agent_factory


def _parse_profile_targets(profile: UserProfile | None) -> list[str]:
    """Extract the target list from a UserProfile's JSON/CSV targets field."""
    if not profile or not profile.targets:
        return []
    raw: str = str(profile.targets)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return [parsed]
    except (ValueError, TypeError):
        pass
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_profile_skills(profile: UserProfile | None) -> list[str]:
    """Extract the skill list from a UserProfile's JSON/CSV skills field."""
    if not profile or not profile.skills:
        return []
    raw: str = str(profile.skills)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return [parsed]
    except (ValueError, TypeError):
        pass
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_profile_constraints(profile: UserProfile | None) -> list[str]:
    """Extract the constraint list from a UserProfile's JSON/CSV constraints field."""
    if not profile or not profile.constraints:
        return []
    raw: str = str(profile.constraints)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return [parsed]
    except (ValueError, TypeError):
        pass
    return [c.strip() for c in raw.split(",") if c.strip()]


def _build_graph(
    mode: str,
    policy_engine: Any,
    audit_writer: Any,
    agent_factory: Any,
    verifier: Any = None,
    run_event_manager: Any = None,
) -> Any:
    """Build the appropriate LangGraph StateGraph for the given run mode."""
    builders = {
        "weekly": build_weekly_graph,
        "cover_letter": build_cover_letter_graph,
    }
    builder = builders.get(mode, build_daily_graph)
    return builder(
        policy_engine=policy_engine,
        audit_writer=audit_writer,
        agent_factory=agent_factory,
        verifier=verifier,
        event_manager=run_event_manager,
    )


async def _update_run_status(run_id: str, status: str, **extra: Any) -> None:
    """Set a run's status and finished_at timestamp in the DB."""
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run:
            run.status = status
            run.finished_at = datetime.now(timezone.utc)
            for key, value in extra.items():
                setattr(run, key, value)
            await session.commit()


async def _start_run(run_id: str) -> bool:
    """Mark run as running. Returns False if the run no longer exists."""
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return False
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await session.commit()
    return True


async def _load_profile(profile_id: str) -> dict[str, Any]:
    """Load all profile fields needed by the pipeline from the DB."""
    async with async_session_factory() as session:
        profile = await session.get(UserProfile, profile_id)
        cv_summary = ""
        if profile and profile.cv_path:
            cv_summary = _read_cv_text(profile.cv_path)
        return {
            "profile_targets": _parse_profile_targets(profile),
            "profile_skills": _parse_profile_skills(profile),
            "profile_constraints": _parse_profile_constraints(profile),
            "cv_summary": cv_summary,
            # Structured profile fields
            "preferred_titles": _parse_json_list(profile, "preferred_titles"),
            "experience_level": getattr(profile, "experience_level", "") or "",
            "industries": _parse_json_list(profile, "industries"),
            "locations": _parse_json_list(profile, "locations"),
            "work_arrangement": getattr(profile, "work_arrangement", "") or "",
            "event_attendance": getattr(profile, "event_attendance", "") or "",
            "target_certifications": _parse_json_list(profile, "target_certifications"),
            "learning_format": getattr(profile, "learning_format", "") or "",
        }


def _parse_json_list(profile: UserProfile | None, field: str) -> list[str]:
    """Parse a JSON-encoded list field from the profile, returning [] if absent."""
    if not profile:
        return []
    raw = getattr(profile, field, None)
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            return parsed
    except (ValueError, TypeError):
        pass
    return []


def _read_cv_text(cv_path: str) -> str:
    """Read CV content from file. Returns empty string on failure."""
    from pathlib import Path

    path = Path(cv_path)
    if not path.exists():
        return ""
    try:
        if path.suffix.lower() == ".pdf":
            from app.services.profile_service import extract_text_from_pdf

            return extract_text_from_pdf(cv_path)
        return path.read_text("utf-8")
    except Exception:
        logger.warning("Failed to read CV at %s", cv_path)
        return ""


async def persist_results(
    run_id: str, profile_id: str, result: dict[str, Any]
) -> None:
    """Save the 5 DTO types from the pipeline result to the database."""
    async with async_session_factory() as session:
        for job in result.get("formatted_jobs", []):
            session.add(JobOpportunity(
                profile_id=profile_id, run_id=run_id,
                title=job.get("title", "Untitled"),
                company=job.get("company"),
                url=job.get("url"),
                description=job.get("description"),
                location=job.get("location"),
                salary_range=job.get("salary_range"),
                source_query=job.get("source_query"),
            ))
        for cert in result.get("formatted_certifications", []):
            session.add(Certification(
                profile_id=profile_id, run_id=run_id,
                title=cert.get("title", "Untitled"),
                provider=cert.get("provider"),
                url=cert.get("url"),
                description=cert.get("description"),
                cost=cert.get("cost"),
                duration=cert.get("duration"),
            ))
        for course in result.get("formatted_courses", []):
            session.add(Course(
                profile_id=profile_id, run_id=run_id,
                title=course.get("title", "Untitled"),
                platform=course.get("platform"),
                url=course.get("url"),
                description=course.get("description"),
                cost=course.get("cost"),
                duration=course.get("duration"),
            ))
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for event in result.get("formatted_events", []):
            event_date = event.get("event_date")
            if event_date and event_date < today_str:
                logger.info("Skipping past event %s (date=%s)", event.get("title"), event_date)
                continue
            session.add(Event(
                profile_id=profile_id, run_id=run_id,
                title=event.get("title", "Untitled"),
                organizer=event.get("organizer"),
                url=event.get("url"),
                description=event.get("description"),
                event_date=event_date,
                location=event.get("location"),
            ))
        for group in result.get("formatted_groups", []):
            session.add(Group(
                profile_id=profile_id, run_id=run_id,
                title=group.get("title", "Untitled"),
                platform=group.get("platform"),
                url=group.get("url"),
                description=group.get("description"),
                member_count=group.get("member_count"),
            ))
        for trend in result.get("formatted_trends", []):
            session.add(Trend(
                profile_id=profile_id, run_id=run_id,
                title=trend.get("title", "Untitled"),
                category=trend.get("category"),
                url=trend.get("url"),
                description=trend.get("description"),
                relevance=trend.get("relevance"),
                source=trend.get("source"),
            ))
        await session.commit()


async def execute_run(run_id: str, profile_id: str, mode: str) -> None:
    """Background task that executes the LangGraph pipeline."""
    try:
        if not await _start_run(run_id):
            return

        profile_data = await _load_profile(profile_id)
        logger.info(
            "Run %s started (mode=%s, profile=%s, targets=%s, constraints=%s)",
            run_id, mode, profile_id, profile_data["profile_targets"], profile_data["profile_constraints"],
        )

        await event_manager.publish(run_id, {
            "type": "run_started",
            "run_id": run_id,
            "mode": mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        policy_engine = PolicyEngine(settings.policy_dir)
        audit_writer = AuditWriter(
            artifacts_dir=settings.artifacts_dir, policy_engine=policy_engine
        )
        await audit_writer.append(
            run_id,
            AuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type="agent_start",
                agent=f"{mode}_pipeline",
                data={"mode": mode, "profile_id": profile_id},
            ),
        )

        from app.engine.verifier import Verifier
        verifier = Verifier(policy_engine=policy_engine)

        agent_factory = get_agent_factory()
        graph = _build_graph(
            mode, policy_engine, audit_writer, agent_factory,
            verifier=verifier, run_event_manager=event_manager,
        )
        compiled = graph.compile()

        initial_state = {
            "profile_id": profile_id,
            **profile_data,
            "run_id": run_id,
            "errors": [],
            "safe_degradation": False,
            "audit_events": [],
        }
        t0 = time.monotonic()
        result = await compiled.ainvoke(initial_state)
        elapsed = time.monotonic() - t0

        # Persist results to DB
        await persist_results(run_id, profile_id, result)

        errors = result.get("errors", [])
        logger.info(
            "Run %s completed in %.2fs (errors=%d)",
            run_id, elapsed, len(errors),
        )
        if errors:
            logger.warning("Run %s had errors: %s", run_id, errors)

        # Derive verifier status from accumulated results
        verifier_results = result.get("verifier_results", [])
        verifier_status = "pass"
        if any(vr.get("status") == "fail" for vr in verifier_results):
            verifier_status = "fail"
        elif any(vr.get("status") == "partial" for vr in verifier_results):
            verifier_status = "partial"

        await _update_run_status(
            run_id, "completed",
            audit_path=str(settings.artifacts_dir / "runs" / run_id),
            verifier_status=verifier_status,
        )
        await event_manager.publish(run_id, {
            "type": "run_finished",
            "run_id": run_id,
            "status": "completed",
            "verifier_status": verifier_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except asyncio.CancelledError:
        logger.info("Run %s cancelled", run_id)
        await _update_run_status(run_id, "cancelled")
        await event_manager.publish(run_id, {
            "type": "run_cancelled",
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raise

    except Exception as exc:
        logger.error("Run %s failed: %s", run_id, exc, exc_info=True)
        await _update_run_status(run_id, "failed")
        await event_manager.publish(run_id, {
            "type": "run_failed",
            "run_id": run_id,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    finally:
        await event_manager.close(run_id)
        _ = _running_tasks.pop(run_id, None)


# ------------------------------------------------------------------
# Service functions called by the router
# ------------------------------------------------------------------


async def list_all_runs(db: AsyncSession, limit: int = 10) -> list[RunRead]:
    """List recent runs across all profiles."""
    result = await db.execute(
        select(Run).order_by(Run.created_at.desc()).limit(limit)
    )
    return [run_to_read(r) for r in result.scalars().all()]


async def create_run(
    db: AsyncSession, profile_id: str, body: RunCreate
) -> RunRead:
    """Create a run record and launch the pipeline in the background.

    Raises LookupError if the profile does not exist.
    """
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        raise LookupError("Profile not found")

    # Validate profile completeness
    missing: list[str] = []
    parsed_targets = _parse_profile_targets(profile)
    parsed_skills = _parse_profile_skills(profile)
    parsed_titles = _parse_json_list(profile, "preferred_titles")
    if not parsed_targets:
        missing.append("targets")
    if not parsed_skills:
        missing.append("skills")
    if not parsed_titles:
        missing.append("preferred job titles")
    if not profile.cv_path:
        missing.append("a CV")
    if missing:
        raise ValueError(f"Profile is incomplete: please add {', '.join(missing)}")

    run = Run(
        profile_id=profile_id,
        mode=body.mode,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    task = asyncio.create_task(
        execute_run(run.id, profile_id, body.mode)
    )
    _running_tasks[run.id] = task

    return run_to_read(run)


async def list_runs(db: AsyncSession, profile_id: str) -> list[RunRead]:
    """List all runs for a profile, most recent first."""
    result = await db.execute(
        select(Run)
        .where(Run.profile_id == profile_id)
        .order_by(Run.created_at.desc())
    )
    runs = result.scalars().all()
    return [run_to_read(r) for r in runs]


async def get_run(
    db: AsyncSession, profile_id: str, run_id: str
) -> RunRead | None:
    """Return RunRead or None if not found / wrong profile."""
    run = await db.get(Run, run_id)
    if run is None or run.profile_id != profile_id:
        return None
    return run_to_read(run)


async def cancel_run(
    db: AsyncSession, profile_id: str, run_id: str
) -> dict:
    """Cancel a running task.

    Raises LookupError if run not found, ValueError if not running.
    """
    run = await db.get(Run, run_id)
    if run is None or run.profile_id != profile_id:
        raise LookupError("Run not found")

    task = _running_tasks.get(run_id)
    if task is None or task.done():
        raise ValueError("Run is not currently executing")

    task.cancel()
    return {"detail": "Cancellation requested", "run_id": run_id}


async def delete_run(db: AsyncSession, profile_id: str, run_id: str) -> bool:
    """Delete a run and all its associated results.

    Deletes cover letters from this run, unlinks cover letters from other runs
    that reference jobs produced by this run, then deletes all result rows and
    the run itself.

    Raises LookupError if the run is not found.
    Raises ValueError if the run is still executing.
    """
    run = await db.get(Run, run_id)
    if run is None or run.profile_id != profile_id:
        raise LookupError("Run not found")

    task = _running_tasks.get(run_id)
    if task is not None and not task.done():
        raise ValueError("Cannot delete a run that is still executing")

    # 1) Delete cover letters that belong to this run
    await db.execute(
        delete(CoverLetter).where(CoverLetter.run_id == run_id)
    )

    # 2) Unlink cover letters from other runs that reference jobs from this run
    await db.execute(
        update(CoverLetter)
        .where(CoverLetter.job_opportunity_id.in_(
            select(JobOpportunity.id).where(JobOpportunity.run_id == run_id)
        ))
        .values(job_opportunity_id=None)
    )

    # 3) Delete all result types for this run
    for model in (JobOpportunity, Certification, Course, Event, Group, Trend):
        await db.execute(delete(model).where(model.run_id == run_id))

    # 4) Delete the run
    await db.delete(run)
    await db.commit()

    # 5) Clean up audit artifacts from disk (in thread to avoid blocking)
    def _cleanup() -> None:
        run_dir = settings.artifacts_dir / "runs" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

    await asyncio.to_thread(_cleanup)
    return True
