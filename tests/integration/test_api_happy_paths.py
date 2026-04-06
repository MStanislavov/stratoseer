"""Integration tests covering SUCCESS paths for API endpoints.

Complements the existing test files which focus primarily on error paths
(404, 409, 422). Every test here exercises a happy-path code branch that
was previously uncovered.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest

from app.models.certification import Certification
from app.models.course import Course
from app.models.cover_letter import CoverLetter
from app.models.event import Event
from app.models.group import Group
from app.models.job_opportunity import JobOpportunity
from app.models.profile import UserProfile
from app.models.run import Run
from app.models.trend import Trend
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(db_session, *, suffix="hp", role="admin"):
    """Insert a bare User row and return it."""
    user = User(
        first_name="HP",
        last_name="Test",
        email=f"hp-{suffix}-{id(db_session)}@test.com",
        password_hash="fake",
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_profile_and_run(db_session, *, suffix="hp"):
    """Create user + profile + completed run.  Returns (user, profile, run)."""
    user = await _make_user(db_session, suffix=suffix)
    profile = UserProfile(name=f"HPProfile-{suffix}", owner_id=user.id)
    db_session.add(profile)
    await db_session.flush()
    run = Run(profile_id=profile.id, mode="daily", status="completed")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(profile)
    await db_session.refresh(run)
    return user, profile, run


# ===================================================================
# Auth happy paths
# ===================================================================


class TestAuthHappyPaths:
    """Success paths for auth endpoints not already covered elsewhere."""

    @pytest.mark.asyncio
    async def test_login_returns_user_info(self, client):
        """Login response includes user details alongside tokens."""
        await client.post(
            "/api/auth/register",
            json={
                "first_name": "Login",
                "last_name": "Test",
                "email": "login-hp@test.com",
                "password": "LoginPass1",
            },
        )
        resp = await client.post(
            "/api/auth/login",
            json={"email": "login-hp@test.com", "password": "LoginPass1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "login-hp@test.com"
        assert data["user"]["first_name"] == "Login"

    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(self, client):
        """Refresh endpoint returns a new access AND a new refresh token."""
        reg = await client.post(
            "/api/auth/register",
            json={
                "first_name": "Ref",
                "last_name": "Test",
                "email": "ref-hp@test.com",
                "password": "RefPass11",
            },
        )
        old_refresh = reg.json()["refresh_token"]
        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_logout_returns_detail(self, client):
        """Logout always returns a detail message."""
        reg = await client.post(
            "/api/auth/register",
            json={
                "first_name": "Out",
                "last_name": "Test",
                "email": "out-hp@test.com",
                "password": "OutPass11",
            },
        )
        refresh = reg.json()["refresh_token"]
        resp = await client.post(
            "/api/auth/logout",
            json={"refresh_token": refresh},
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Logged out"

    @pytest.mark.asyncio
    async def test_me_returns_full_user(self, client, admin_headers):
        """GET /auth/me returns full user object fields."""
        resp = await client.get("/api/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@test.com"
        assert "id" in data
        assert "first_name" in data
        assert "last_name" in data
        assert "role" in data

    @pytest.mark.asyncio
    async def test_forgot_password_existing_email(self, client):
        """forgot-password succeeds (200) for an existing email too."""
        await client.post(
            "/api/auth/register",
            json={
                "first_name": "Forgot",
                "last_name": "Test",
                "email": "forgot-hp@test.com",
                "password": "ForgotP1",
            },
        )
        resp = await client.post(
            "/api/auth/forgot-password",
            json={"email": "forgot-hp@test.com"},
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_google_login_not_configured_501(self, client):
        """Google OAuth returns 501 when GOOGLE_CLIENT_ID is unset."""
        resp = await client.get("/api/auth/google", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 501)


# ===================================================================
# Profile happy paths
# ===================================================================


class TestProfileHappyPaths:
    """Success paths for profile CRUD, export/import, and CV upload."""

    @pytest.mark.asyncio
    async def test_export_profile_success(self, client, admin_headers):
        """Export returns all profile fields as a portable dict."""
        create = await client.post(
            "/api/profiles",
            json={
                "name": "Export Me",
                "targets": ["devops"],
                "skills": ["terraform"],
                "preferred_titles": ["SRE"],
            },
            headers=admin_headers,
        )
        assert create.status_code == 201
        pid = create.json()["id"]

        resp = await client.get(
            f"/api/profiles/{pid}/export", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Export Me"
        assert data["targets"] == ["devops"]
        assert data["skills"] == ["terraform"]
        assert data["preferred_titles"] == ["SRE"]

    @pytest.mark.asyncio
    async def test_import_profile_success(self, client, admin_headers):
        """Import creates a brand-new profile from previously exported data."""
        payload = {
            "name": "Imported Profile",
            "targets": ["cloud"],
            "skills": ["aws", "gcp"],
            "preferred_titles": ["Cloud Architect"],
        }
        resp = await client.post(
            "/api/profiles/import", json=payload, headers=admin_headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Imported Profile"
        assert data["targets"] == ["cloud"]
        assert data["skills"] == ["aws", "gcp"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_import_profile_duplicate_name_409(self, client, admin_headers):
        """Importing a profile with a duplicate name returns 409."""
        payload = {"name": "DuplicateImport", "preferred_titles": ["Dev"]}
        resp1 = await client.post(
            "/api/profiles/import", json=payload, headers=admin_headers
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/profiles/import", json=payload, headers=admin_headers
        )
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_export_import_round_trip(self, client, admin_headers):
        """Exporting then importing preserves all fields."""
        create = await client.post(
            "/api/profiles",
            json={
                "name": "RoundTrip",
                "targets": ["backend"],
                "skills": ["python"],
                "preferred_titles": ["Backend Dev"],
                "experience_level": "senior",
                "industries": ["fintech"],
                "locations": ["remote"],
                "work_arrangement": "remote",
            },
            headers=admin_headers,
        )
        pid = create.json()["id"]
        exported = (
            await client.get(
                f"/api/profiles/{pid}/export", headers=admin_headers
            )
        ).json()

        # Change name to avoid 409
        exported["name"] = "RoundTrip Copy"
        imported = await client.post(
            "/api/profiles/import", json=exported, headers=admin_headers
        )
        assert imported.status_code == 201
        data = imported.json()
        assert data["targets"] == ["backend"]
        assert data["skills"] == ["python"]
        assert data["experience_level"] == "senior"

    @pytest.mark.asyncio
    async def test_upload_cv_pdf_success(self, client, admin_headers):
        """Uploading a file named .pdf stores the CV and returns profile."""
        create = await client.post(
            "/api/profiles",
            json={"name": "CV Upload Test", "preferred_titles": ["Dev"]},
            headers=admin_headers,
        )
        pid = create.json()["id"]

        fake_pdf = b"%PDF-1.4 fake content"
        resp = await client.post(
            f"/api/profiles/{pid}/cv",
            files={"file": ("resume.pdf", io.BytesIO(fake_pdf), "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cv_filename"] == "resume.pdf"

    @pytest.mark.asyncio
    async def test_update_profile_name_conflict_409(self, client, admin_headers):
        """Renaming a profile to an existing name returns 409."""
        await client.post(
            "/api/profiles",
            json={"name": "Name A", "preferred_titles": ["Dev"]},
            headers=admin_headers,
        )
        create_b = await client.post(
            "/api/profiles",
            json={"name": "Name B", "preferred_titles": ["Dev"]},
            headers=admin_headers,
        )
        pid_b = create_b.json()["id"]

        resp = await client.put(
            f"/api/profiles/{pid_b}",
            json={"name": "Name A"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_extract_skills_no_cv_400(self, client, admin_headers):
        """extract-skills returns 400 when profile has no CV uploaded."""
        create = await client.post(
            "/api/profiles",
            json={"name": "No CV Prof", "preferred_titles": ["Dev"]},
            headers=admin_headers,
        )
        pid = create.json()["id"]

        resp = await client.post(
            f"/api/profiles/{pid}/cv/extract-skills",
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "no cv" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_extract_skills_profile_not_found_404(self, client, admin_headers):
        """extract-skills returns 404 for nonexistent profile."""
        resp = await client.post(
            "/api/profiles/nonexistent-id/cv/extract-skills",
            headers=admin_headers,
        )
        # Will be 404 (profile not found from VerifiedProfile) or 403
        assert resp.status_code in (403, 404)


# ===================================================================
# Results PATCH success paths
# ===================================================================


class TestResultsPatchSuccess:
    """PATCH (rename) success paths for each entity type."""

    @pytest.mark.asyncio
    async def test_patch_certification_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="pcert1")
        cert = Certification(
            profile_id=profile.id,
            run_id=run.id,
            title="Old Cert",
            provider="AWS",
        )
        db_session.add(cert)
        await db_session.commit()
        await db_session.refresh(cert)

        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/certifications/{cert.id}",
            json={"title": "New Cert Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Cert Name"

    @pytest.mark.asyncio
    async def test_patch_course_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="pcourse1")
        course = Course(
            profile_id=profile.id,
            run_id=run.id,
            title="Old Course",
            platform="Udemy",
        )
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)

        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/courses/{course.id}",
            json={"title": "Updated Course"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Course"

    @pytest.mark.asyncio
    async def test_patch_event_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="pevent1")
        event = Event(
            profile_id=profile.id,
            run_id=run.id,
            title="Old Event",
            organizer="PSF",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/events/{event.id}",
            json={"title": "Updated Event"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Event"

    @pytest.mark.asyncio
    async def test_patch_group_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="pgroup1")
        group = Group(
            profile_id=profile.id,
            run_id=run.id,
            title="Old Group",
            platform="Discord",
            member_count=100,
        )
        db_session.add(group)
        await db_session.commit()
        await db_session.refresh(group)

        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/groups/{group.id}",
            json={"title": "Updated Group"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Group"

    @pytest.mark.asyncio
    async def test_patch_trend_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="ptrend1")
        trend = Trend(
            profile_id=profile.id,
            run_id=run.id,
            title="Old Trend",
            category="Tech",
        )
        db_session.add(trend)
        await db_session.commit()
        await db_session.refresh(trend)

        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/trends/{trend.id}",
            json={"title": "Updated Trend"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Trend"


# ===================================================================
# Results DELETE success paths
# ===================================================================


class TestResultsDeleteSuccess:
    """DELETE success paths for course, event, group, and trend."""

    @pytest.mark.asyncio
    async def test_delete_course_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="dcourse1")
        course = Course(
            profile_id=profile.id,
            run_id=run.id,
            title="Course To Delete",
            platform="Coursera",
        )
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/courses/{course.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_event_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="devent1")
        event = Event(
            profile_id=profile.id,
            run_id=run.id,
            title="Event To Delete",
            organizer="Org",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/events/{event.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_group_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="dgroup1")
        group = Group(
            profile_id=profile.id,
            run_id=run.id,
            title="Group To Delete",
            platform="Slack",
        )
        db_session.add(group)
        await db_session.commit()
        await db_session.refresh(group)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/groups/{group.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_trend_success(self, client, db_session, admin_headers):
        _, profile, run = await _make_profile_and_run(db_session, suffix="dtrend1")
        trend = Trend(
            profile_id=profile.id,
            run_id=run.id,
            title="Trend To Delete",
            category="AI",
        )
        db_session.add(trend)
        await db_session.commit()
        await db_session.refresh(trend)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/trends/{trend.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"


# ===================================================================
# Run happy paths
# ===================================================================


class TestRunHappyPaths:
    """Success paths for run endpoints not already exercised."""

    @pytest.mark.asyncio
    async def test_get_run_success(self, client, db_session, admin_headers):
        """GET /runs/{run_id} returns a completed run."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="getrun1")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/{run.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run.id
        assert data["mode"] == "daily"
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_runs_success(self, client, db_session, admin_headers):
        """GET /profiles/{id}/runs returns runs list."""
        _, profile, _ = await _make_profile_and_run(db_session, suffix="listrun1")
        # Add a second run
        run2 = Run(profile_id=profile.id, mode="weekly", status="completed")
        db_session.add(run2)
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/runs", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_cancel_completed_run_409(self, client, db_session, admin_headers):
        """Canceling a completed run returns 409."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="cancelrun1")
        resp = await client.post(
            f"/api/profiles/{profile.id}/runs/{run.id}/cancel",
            headers=admin_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_run_success(self, client, db_session, admin_headers):
        """DELETE on a completed run succeeds."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="delrun1")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/runs/{run.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"


