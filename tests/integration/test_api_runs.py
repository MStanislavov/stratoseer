"""Tests for the Run API endpoints."""

import asyncio
import json

import pytest

from app.models.profile import UserProfile


async def _create_complete_profile(client, db_session, name="TestProfile"):
    """Create a profile with targets, skills, preferred titles, and a CV path so runs can start."""
    profile_resp = await client.post(
        "/api/profiles",
        json={"name": name, "preferred_titles": ["Software Engineer"]},
    )
    profile_id = profile_resp.json()["id"]

    # Set targets, skills, and cv_path directly on the DB row
    profile = await db_session.get(UserProfile, profile_id)
    profile.targets = json.dumps(["software engineer"])
    profile.skills = json.dumps(["python", "fastapi"])
    profile.preferred_titles = json.dumps(["Software Engineer"])
    profile.cv_path = "/fake/cv.pdf"
    await db_session.commit()

    return profile_id


@pytest.mark.asyncio
async def test_create_run(client, db_session):
    profile_id = await _create_complete_profile(client, db_session)

    resp = await client.post(
        f"/api/profiles/{profile_id}/runs",
        json={"mode": "daily"},
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
async def test_create_run_incomplete_profile(client):
    """Creating a run on a profile with no targets/skills/titles/CV should fail."""
    profile_resp = await client.post(
        "/api/profiles", json={"name": "Empty", "preferred_titles": ["Dev"]}
    )
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/runs",
        json={"mode": "daily"},
    )
    assert resp.status_code == 422
    assert "targets" in resp.json()["detail"]
    assert "skills" in resp.json()["detail"]
    assert "CV" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_run_profile_not_found(client):
    resp = await client.post(
        "/api/profiles/nonexistent/runs",
        json={"mode": "daily"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_invalid_mode(client):
    profile_resp = await client.post("/api/profiles", json={"name": "TestProfile", "preferred_titles": ["Dev"]})
    profile_id = profile_resp.json()["id"]

    resp = await client.post(
        f"/api/profiles/{profile_id}/runs",
        json={"mode": "invalid_mode"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs(client, db_session):
    profile_id = await _create_complete_profile(client, db_session)

    await client.post(f"/api/profiles/{profile_id}/runs", json={"mode": "daily"})
    await client.post(f"/api/profiles/{profile_id}/runs", json={"mode": "daily"})

    resp = await client.get(f"/api/profiles/{profile_id}/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_get_run(client, db_session):
    profile_id = await _create_complete_profile(client, db_session)

    run_resp = await client.post(
        f"/api/profiles/{profile_id}/runs", json={"mode": "daily"}
    )
    run_id = run_resp.json()["id"]

    resp = await client.get(f"/api/profiles/{profile_id}/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id

    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    profile_resp = await client.post("/api/profiles", json={"name": "TestProfile", "preferred_titles": ["Dev"]})
    profile_id = profile_resp.json()["id"]

    resp = await client.get(f"/api/profiles/{profile_id}/runs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_wrong_profile(client, db_session):
    p1_id = await _create_complete_profile(client, db_session, "Profile1")
    p2 = await client.post("/api/profiles", json={"name": "Profile2", "preferred_titles": ["Dev"]})
    p2_id = p2.json()["id"]

    run_resp = await client.post(f"/api/profiles/{p1_id}/runs", json={"mode": "daily"})
    run_id = run_resp.json()["id"]

    # Try to access run via wrong profile
    resp = await client.get(f"/api/profiles/{p2_id}/runs/{run_id}")
    assert resp.status_code == 404

    await asyncio.sleep(0.1)
