"""Cover letter business logic: generation, resolution, persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory
from app.engine.audit_writer import AuditEvent, AuditWriter
from app.engine.policy_engine import PolicyEngine
from app.graphs.cover_letter import build_cover_letter_graph
from app.models.cover_letter import CoverLetter
from app.models.job_opportunity import JobOpportunity
from app.models.profile import UserProfile
from app.models.run import Run
from app.models.user import User
from app.schemas.cover_letter import CoverLetterCreate, CoverLetterRead
from app.services.api_key_service import get_user_api_key
from app.services.run_service import (
    _parse_profile_constraints,
    _parse_profile_skills,
    _parse_profile_targets,
    create_agent_factory,
)
from app.sse import event_manager

# Prevent background tasks from being garbage-collected
_background_tasks: set[asyncio.Task] = set()


def cl_to_read(cl: CoverLetter, job: JobOpportunity | None = None) -> CoverLetterRead:
    """Convert a CoverLetter ORM instance to a CoverLetterRead schema."""
    return CoverLetterRead(
        id=cl.id,
        profile_id=cl.profile_id,
        job_opportunity_id=cl.job_opportunity_id,
        run_id=cl.run_id,
        content=cl.content,
        created_at=cl.created_at,
        job_title=job.title if job else None,
        job_company=job.company if job else None,
        job_url=job.url if job else None,
    )


async def resolve_job_opportunity(
    db: AsyncSession,
    job_opportunity_id: str | None,
    profile_id: str,
    jd_text: str,
) -> tuple[dict, str, JobOpportunity | None]:
    """Resolve job opportunity details and JD text from a job opportunity ID.

    Returns (job_dict, jd_text, job_orm_or_None).
    Raises LookupError if job_opportunity_id is given but not found.
    """
    job_opportunity: dict = {}
    if not job_opportunity_id:
        return job_opportunity, jd_text, None
    job = await db.get(JobOpportunity, job_opportunity_id)
    if job is None or job.profile_id != profile_id:
        raise LookupError("Job opportunity not found")
    job_opportunity = {
        "title": job.title,
        "company": job.company,
        "url": job.url,
        "description": job.description,
    }
    if not jd_text:
        jd_text = job.description or job.title
    return job_opportunity, jd_text, job


async def read_cv_content(cv_data: bytes | None, skills_fallback: str = "") -> str:
    """Extract text from CV bytes (PDF) or fall back to skills."""
    if cv_data:
        try:
            from app.services.profile_service import extract_text_from_pdf

            return await asyncio.to_thread(extract_text_from_pdf, cv_data)
        except Exception:
            pass
    return skills_fallback


async def summarize_cv(raw_cv_content: str, api_key: str) -> str:
    """Summarize CV content using LLM if available, otherwise return raw."""
    if not raw_cv_content:
        return raw_cv_content
    factory = create_agent_factory(api_key)
    from app.llm.prompt_loader import PromptLoader

    prompt_loader = PromptLoader(settings.prompts_dir)
    system_prompt = prompt_loader.load("cv_summarizer")
    llm = factory._llm
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_cv_content},
    ]
    response = await llm.ainvoke(messages)
    return response.content


async def generate_cover_letter(
    run_id: str,
    profile_id: str,
    cover_letter_id: str,
    jd_text: str,
    job_opportunity: dict,
    job_opportunity_id: str | None,
    api_key: str,
    profile_name: str = "",
    profile_targets: list[str] | None = None,
    profile_skills: list[str] | None = None,
    profile_constraints: list[str] | None = None,
) -> None:
    """Background task: run the cover letter LangGraph pipeline and persist a result."""
    try:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            if run:
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                await session.commit()

        await event_manager.publish(
            run_id,
            {
                "type": "run_started",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Load profile and use cached CV summary (or generate on demand)
        async with async_session_factory() as session:
            profile = await session.get(UserProfile, profile_id)
            from app.services.profile_service import ensure_cv_summary

            cv_content = await ensure_cv_summary(session, profile) if profile else ""

            # Extract candidate name from raw CV text (cheap, no LLM)
            raw_cv_content = await read_cv_content(
                profile.cv_data if profile else None,
                profile.skills or "",
            )

        from app.agents.cover_letter_agent import _extract_name_from_cv

        candidate_name = _extract_name_from_cv(raw_cv_content)
        if candidate_name:
            profile_name = candidate_name

        policy_engine = PolicyEngine(settings.policy_dir)
        audit_writer = AuditWriter(policy_engine=policy_engine)

        await audit_writer.append(
            run_id,
            AuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type="agent_start",
                agent="cover_letter_pipeline",
                data={"profile_id": profile_id, "job_opportunity_id": job_opportunity_id},
            ),
        )

        from app.engine.verifier import Verifier

        verifier = Verifier(policy_engine=policy_engine)

        graph = build_cover_letter_graph(
            policy_engine=policy_engine,
            audit_writer=audit_writer,
            agent_factory=create_agent_factory(api_key),
            verifier=verifier,
            event_manager=event_manager,
        )
        compiled = graph.compile()

        initial_state = {
            "profile_id": profile_id,
            "profile_name": profile_name,
            "profile_targets": profile_targets or [],
            "profile_skills": profile_skills or [],
            "profile_constraints": profile_constraints or [],
            "cv_content": cv_content,
            "jd_text": jd_text,
            "job_opportunity": job_opportunity,
            "run_id": run_id,
            "errors": [],
            "audit_events": [],
        }

        result = await compiled.ainvoke(initial_state)
        content = result.get("cover_letter_content", "")

        async with async_session_factory() as session:
            cl = await session.get(CoverLetter, cover_letter_id)
            if cl:
                cl.content = content

            run = await session.get(Run, run_id)
            if run:
                run.status = "completed"
                run.finished_at = datetime.now(timezone.utc)

            await session.commit()

        await event_manager.publish(
            run_id,
            {
                "type": "run_finished",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        print(e)
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            if run:
                run.status = "failed"
                run.finished_at = datetime.now(timezone.utc)
                await session.commit()

        await event_manager.publish(
            run_id,
            {
                "type": "run_failed",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    finally:
        await event_manager.close(run_id)


async def create_cover_letter(
    db: AsyncSession, profile_id: str, body: CoverLetterCreate, user: User
) -> CoverLetterRead:
    """Create a cover letter and launch background generation.

    Raises LookupError if profile/ job is not found, ValueError if missing input.
    """
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        raise LookupError("Profile not found")

    # Use the user's own key if available, otherwise fall back to server key
    api_key = get_user_api_key(user) or settings.api_key
    if not api_key:
        raise ValueError("No API key available for cover letter generation")

    if not profile.cv_data:
        raise ValueError(
            "Profile is incomplete: please upload a CV before generating a cover letter"
        )

    if not body.job_opportunity_id and not body.jd_text:
        raise ValueError("Either job_opportunity_id or jd_text must be provided")

    jd_text = body.jd_text or ""
    job_opportunity, jd_text, job_orm = await resolve_job_opportunity(
        db, body.job_opportunity_id, profile_id, jd_text
    )

    targets = _parse_profile_targets(profile)
    skills = _parse_profile_skills(profile)
    constraints = _parse_profile_constraints(profile)

    # Create a run record
    run = Run(profile_id=profile_id, mode="cover_letter", status="pending")
    db.add(run)
    await db.flush()

    # Create a cover letter record (content filled after the pipeline runs)
    cl = CoverLetter(
        profile_id=profile_id,
        job_opportunity_id=body.job_opportunity_id,
        run_id=run.id,
        content="",
    )
    db.add(cl)
    await db.commit()
    await db.refresh(cl)
    await db.refresh(run)

    # Launch pipeline in background (uses cached CV summary or generates on demand)
    task = asyncio.create_task(
        generate_cover_letter(
            run_id=run.id,
            profile_id=profile_id,
            cover_letter_id=cl.id,
            jd_text=jd_text,
            job_opportunity=job_opportunity,
            job_opportunity_id=body.job_opportunity_id,
            api_key=api_key,
            profile_name=profile.name,
            profile_targets=targets,
            profile_skills=skills,
            profile_constraints=constraints,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return cl_to_read(cl, job_orm)


async def list_cover_letters(db: AsyncSession, profile_id: str) -> list[CoverLetterRead]:
    """List all cover letters for a profile, with job details."""
    result = await db.execute(
        select(CoverLetter, JobOpportunity)
        .outerjoin(
            JobOpportunity,
            CoverLetter.job_opportunity_id == JobOpportunity.id,
        )
        .where(CoverLetter.profile_id == profile_id)
        .order_by(CoverLetter.created_at.desc())
    )
    return [cl_to_read(cl, job) for cl, job in result.all()]


async def get_cover_letter(
    db: AsyncSession, profile_id: str, letter_id: str
) -> CoverLetterRead | None:
    """Return CoverLetterRead or None if not found."""
    result = await db.execute(
        select(CoverLetter, JobOpportunity)
        .outerjoin(
            JobOpportunity,
            CoverLetter.job_opportunity_id == JobOpportunity.id,
        )
        .where(CoverLetter.id == letter_id, CoverLetter.profile_id == profile_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    cl, job = row
    return cl_to_read(cl, job)


async def delete_cover_letter(db: AsyncSession, profile_id: str, letter_id: str) -> bool:
    """Delete a cover letter. Returns True if deleted, False if not found."""
    cl = await db.get(CoverLetter, letter_id)
    if cl is None or cl.profile_id != profile_id:
        return False
    await db.delete(cl)
    await db.commit()
    return True
