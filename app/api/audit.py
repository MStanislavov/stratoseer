"""Audit HTTP endpoints: audit trail, verifier report, replay, diff."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import VerifiedProfile
from app.db import get_db
from app.services import audit_service

router = APIRouter(tags=["audit"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class ReplayRequest(BaseModel):
    """Request body for replaying a run."""

    mode: Literal["strict", "refresh"]


class ReplayResponse(BaseModel):
    """Response body containing replay results and drift information."""

    run_id: str
    replay_mode: str
    original_run_id: str
    result: dict
    verifier_report: dict
    drift: list


class DiffResponse(BaseModel):
    """Response body containing a structured diff between two runs."""

    run_a: str
    run_b: str
    additions: list
    removals: list
    changes: list
    summary: dict


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get(
    "/profiles/{profile_id}/runs/{run_id}/audit",
    responses={404: {"description": "Run not found"}},
)
async def get_audit_trail(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return the full audit event log for a run."""
    try:
        return await audit_service.get_audit_trail(db, profile_id, run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.get(
    "/profiles/{profile_id}/runs/{run_id}/verifier-report",
    responses={404: {"description": "No audit bundle found for this run"}},
)
async def get_verifier_report(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return the verifier report from the run bundle."""
    try:
        return await audit_service.get_verifier_report(db, profile_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------
# Token usage endpoint
# ------------------------------------------------------------------


@router.get(
    "/profiles/{profile_id}/runs/{run_id}/token-usage",
    responses={404: {"description": "Run not found or no usage data"}},
)
async def get_token_usage(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return per-agent token usage breakdown for a run."""
    try:
        return await audit_service.get_token_usage(db, profile_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------
# Executive insights (CEO / CFO) endpoint
# ------------------------------------------------------------------


@router.get(
    "/profiles/{profile_id}/runs/{run_id}/insights",
    responses={404: {"description": "Run or audit bundle not found"}},
)
async def get_executive_insights(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return strategic recommendations (CEO) and risk assessments (CFO) for a run."""
    try:
        return await audit_service.get_executive_insights(db, profile_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------
# Replay endpoint
# ------------------------------------------------------------------


@router.post(
    "/profiles/{profile_id}/runs/{run_id}/replay",
    response_model=ReplayResponse,
    responses={404: {"description": "Run or audit bundle not found"}},
)
async def replay_run(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    body: ReplayRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Replay a previous run in strict or refresh mode.

    - **strict**: re-use stored tool responses (no network calls).
    - **refresh**: re-execute the graph live and compare for drift.

    In Phase 1 (mock agents) both modes produce identical results.
    """
    try:
        return await audit_service.replay_run(db, profile_id, run_id, body.mode)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------
# Diff endpoint
# ------------------------------------------------------------------


@router.get(
    "/profiles/{profile_id}/runs/{run_id}/diff/{other_run_id}",
    response_model=DiffResponse,
    responses={404: {"description": "Run not found"}},
)
async def diff_runs(
    _profile: VerifiedProfile,
    profile_id: str,
    run_id: str,
    other_run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return a structured diff between two runs."""
    try:
        return await audit_service.diff_runs(db, profile_id, run_id, other_run_id)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
