"""Tests for the cover letters API endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_cover_letter_requires_input(client, admin_headers):
    """POST without job_opportunity_id or jd_text should fail."""
    profile_resp = await client.post(
        "/api/profiles",
        json={"name": "CL Validation", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/cover-letters",
        json={},
        headers=admin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_cover_letter_not_found(client, admin_headers):
    """GET nonexistent cover letter returns 404."""
    profile_resp = await client.post(
        "/api/profiles",
        json={"name": "CL 404", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.get(
        f"/api/profiles/{profile_id}/cover-letters/nonexistent-id",
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_cover_letter_profile_not_found(client, admin_headers):
    """POST to nonexistent profile returns 404."""
    resp = await client.post(
        "/api/profiles/nonexistent/cover-letters",
        json={"jd_text": "Some JD"},
        headers=admin_headers,
    )
    assert resp.status_code == 404
