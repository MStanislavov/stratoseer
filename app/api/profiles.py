"""Profile HTTP endpoints: CRUD, CV upload, skill extraction."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.error_messages import profile_name_exists, profile_not_found
from app.auth.dependencies import CurrentUser, VerifiedProfile
from app.db import get_db
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate
from app.services import profile_service
from app.services.profile_service import ExtractedSkills

router = APIRouter(tags=["profiles"])


@router.post("/profiles", status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileRead:
    """Create a new profile."""
    try:
        return await profile_service.create_profile(db, body, owner_id=user.id)
    except ValueError:
        raise HTTPException(status_code=409, detail=profile_name_exists)


@router.get("/profiles")
async def list_profiles(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProfileRead]:
    """List profiles owned by the current user (admin sees all)."""
    owner_id = None if user.role == "admin" else user.id
    return await profile_service.list_profiles(db, owner_id=owner_id)


@router.get(
    "/profiles/{profile_id}",
    responses={404: {"description": profile_not_found}},
)
async def get_profile(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileRead:
    """Get a single profile by ID."""
    result = await profile_service.get_profile(db, profile_id)
    if result is None:
        raise HTTPException(status_code=404, detail=profile_not_found)
    return result


@router.put(
    "/profiles/{profile_id}",
    responses={404: {"description": profile_not_found}},
)
async def update_profile(
    _profile: VerifiedProfile,
    profile_id: str,
    body: ProfileUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileRead:
    """Update an existing profile."""
    try:
        result = await profile_service.update_profile(db, profile_id, body)
    except ValueError:
        raise HTTPException(status_code=409, detail=profile_name_exists)
    if result is None:
        raise HTTPException(status_code=404, detail=profile_not_found)
    return result


@router.delete(
    "/profiles/{profile_id}",
    status_code=204,
    responses={404: {"description": profile_not_found}},
)
async def delete_profile(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a profile and all associated data."""
    deleted = await profile_service.delete_profile(db, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=profile_not_found)


@router.get(
    "/profiles/{profile_id}/export",
    responses={404: {"description": profile_not_found}},
)
async def export_profile(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Export a profile as a portable dict."""
    result = await profile_service.export_profile(db, profile_id)
    if result is None:
        raise HTTPException(status_code=404, detail=profile_not_found)
    return result


@router.post("/profiles/import", status_code=201)
async def import_profile(
    body: dict,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileRead:
    """Import a profile from previously exported data."""
    try:
        return await profile_service.import_profile(db, body, owner_id=user.id)
    except ValueError:
        raise HTTPException(status_code=409, detail=profile_name_exists)


@router.post(
    "/profiles/{profile_id}/cv",
    responses={404: {"description": profile_not_found}},
)
async def upload_cv(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> ProfileRead:
    """Upload a CV file for a profile."""
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Only PDF files are accepted")
    content = await file.read()
    result = await profile_service.upload_cv(
        db, profile_id, file.filename or "cv.pdf", content
    )
    if result is None:
        raise HTTPException(status_code=404, detail=profile_not_found)
    return result


@router.post(
    "/profiles/{profile_id}/cv/extract-skills",
    responses={
        404: {"description": profile_not_found},
        400: {"description": "No CV uploaded for this profile"},
    },
)
async def extract_skills_from_cv(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExtractedSkills:
    """Extract skills from a profile's uploaded CV using AI."""
    try:
        return await profile_service.extract_skills_from_cv(db, profile_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=profile_not_found)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