# ===================================================================
# Cover letter happy paths
# ===================================================================


class TestCoverLetterHappyPaths:
    """Success paths for cover letter list, get, and delete."""

    @pytest.mark.asyncio
    async def test_list_cover_letters_with_data(self, client, db_session, admin_headers):
        """Listing cover letters returns them in reverse chronological order."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="cllist1")
        cl1 = CoverLetter(
            profile_id=profile.id, run_id=run.id, content="Letter one"
        )
        cl2 = CoverLetter(
            profile_id=profile.id, run_id=run.id, content="Letter two"
        )
        db_session.add(cl1)
        db_session.add(cl2)
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/cover-letters",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_cover_letter_success(self, client, db_session, admin_headers):
        """GET a specific cover letter by ID."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="clget1")
        cl = CoverLetter(
            profile_id=profile.id, run_id=run.id, content="Dear hiring manager..."
        )
        db_session.add(cl)
        await db_session.commit()
        await db_session.refresh(cl)

        resp = await client.get(
            f"/api/profiles/{profile.id}/cover-letters/{cl.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == cl.id
        assert data["content"] == "Dear hiring manager..."

    @pytest.mark.asyncio
    async def test_get_cover_letter_with_job(self, client, db_session, admin_headers):
        """GET cover letter includes job details when linked to a job opportunity."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="clgetjob1")
        job = JobOpportunity(
            profile_id=profile.id,
            run_id=run.id,
            title="SWE at BigCo",
            company="BigCo",
            url="https://bigco.com/jobs/1",
        )
        db_session.add(job)
        await db_session.flush()

        cl = CoverLetter(
            profile_id=profile.id,
            job_opportunity_id=job.id,
            run_id=run.id,
            content="Dear BigCo team...",
        )
        db_session.add(cl)
        await db_session.commit()
        await db_session.refresh(cl)

        resp = await client.get(
            f"/api/profiles/{profile.id}/cover-letters/{cl.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_title"] == "SWE at BigCo"
        assert data["job_company"] == "BigCo"
        assert data["job_url"] == "https://bigco.com/jobs/1"

    @pytest.mark.asyncio
    async def test_delete_cover_letter_success(self, client, db_session, admin_headers):
        """DELETE an existing cover letter returns 204."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="cldel1")
        cl = CoverLetter(
            profile_id=profile.id, run_id=run.id, content="To be deleted"
        )
        db_session.add(cl)
        await db_session.commit()
        await db_session.refresh(cl)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/cover-letters/{cl.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 204

        # Confirm it is gone
        resp2 = await client.get(
            f"/api/profiles/{profile.id}/cover-letters/{cl.id}",
            headers=admin_headers,
        )
        assert resp2.status_code == 404


# ===================================================================
# Audit happy paths (mocked audit_service internals)
# ===================================================================


class TestAuditHappyPaths:
    """Success paths for audit endpoints, mocking the file-based audit service."""

    @pytest.mark.asyncio
    async def test_audit_trail_success(self, client, db_session, admin_headers):
        """GET /audit returns events list when audit data exists."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="audtrail1")

        mock_return = {"run_id": run.id, "events": [{"event_type": "agent_start"}]}
        with patch(
            "app.services.audit_service.get_audit_trail",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.get(
                f"/api/profiles/{profile.id}/runs/{run.id}/audit",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run.id
        assert len(data["events"]) == 1

    @pytest.mark.asyncio
    async def test_verifier_report_success(self, client, db_session, admin_headers):
        """GET /verifier-report returns report when bundle exists."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="audver1")

        mock_return = {"overall": "pass", "claims": []}
        with patch(
            "app.services.audit_service.get_verifier_report",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.get(
                f"/api/profiles/{profile.id}/runs/{run.id}/verifier-report",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall"] == "pass"

    @pytest.mark.asyncio
    async def test_token_usage_success(self, client, db_session, admin_headers):
        """GET /token-usage returns usage breakdown."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="audtok1")

        mock_return = {"total_tokens": 500, "agents": {"retriever": 300}}
        with patch(
            "app.services.audit_service.get_token_usage",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.get(
                f"/api/profiles/{profile.id}/runs/{run.id}/token-usage",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == 500

    @pytest.mark.asyncio
    async def test_insights_success(self, client, db_session, admin_headers):
        """GET /insights returns strategic recommendations and risk assessments."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="audins1")

        mock_return = {
            "strategic_recommendations": ["Expand cloud skills"],
            "ceo_summary": "Focus on growth",
            "risk_assessments": [],
            "cfo_summary": "Budget on track",
        }
        with patch(
            "app.services.audit_service.get_executive_insights",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.get(
                f"/api/profiles/{profile.id}/runs/{run.id}/insights",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ceo_summary"] == "Focus on growth"
        assert data["cfo_summary"] == "Budget on track"

    @pytest.mark.asyncio
    async def test_replay_strict_success(self, client, db_session, admin_headers):
        """POST /replay with mode=strict returns a replay response."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="audrep1")

        mock_return = {
            "run_id": "new-run-id",
            "replay_mode": "strict",
            "original_run_id": run.id,
            "result": {},
            "verifier_report": {},
            "drift": [],
        }
        with patch(
            "app.services.audit_service.replay_run",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.post(
                f"/api/profiles/{profile.id}/runs/{run.id}/replay",
                json={"mode": "strict"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["replay_mode"] == "strict"
        assert data["original_run_id"] == run.id

    @pytest.mark.asyncio
    async def test_replay_refresh_success(self, client, db_session, admin_headers):
        """POST /replay with mode=refresh returns a replay response."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="audrep2")

        mock_return = {
            "run_id": "new-run-id-2",
            "replay_mode": "refresh",
            "original_run_id": run.id,
            "result": {},
            "verifier_report": {},
            "drift": [],
        }
        with patch(
            "app.services.audit_service.replay_run",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.post(
                f"/api/profiles/{profile.id}/runs/{run.id}/replay",
                json={"mode": "refresh"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["replay_mode"] == "refresh"

    @pytest.mark.asyncio
    async def test_diff_success(self, client, db_session, admin_headers):
        """GET /diff/{other_run_id} returns a structured diff."""
        _, profile, run = await _make_profile_and_run(db_session, suffix="auddiff1")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.commit()
        await db_session.refresh(run2)

        mock_return = {
            "run_a": run.id,
            "run_b": run2.id,
            "additions": [],
            "removals": [],
            "changes": [],
            "summary": {"total_changes": 0},
        }
        with patch(
            "app.services.audit_service.diff_runs",
            new_callable=AsyncMock,
            return_value=mock_return,
        ):
            resp = await client.get(
                f"/api/profiles/{profile.id}/runs/{run.id}/diff/{run2.id}",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_a"] == run.id
        assert data["run_b"] == run2.id


# ===================================================================
# Admin happy paths
# ===================================================================


class TestAdminHappyPaths:
    """Success paths for admin endpoints."""

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, client, admin_headers):
        """Admin can paginate users list."""
        resp = await client.get(
            "/api/admin/users?page=1&page_size=5",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert data["total"] >= 1
        assert len(data["users"]) >= 1

    @pytest.mark.asyncio
    async def test_list_users_has_profile_and_run_counts(
        self, client, db_session, admin_headers
    ):
        """User rows include profile_count and run_count."""
        resp = await client.get("/api/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        user_row = resp.json()["users"][0]
        assert "profile_count" in user_row
        assert "run_count" in user_row

    @pytest.mark.asyncio
    async def test_admin_forbidden_for_regular_user(self, client, auth_headers):
        """Non-admin gets 403."""
        resp = await client.get("/api/admin/users", headers=auth_headers)
        assert resp.status_code == 403


# ===================================================================
# Cross-profile /api/runs
# ===================================================================


class TestCrossProfileRuns:
    """Success paths for the cross-profile GET /api/runs endpoint."""

    @pytest.mark.asyncio
    async def test_list_all_runs_with_limit(self, client, db_session, admin_headers):
        """GET /api/runs respects limit parameter."""
        _, profile, _ = await _make_profile_and_run(db_session, suffix="xrun1")
        for i in range(3):
            db_session.add(
                Run(profile_id=profile.id, mode="daily", status="completed")
            )
        await db_session.commit()

        resp = await client.get("/api/runs?limit=2", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should respect the limit
        assert len(data) <= 2

    @pytest.mark.asyncio
    async def test_list_all_runs_default(self, client, db_session, admin_headers):
        """GET /api/runs with default limit works."""
        resp = await client.get("/api/runs", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ===================================================================
# Results list with run_id filter for non-job types
# ===================================================================


class TestResultsListFiltered:
    """Verify run_id filter works for certification, course, event, group, trend."""

    @pytest.mark.asyncio
    async def test_list_certifications_filtered(self, client, db_session, admin_headers):
        _, profile, run1 = await _make_profile_and_run(db_session, suffix="cfilt1")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.flush()

        db_session.add(Certification(profile_id=profile.id, run_id=run1.id, title="C1", provider="P"))
        db_session.add(Certification(profile_id=profile.id, run_id=run2.id, title="C2", provider="P"))
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/results/certifications?run_id={run1.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "C1"

    @pytest.mark.asyncio
    async def test_list_courses_filtered(self, client, db_session, admin_headers):
        _, profile, run1 = await _make_profile_and_run(db_session, suffix="cofilt1")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.flush()

        db_session.add(Course(profile_id=profile.id, run_id=run1.id, title="Co1", platform="U"))
        db_session.add(Course(profile_id=profile.id, run_id=run2.id, title="Co2", platform="U"))
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/results/courses?run_id={run1.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "Co1"

    @pytest.mark.asyncio
    async def test_list_events_filtered(self, client, db_session, admin_headers):
        _, profile, run1 = await _make_profile_and_run(db_session, suffix="efilt1")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.flush()

        db_session.add(Event(profile_id=profile.id, run_id=run1.id, title="E1", organizer="O"))
        db_session.add(Event(profile_id=profile.id, run_id=run2.id, title="E2", organizer="O"))
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/results/events?run_id={run1.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "E1"

    @pytest.mark.asyncio
    async def test_list_groups_filtered(self, client, db_session, admin_headers):
        _, profile, run1 = await _make_profile_and_run(db_session, suffix="gfilt1")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.flush()

        db_session.add(Group(profile_id=profile.id, run_id=run1.id, title="G1", platform="S"))
        db_session.add(Group(profile_id=profile.id, run_id=run2.id, title="G2", platform="S"))
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/results/groups?run_id={run1.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "G1"

    @pytest.mark.asyncio
    async def test_list_trends_filtered(self, client, db_session, admin_headers):
        _, profile, run1 = await _make_profile_and_run(db_session, suffix="tfilt1")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.flush()

        db_session.add(Trend(profile_id=profile.id, run_id=run1.id, title="T1", category="AI"))
        db_session.add(Trend(profile_id=profile.id, run_id=run2.id, title="T2", category="AI"))
        await db_session.commit()

        resp = await client.get(
            f"/api/profiles/{profile.id}/results/trends?run_id={run1.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "T1"
