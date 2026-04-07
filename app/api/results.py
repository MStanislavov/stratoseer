"""Results HTTP endpoints: list, update, and delete results for all 6 entity types."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import VerifiedProfile
from app.db import get_db
from app.models.certification import Certification
from app.models.course import Course
from app.models.event import Event
from app.models.group import Group
from app.models.job_opportunity import JobOpportunity
from app.models.trend import Trend
from app.schemas.certification import CertificationRead
from app.schemas.course import CourseRead
from app.schemas.event import EventRead
from app.schemas.group import GroupRead
from app.schemas.job_opportunity import JobOpportunityRead
from app.schemas.trend import TrendRead
from app.services import result_service

_ITEM_NOT_FOUND = "Item not found"

router = APIRouter(tags=["results"])


class ResultTitleUpdate(BaseModel):
    """Request body for renaming a result item."""

    title: str


# --- List endpoints ---


@router.get("/profiles/{profile_id}/results/jobs")
async def list_jobs(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = None,
) -> list[JobOpportunityRead]:
    """List job opportunities for a profile, optionally filtered by run."""
    return await result_service.list_jobs(db, profile_id, run_id)


@router.get("/profiles/{profile_id}/results/certifications")
async def list_certifications(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = None,
) -> list[CertificationRead]:
    """List certifications for a profile, optionally filtered by run."""
    return await result_service.list_certifications(db, profile_id, run_id)


@router.get("/profiles/{profile_id}/results/courses")
async def list_courses(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = None,
) -> list[CourseRead]:
    """List courses for a profile, optionally filtered by run."""
    return await result_service.list_courses(db, profile_id, run_id)


@router.get("/profiles/{profile_id}/results/events")
async def list_events(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = None,
) -> list[EventRead]:
    """List events for a profile, optionally filtered by run."""
    return await result_service.list_events(db, profile_id, run_id)


@router.get("/profiles/{profile_id}/results/groups")
async def list_groups(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = None,
) -> list[GroupRead]:
    """List groups for a profile, optionally filtered by run."""
    return await result_service.list_groups(db, profile_id, run_id)


@router.get("/profiles/{profile_id}/results/trends")
async def list_trends(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    run_id: str | None = None,
) -> list[TrendRead]:
    """List trends for a profile, optionally filtered by run."""
    return await result_service.list_trends(db, profile_id, run_id)


# --- PATCH endpoints (rename title) ---


@router.patch(
    "/profiles/{profile_id}/results/jobs/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def update_job(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    body: ResultTitleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOpportunityRead:
    """Rename a job opportunity."""
    item = await result_service.update_result_title(
        db, JobOpportunity, profile_id, item_id, body.title
    )
    if item is None:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return JobOpportunityRead.model_validate(item)


@router.patch(
    "/profiles/{profile_id}/results/certifications/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def update_certification(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    body: ResultTitleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CertificationRead:
    """Rename a certification."""
    item = await result_service.update_result_title(
        db, Certification, profile_id, item_id, body.title
    )
    if item is None:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return CertificationRead.model_validate(item)


@router.patch(
    "/profiles/{profile_id}/results/courses/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def update_course(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    body: ResultTitleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CourseRead:
    """Rename a course."""
    item = await result_service.update_result_title(db, Course, profile_id, item_id, body.title)
    if item is None:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return CourseRead.model_validate(item)


@router.patch(
    "/profiles/{profile_id}/results/events/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def update_event(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    body: ResultTitleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EventRead:
    """Rename an event."""
    item = await result_service.update_result_title(db, Event, profile_id, item_id, body.title)
    if item is None:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return EventRead.model_validate(item)


@router.patch(
    "/profiles/{profile_id}/results/groups/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def update_group(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    body: ResultTitleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GroupRead:
    """Rename a group."""
    item = await result_service.update_result_title(db, Group, profile_id, item_id, body.title)
    if item is None:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return GroupRead.model_validate(item)


@router.patch(
    "/profiles/{profile_id}/results/trends/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def update_trend(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    body: ResultTitleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrendRead:
    """Rename a trend."""
    item = await result_service.update_result_title(db, Trend, profile_id, item_id, body.title)
    if item is None:
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return TrendRead.model_validate(item)


# --- DELETE endpoints ---


@router.delete(
    "/profiles/{profile_id}/results/jobs/{item_id}",
    responses={
        404: {"description": "Item not found"},
        409: {"description": "Job has cover letters"},
    },
)
async def delete_job(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    force: bool = False,
) -> dict[str, str]:
    """Delete a job opportunity. Use force=True to cascade-delete linked cover letters."""
    if not force:
        count = await result_service.count_cover_letters_for_job(db, profile_id, item_id)
        if count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"This job has {count} cover letter(s). Delete them too?",
            )
    if force:
        if not await result_service.delete_job_cascade(db, profile_id, item_id):
            raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    else:
        if not await result_service.delete_result(db, JobOpportunity, profile_id, item_id):
            raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return {"detail": "Deleted"}


@router.delete(
    "/profiles/{profile_id}/results/certifications/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def delete_certification(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Delete a certification."""
    if not await result_service.delete_result(db, Certification, profile_id, item_id):
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return {"detail": "Deleted"}


@router.delete(
    "/profiles/{profile_id}/results/courses/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def delete_course(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Delete a course."""
    if not await result_service.delete_result(db, Course, profile_id, item_id):
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return {"detail": "Deleted"}


@router.delete(
    "/profiles/{profile_id}/results/events/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def delete_event(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Delete an event."""
    if not await result_service.delete_result(db, Event, profile_id, item_id):
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return {"detail": "Deleted"}


@router.delete(
    "/profiles/{profile_id}/results/groups/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def delete_group(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Delete a group."""
    if not await result_service.delete_result(db, Group, profile_id, item_id):
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return {"detail": "Deleted"}


@router.delete(
    "/profiles/{profile_id}/results/trends/{item_id}",
    responses={404: {"description": "Item not found"}},
)
async def delete_trend(
    _profile: VerifiedProfile,
    profile_id: str,
    item_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Delete a trend."""
    if not await result_service.delete_result(db, Trend, profile_id, item_id):
        raise HTTPException(status_code=404, detail=_ITEM_NOT_FOUND)
    return {"detail": "Deleted"}
