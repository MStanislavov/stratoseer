"""Tests for the Run API endpoints."""

import asyncio
import json

import pytest

from app.models.profile import UserProfile


async def _create_complete_profile(client, db_session, headers, name="TestProfile"):
    """Create a profile with targets, skills, preferred titles, and a CV path so runs can start."""
    profile_resp = await client.post(
        "/api/profiles",
        json={"name": name, "preferred_titles": ["Software Engineer"]},
        headers=headers,
    )
    profile_id = profile_resp.json()["id"]

    # Set targets, skills, and cv_data directly on the DB row
    profile = await db_session.get(UserProfile, profile_id)
    profile.targets = json.dumps(["software engineer"])
    profile.skills = json.dumps(["python", "fastapi"])
    profile.preferred_titles = json.dumps(["Software Engineer"])
    profile.cv_data = b"fake-pdf-content"
    profile.cv_filename = "cv.pdf"
    await db_session.commit()

    return profile_id


@pytest.mark.asyncio
async def test_create_run(client, db_session, admin_headers):
    """Verify that creating a daily run returns status 201 with a pending run record.

    Args:
        client: The httpx test client.
        db_session: The test database session.
        admin_headers: Auth headers for the admin user.
    """
    profile_id = await _create_complete_profile(client, db_session, admin_headers)

    resp = await client.post(
        f"/api/profiles/{profile_id}/runs",
        json={"mode": "daily"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["mode"] == "daily"
    assert data["status"] == "pending"
    assert data["profile_id"] == profile_id
    assert "id" in data

    # Allow background task to be created (but it will fail since no real DB for background)
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_create_run_incomplete_profile(client, admin_headers):
    """Creating a run on a profile with no targets/skills/titles/CV should fail."""
    profile_resp = await client.post(
        "/api/profiles", json={"name": "Empty", "preferred_titles": ["Dev"]}, headers=admin_headers
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/runs",
        json={"mode": "daily"},
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert "targets" in resp.json()["detail"]
    assert "skills" in resp.json()["detail"]
    assert "CV" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_run_profile_not_found(client, admin_headers):
    """Verify that starting a run on a nonexistent profile returns 404.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    resp = await client.post(
        "/api/profiles/nonexistent/runs",
        json={"mode": "daily"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_invalid_mode(client, admin_headers):
    """Verify that an invalid run mode returns 422.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    profile_resp = await client.post(
        "/api/profiles",
        json={"name": "TestProfile", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/runs",
        json={"mode": "invalid_mode"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs(client, db_session, admin_headers):
    """Verify listing runs for a profile returns all created runs.

    Args:
        client: The httpx test client.
        db_session: The test database session.
        admin_headers: Auth headers for the admin user.
    """
    profile_id = await _create_complete_profile(client, db_session, admin_headers)

    await client.post(
        f"/api/profiles/{profile_id}/runs", json={"mode": "daily"}, headers=admin_headers
    )
    await client.post(
        f"/api/profiles/{profile_id}/runs", json={"mode": "daily"}, headers=admin_headers
    )

    resp = await client.get(f"/api/profiles/{profile_id}/runs", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_get_run(client, db_session, admin_headers):
    """Verify fetching a single run by ID returns the correct record.

    Args:
        client: The httpx test client.
        db_session: The test database session.
        admin_headers: Auth headers for the admin user.
    """
    profile_id = await _create_complete_profile(client, db_session, admin_headers)

    run_resp = await client.post(
        f"/api/profiles/{profile_id}/runs", json={"mode": "daily"}, headers=admin_headers
    )
    run_id = run_resp.json()["id"]

    resp = await client.get(f"/api/profiles/{profile_id}/runs/{run_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id

    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_get_run_not_found(client, admin_headers):
    """Verify that fetching a nonexistent run returns 404.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    profile_resp = await client.post(
        "/api/profiles",
        json={"name": "TestProfile", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.get(f"/api/profiles/{profile_id}/runs/nonexistent", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_wrong_profile(client, db_session, admin_headers):
    """Verify that accessing a run via a different profile returns 404.

    Args:
        client: The httpx test client.
        db_session: The test database session.
        admin_headers: Auth headers for the admin user.
    """
    p1_id = await _create_complete_profile(client, db_session, admin_headers, "Profile1")
    p2 = await client.post(
        "/api/profiles",
        json={"name": "Profile2", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    p2_id = p2.json()["id"]

    run_resp = await client.post(
        f"/api/profiles/{p1_id}/runs", json={"mode": "daily"}, headers=admin_headers
    )
    run_id = run_resp.json()["id"]

    # Try to access run via wrong profile
    resp = await client.get(f"/api/profiles/{p2_id}/runs/{run_id}", headers=admin_headers)
    assert resp.status_code == 404

    await asyncio.sleep(0.1)
