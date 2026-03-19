"""Tests for the cover letters API endpoints."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_create_cover_letter_with_jd_text(client):
    """POST cover letter with raw JD text."""
    profile_resp = await client.post(
        "/api/profiles", json={"name": "CL Test Profile"}
    )
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/cover-letters",
        json={"jd_text": "Looking for a Python developer with AWS experience."},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["profile_id"] == profile_id
    assert data["run_id"] is not None
    assert data["job_opportunity_id"] is None

    # Wait for background pipeline to complete
    await asyncio.sleep(1)

    # Fetch the cover letter, it should now have content
    get_resp = await client.get(
        f"/api/profiles/{profile_id}/cover-letters/{data['id']}"
    )
    assert get_resp.status_code == 200


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
async def test_list_cover_letters(client):
    """GET list of cover letters for a profile."""
    profile_resp = await client.post(
        "/api/profiles", json={"name": "CL List"}
    )
    profile_id = profile_resp.json()["id"]

    # Create one
    await client.post(
        f"/api/profiles/{profile_id}/cover-letters",
        json={"jd_text": "Some JD text here."},
    )

    resp = await client.get(f"/api/profiles/{profile_id}/cover-letters")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1


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
