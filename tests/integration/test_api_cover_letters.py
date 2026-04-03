"""Tests for the cover letters API endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_cover_letter_requires_input(client):
    """POST without job_opportunity_id or jd_text should fail."""
    profile_resp = await client.post(
        "/api/profiles", json={"name": "CL Validation"}
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/cover-letters",
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_cover_letter_not_found(client):
    """GET nonexistent cover letter returns 404."""
    profile_resp = await client.post(
        "/api/profiles", json={"name": "CL 404"}
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.get(
        f"/api/profiles/{profile_id}/cover-letters/nonexistent-id"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_cover_letter_profile_not_found(client):
    """POST to nonexistent profile returns 404."""
    resp = await client.post(
        "/api/profiles/nonexistent/cover-letters",
        json={"jd_text": "Some JD"},
    )
    assert resp.status_code == 404
