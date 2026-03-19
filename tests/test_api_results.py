"""Tests for the results API (all 5 entity types)."""

import pytest

from app.models.certification import Certification
from app.models.course import Course
from app.models.event import Event
from app.models.group import Group
from app.models.job_opportunity import JobOpportunity
from app.models.trend import Trend
from app.models.profile import UserProfile
from app.models.run import Run


async def _create_profile_and_run(db_session):
    """Helper to create a profile and run for testing."""
    profile = UserProfile(name="Test Profile")
    db_session.add(profile)
    await db_session.flush()

    run = Run(profile_id=profile.id, mode="daily", status="completed")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(profile)
    await db_session.refresh(run)
    return profile, run


@pytest.mark.asyncio
async def test_list_jobs(client, db_session):
    profile, run = await _create_profile_and_run(db_session)
    db_session.add(JobOpportunity(
        profile_id=profile.id, run_id=run.id,
        title="SWE at Acme", company="Acme",
        url="https://example.com/1", description="Python role",
    ))
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile.id}/results/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "SWE at Acme"
    assert data[0]["company"] == "Acme"


@pytest.mark.asyncio
async def test_list_certifications(client, db_session):
    profile, run = await _create_profile_and_run(db_session)
    db_session.add(Certification(
        profile_id=profile.id, run_id=run.id,
        title="AWS SA", provider="Amazon",
    ))
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile.id}/results/certifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "AWS SA"


@pytest.mark.asyncio
async def test_list_courses(client, db_session):
    profile, run = await _create_profile_and_run(db_session)
    db_session.add(Course(
        profile_id=profile.id, run_id=run.id,
        title="Python Masterclass", platform="Udemy",
    ))
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile.id}/results/courses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Python Masterclass"


@pytest.mark.asyncio
async def test_list_events(client, db_session):
    profile, run = await _create_profile_and_run(db_session)
    db_session.add(Event(
        profile_id=profile.id, run_id=run.id,
        title="PyCon 2026", organizer="PSF",
    ))
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile.id}/results/events")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "PyCon 2026"


@pytest.mark.asyncio
async def test_list_groups(client, db_session):
    profile, run = await _create_profile_and_run(db_session)
    db_session.add(Group(
        profile_id=profile.id, run_id=run.id,
        title="Python Discord", platform="Discord", member_count=50000,
    ))
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile.id}/results/groups")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Python Discord"
    assert data[0]["member_count"] == 50000


@pytest.mark.asyncio
async def test_list_trends(client, db_session):
    profile, run = await _create_profile_and_run(db_session)
    db_session.add(Trend(
        profile_id=profile.id, run_id=run.id,
        title="AI-Driven DevOps", category="Technology",
        url="https://example.com/trend/1", description="Growing trend",
        relevance="high", source="TechCrunch",
    ))
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile.id}/results/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "AI-Driven DevOps"
    assert data[0]["category"] == "Technology"
    assert data[0]["relevance"] == "high"


@pytest.mark.asyncio
async def test_list_jobs_filtered_by_run_id(client, db_session):
    profile, run1 = await _create_profile_and_run(db_session)
    run2 = Run(profile_id=profile.id, mode="daily", status="completed")
    db_session.add(run2)
    await db_session.commit()
    await db_session.refresh(run2)

    db_session.add(JobOpportunity(
        profile_id=profile.id, run_id=run1.id,
        title="Job from run1", company="A",
    ))
    db_session.add(JobOpportunity(
        profile_id=profile.id, run_id=run2.id,
        title="Job from run2", company="B",
    ))
    await db_session.commit()

    # No filter: both returned
    resp = await client.get(f"/api/profiles/{profile.id}/results/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Filter by run1
    resp = await client.get(f"/api/profiles/{profile.id}/results/jobs?run_id={run1.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Job from run1"

    # Filter by run2
    resp = await client.get(f"/api/profiles/{profile.id}/results/jobs?run_id={run2.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Job from run2"


@pytest.mark.asyncio
async def test_list_jobs_empty(client, db_session):
    profile, _ = await _create_profile_and_run(db_session)
    resp = await client.get(f"/api/profiles/{profile.id}/results/jobs")
    assert resp.status_code == 200
    assert resp.json() == []
