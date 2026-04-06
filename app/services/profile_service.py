"""Profile business logic: CRUD, CV upload, skill extraction."""

import asyncio
import hashlib
import io
import json
import logging
import shutil
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory
from app.models.certification import Certification
from app.models.course import Course
from app.models.cover_letter import CoverLetter
from app.models.event import Event
from app.models.group import Group
from app.models.job_opportunity import JobOpportunity
from app.models.profile import UserProfile
from app.models.run import Run
from app.models.trend import Trend
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate

logger = logging.getLogger(__name__)

# Prevent background tasks from being garbage-collected
_background_tasks: set[asyncio.Task] = set()


class ExtractedSkills(BaseModel):
    """Response model containing a list of extracted skills."""

    skills: list[str]


def _serialize_list(value: list[str] | None) -> str | None:
    """Serialize a list to JSON string for Text column storage."""
    if value is None:
        return None
    return json.dumps(value)


def _deserialize_list(value: str | None) -> list[str] | None:
    """Deserialize a JSON string from the Text column to list."""
    if value is None:
        return None
    return json.loads(value)


def profile_to_read(profile: UserProfile) -> ProfileRead:
    """Convert an SQLAlchemy UserProfile to a ProfileRead schema."""
    return ProfileRead(
        id=profile.id,
        name=profile.name,
        targets=_deserialize_list(profile.targets),
        constraints=_deserialize_list(profile.constraints),
        skills=_deserialize_list(profile.skills),
        cv_filename=profile.cv_filename,
        has_cv_summary=bool(profile.cv_summary),
        preferred_titles=_deserialize_list(profile.preferred_titles),
        experience_level=profile.experience_level,
        industries=_deserialize_list(profile.industries),
        locations=_deserialize_list(profile.locations),
        work_arrangement=profile.work_arrangement,
        event_attendance=profile.event_attendance,
        event_topics=_deserialize_list(profile.event_topics),
        target_certifications=_deserialize_list(profile.target_certifications),
        learning_format=profile.learning_format,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def create_profile(
    db: AsyncSession, body: ProfileCreate, owner_id: str | None = None
) -> ProfileRead:
    """Create a new profile and return its read representation."""
    profile = UserProfile(
        name=body.name,
        owner_id=owner_id or "",
        targets=_serialize_list(body.targets),
        constraints=_serialize_list(body.constraints),
        skills=_serialize_list(body.skills),
        preferred_titles=_serialize_list(body.preferred_titles),
        experience_level=body.experience_level,
        industries=_serialize_list(body.industries),
        locations=_serialize_list(body.locations),
        work_arrangement=body.work_arrangement,
        event_attendance=body.event_attendance,
        event_topics=_serialize_list(body.event_topics),
        target_certifications=_serialize_list(body.target_certifications),
        learning_format=body.learning_format,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile_to_read(profile)


async def list_profiles(
    db: AsyncSession, owner_id: str | None = None
) -> list[ProfileRead]:
    """List profiles ordered by creation date. If owner_id given, filter by owner."""
    query = select(UserProfile).order_by(UserProfile.created_at)
    if owner_id is not None:
        query = query.where(UserProfile.owner_id == owner_id)
    result = await db.execute(query)
    profiles = result.scalars().all()
    return [profile_to_read(p) for p in profiles]


async def get_profile(db: AsyncSession, profile_id: str) -> ProfileRead | None:
    """Return ProfileRead or None if not found."""
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        return None
    return profile_to_read(profile)


async def update_profile(
    db: AsyncSession, profile_id: str, body: ProfileUpdate
) -> ProfileRead | None:
    """Return updated ProfileRead or None if not found."""
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        return None

    update_data = body.model_dump(exclude_unset=True)
    for field in ("targets", "constraints", "skills", "preferred_titles", "industries", "locations", "event_topics", "target_certifications"):
        if field in update_data:
            update_data[field] = _serialize_list(update_data[field])

    for key, value in update_data.items():
        setattr(profile, key, value)

    await db.commit()
    await db.refresh(profile)
    return profile_to_read(profile)


async def delete_profile(db: AsyncSession, profile_id: str) -> bool:
    """Delete profile and cascade. Returns False if not found."""
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        return False

    # Collect run IDs for this profile
    run_rows = await db.execute(
        select(Run.id).where(Run.profile_id == profile_id)
    )
    run_ids = [r for (r,) in run_rows.all()]

    # Delete in FK-safe order: cover letters first (FK -> job_opportunities),
    # then result tables (FK -> runs), then runs (FK -> user_profiles)
    await db.execute(delete(CoverLetter).where(CoverLetter.profile_id == profile_id))
    if run_ids:
        for model in (JobOpportunity, Certification, Course, Event, Group, Trend):
            await db.execute(delete(model).where(model.run_id.in_(run_ids)))
        await db.execute(delete(Run).where(Run.profile_id == profile_id))

    await db.delete(profile)
    await db.commit()

    # Clean up filesystem artifacts (run in thread to avoid blocking event loop)
    def _cleanup() -> None:
        for rid in run_ids:
            run_dir = settings.artifacts_dir / "runs" / rid
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)

    await asyncio.to_thread(_cleanup)
    return True


async def upload_cv(
    db: AsyncSession, profile_id: str, filename: str, content: bytes
) -> ProfileRead | None:
    """Store CV bytes in the database. Returns None if profile not found."""
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        return None

    profile.cv_data = content
    profile.cv_filename = filename
    profile.cv_summary = None
    profile.cv_summary_hash = None
    await db.commit()
    await db.refresh(profile)

    task = asyncio.create_task(_background_summarize(profile_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return profile_to_read(profile)


async def _background_summarize(profile_id: str) -> None:
    """Eagerly regenerate the CV summary after upload."""
    try:
        async with async_session_factory() as session:
            profile = await session.get(UserProfile, profile_id)
            if profile and profile.cv_data:
                await ensure_cv_summary(session, profile)
    except Exception:
        logger.warning(
            "Background CV summarization failed for profile %s", profile_id, exc_info=True
        )


def extract_text_from_pdf(source: str | bytes) -> str:
    """Extract text content from a PDF file path or bytes."""
    if isinstance(source, bytes):
        reader = PdfReader(io.BytesIO(source))
    else:
        reader = PdfReader(source)
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)


async def ensure_cv_summary(db: AsyncSession, profile: UserProfile) -> str:
    """Return cached CV summary, generating via LLM if missing or stale."""
    if profile.cv_data is None:
        return ""

    cv_hash = await asyncio.to_thread(
        lambda: hashlib.sha256(profile.cv_data).hexdigest()
    )

    if profile.cv_summary is not None and profile.cv_summary_hash == cv_hash:
        return profile.cv_summary

    raw_text = await asyncio.to_thread(extract_text_from_pdf, profile.cv_data)
    if not raw_text.strip():
        return ""

    try:
        from app.services.cover_letter_service import summarize_cv

        summary = await summarize_cv(raw_text)
    except Exception:
        logger.warning(
            "LLM summarization failed for profile %s, using raw text", profile.id
        )
        summary = raw_text

    profile.cv_summary = summary
    profile.cv_summary_hash = cv_hash
    await db.commit()
    await db.refresh(profile)
    return summary


async def export_profile(db: AsyncSession, profile_id: str) -> dict | None:
    """Export profile data as a dict. Returns None if not found."""
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        return None
    return {
        "name": profile.name,
        "targets": _deserialize_list(profile.targets),
        "constraints": _deserialize_list(profile.constraints),
        "skills": _deserialize_list(profile.skills),
        "preferred_titles": _deserialize_list(profile.preferred_titles),
        "experience_level": profile.experience_level,
        "industries": _deserialize_list(profile.industries),
        "locations": _deserialize_list(profile.locations),
        "work_arrangement": profile.work_arrangement,
        "event_attendance": profile.event_attendance,
        "event_topics": _deserialize_list(profile.event_topics),
        "target_certifications": _deserialize_list(profile.target_certifications),
        "learning_format": profile.learning_format,
    }


async def import_profile(
    db: AsyncSession, data: dict, owner_id: str | None = None
) -> ProfileRead:
    """Import a profile from exported data. Creates a new profile."""
    from app.schemas.profile import ProfileCreate
    body = ProfileCreate(
        name=data.get("name", "Imported Profile"),
        targets=data.get("targets"),
        constraints=data.get("constraints"),
        skills=data.get("skills"),
        preferred_titles=data.get("preferred_titles"),
        experience_level=data.get("experience_level"),
        industries=data.get("industries"),
        locations=data.get("locations"),
        work_arrangement=data.get("work_arrangement"),
        event_attendance=data.get("event_attendance"),
        event_topics=data.get("event_topics"),
        target_certifications=data.get("target_certifications"),
        learning_format=data.get("learning_format"),
    )
    return await create_profile(db, body, owner_id=owner_id)


async def extract_skills_with_ai(cv_text: str) -> list[str]:
    """Use ChatOpenAI to extract skills from CV text."""
    llm = ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.api_key,
    )
    structured_llm = llm.with_structured_output(ExtractedSkills)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a skill extraction assistant. Extract technical skills, "
                "tools, frameworks, programming languages, and professional competencies "
                "from the CV text. Return a JSON object with a single key 'skills' "
                "containing an array of skill strings. Keep each skill concise (1-3 words). "
                "Deduplicate and normalize (e.g. 'JS' -> 'JavaScript')."
            ),
        },
        {"role": "user", "content": cv_text[:8000]},
    ]
    result = await structured_llm.ainvoke(messages)
    return result.skills


async def extract_skills_from_cv(
    db: AsyncSession, profile_id: str
) -> ExtractedSkills:
    """Extract skills from profile's CV. Raises LookupError or ValueError."""
    profile = await db.get(UserProfile, profile_id)
    if profile is None:
        raise LookupError("Profile not found")
    if not profile.cv_data:
        raise ValueError("No CV uploaded for this profile")

    try:
        cv_text = extract_text_from_pdf(profile.cv_data)
    except Exception:
        logger.exception("Failed to extract text from CV for profile %s", profile_id)
        raise ValueError("Failed to read CV file")

    if not cv_text.strip():
        raise ValueError("CV file contains no readable text")

    if not settings.api_key:
        raise ValueError(
            "LLM API key not configured. Set API_KEY in .env to enable skill extraction."
        )

    skills = await extract_skills_with_ai(cv_text)
    return ExtractedSkills(skills=skills)
