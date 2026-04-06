"""Run HTTP endpoints: create, list, get, stream, cancel."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import CurrentUser, VerifiedProfile, get_current_user_from_query
from app.db import get_db
from app.models.user import User
from app.schemas.run import BulkDeleteRequest, BulkDeleteResponse, RunCreate, RunRead
from app.services import run_service
from app.sse import event_manager

_RUN_NOT_FOUND = "Run not found"

router = APIRouter(tags=["runs"])


@router.get("/runs")
async def list_all_runs(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 10,
) -> list[RunRead]:
    """List recent runs across all profiles (filtered by ownership)."""
    owner_id = None if user.role == "admin" else user.id
    return await run_service.list_all_runs(db, limit, owner_id=owner_id)


@router.post(
    "/profiles/{profile_id}/runs",
    status_code=201,
    responses={
        404: {"description": "Profile not found"},
        422: {"description": "Profile is incomplete"},
    },
)
async def create_run(
    _profile: VerifiedProfile,
    profile_id: str,
    body: RunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunRead:
    """Create a new run and launch the pipeline in the background."""
    try:
        return await run_service.create_run(db, profile_id, body)
    except LookupError:
        raise HTTPException(status_code=404, detail="Profile not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/profiles/{profile_id}/runs")
async def list_runs(
    _profile: VerifiedProfile,
    profile_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RunRead]:
    """List all runs for a profile, most recent first."""
    return await run_service.list_runs(db, profile_id)


@router.get(
    "/profiles/{profile_id}/runs/{run_id}",
    responses={404: {"description": "Run not found"}},
)
async def get_run(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunRead:
    """Get details of a single run."""
    result = await run_service.get_run(db, profile_id, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    return result


@router.get("/profiles/{profile_id}/runs/{run_id}/stream")
async def stream_run(
    profile_id: str,
    run_id: str,
    _user: Annotated[User, Depends(get_current_user_from_query)],
):
    """SSE stream of run progress events. Pass token via ?token= query param."""
    _ = profile_id
    return EventSourceResponse(event_manager.event_stream(run_id), ping=15)


@router.post(
    "/profiles/{profile_id}/runs/{run_id}/cancel",
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is not currently executing"},
    },
)
async def cancel_run(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Cancel a running task."""
    try:
        return await run_service.cancel_run(db, profile_id, run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    except ValueError:
        raise HTTPException(status_code=409, detail="Run is not currently executing")


@router.post(
    "/profiles/{profile_id}/runs/bulk-delete",
    responses={
        409: {"description": "Some runs are still executing (listed in skipped)"},
    },
)
async def bulk_delete_runs(
    _profile: VerifiedProfile,
    profile_id: str,
    body: BulkDeleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkDeleteResponse:
    """Delete multiple runs and all associated results at once."""
    result = await run_service.bulk_delete_runs(db, profile_id, body.run_ids)
    return BulkDeleteResponse(**result)


@router.delete(
    "/profiles/{profile_id}/runs/{run_id}",
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is still executing"},
    },
)
async def delete_run(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Delete a run and all associated results."""
    try:
        await run_service.delete_run(db, profile_id, run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    except ValueError:
        raise HTTPException(status_code=409, detail="Cannot delete a run that is still executing")
    return {"detail": "Deleted"}
