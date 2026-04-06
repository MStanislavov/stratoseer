"""Cover letter HTTP endpoints: create, list, get."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import VerifiedProfile
from app.db import get_db
from app.schemas.cover_letter import CoverLetterCreate, CoverLetterRead
from app.services import cover_letter_service

router = APIRouter(tags=["cover-letters"])


@router.post(
    "/profiles/{profile_id}/cover-letters",
    status_code=201,
    responses={
        404: {"description": "Profile or job opportunity not found"},
        422: {"description": "Either job_opportunity_id or jd_text must be provided"},
    },
)
async def create_cover_letter(
    _profile: VerifiedProfile,
    profile_id: str,
    body: CoverLetterCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CoverLetterRead:
    """Generate a cover letter from a job opportunity or raw JD text."""
    try:
        return await cover_letter_service.create_cover_letter(db, profile_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/profiles/{profile_id}/cover-letters")
async def list_cover_letters(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CoverLetterRead]:
    """List all cover letters for a profile."""
    return await cover_letter_service.list_cover_letters(db, profile_id)


@router.get(
    "/profiles/{profile_id}/cover-letters/{letter_id}",
    responses={404: {"description": "Cover letter not found"}},
)
async def get_cover_letter(
    _profile: VerifiedProfile,
    profile_id: str,
    letter_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CoverLetterRead:
    """Get a single cover letter."""
    result = await cover_letter_service.get_cover_letter(db, profile_id, letter_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    return result


@router.delete(
    "/profiles/{profile_id}/cover-letters/{letter_id}",
    status_code=204,
    responses={404: {"description": "Cover letter not found"}},
)
async def delete_cover_letter(
    _profile: VerifiedProfile,
    profile_id: str,
    letter_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a cover letter."""
    deleted = await cover_letter_service.delete_cover_letter(db, profile_id, letter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cover letter not found")
