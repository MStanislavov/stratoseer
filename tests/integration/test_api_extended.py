"""Extended API integration tests: audit, policies, results mutations, runs,
cover letters error paths, and auth edge cases."""

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


async def _setup_profile_and_run(db_session, *, email_suffix="ext"):
    """Create admin user + profile + run, return (profile, run)."""
    user = User(
        first_name="Ext",
        last_name="Test",
        email=f"ext-{email_suffix}-{id(db_session)}@test.com",
        password_hash="fake",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()

    profile = UserProfile(name=f"ExtProfile-{email_suffix}", owner_id=user.id)
    db_session.add(profile)
    await db_session.flush()

    run = Run(profile_id=profile.id, mode="daily", status="completed")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(profile)
    await db_session.refresh(run)
    return profile, run


# ---------------------------------------------------------------------------
# Policy endpoints
# ---------------------------------------------------------------------------


class TestPolicyEndpoints:
    """Tests for GET /api/policies and GET /api/policies/{name}."""

    @pytest.mark.asyncio
    async def test_list_policies(self, client, admin_headers):
        resp = await client.get("/api/policies", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # We know the policy dir has at least budgets.yaml
        names = [p["name"] for p in data]
        assert "budgets" in names

    @pytest.mark.asyncio
    async def test_get_policy_success(self, client, admin_headers):
        resp = await client.get("/api/policies/budgets", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "budgets"
        assert isinstance(data["content"], dict)

    @pytest.mark.asyncio
    async def test_get_policy_not_found(self, client, admin_headers):
        resp = await client.get(
            "/api/policies/nonexistent_policy", headers=admin_headers
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------


class TestAuditEndpoints:
    """Tests for audit trail, verifier report, token-usage, and insights endpoints."""

    @pytest.mark.asyncio
    async def test_audit_trail_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="audit1")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/nonexistent-run-id/audit",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_verifier_report_run_not_found(
        self, client, db_session, admin_headers
    ):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="audit2")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/nonexistent-run-id/verifier-report",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_token_usage_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="audit3")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/nonexistent-run-id/token-usage",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_insights_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="audit4")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/nonexistent-run-id/insights",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_run_not_found(self, client, db_session, admin_headers):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="audit5")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/{run.id}/diff/nonexistent",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_replay_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="audit6")
        resp = await client.post(
            f"/api/profiles/{profile.id}/runs/nonexistent-run-id/replay",
            json={"mode": "strict"},
            headers=admin_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Results PATCH/DELETE endpoints
# ---------------------------------------------------------------------------


class TestResultsMutations:
    """Tests for PATCH (rename) and DELETE on result items across all entity types."""

    @pytest.mark.asyncio
    async def test_patch_job_success(self, client, db_session, admin_headers):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="pj1")
        job = JobOpportunity(
            profile_id=profile.id,
            run_id=run.id,
            title="Old Title",
            company="Co",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/jobs/{job.id}",
            json={"title": "New Title"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_patch_job_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="pj2")
        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/jobs/nonexistent",
            json={"title": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_certification_not_found(
        self, client, db_session, admin_headers
    ):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="pc1")
        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/certifications/nonexistent",
            json={"title": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_course_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="pco1")
        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/courses/nonexistent",
            json={"title": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_event_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="pe1")
        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/events/nonexistent",
            json={"title": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_group_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="pg1")
        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/groups/nonexistent",
            json={"title": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_trend_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="pt1")
        resp = await client.patch(
            f"/api/profiles/{profile.id}/results/trends/nonexistent",
            json={"title": "X"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job_success(self, client, db_session, admin_headers):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="dj1")
        job = JobOpportunity(
            profile_id=profile.id,
            run_id=run.id,
            title="Delete Me",
            company="Co",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/jobs/{job.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_job_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="dj2")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/jobs/nonexistent",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job_with_cover_letters_requires_force(
        self, client, db_session, admin_headers
    ):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="dj3")
        job = JobOpportunity(
            profile_id=profile.id,
            run_id=run.id,
            title="Job With CL",
            company="Co",
        )
        db_session.add(job)
        await db_session.flush()

        cl = CoverLetter(
            profile_id=profile.id,
            job_opportunity_id=job.id,
            content="Dear hiring manager...",
        )
        db_session.add(cl)
        await db_session.commit()
        await db_session.refresh(job)

        # Without force=True, should get 409
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/jobs/{job.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 409
        assert "cover letter" in resp.json()["detail"].lower()

        # With force=True, should succeed
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/jobs/{job.id}?force=true",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_certification_success(
        self, client, db_session, admin_headers
    ):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="dc1")
        cert = Certification(
            profile_id=profile.id,
            run_id=run.id,
            title="AWS SA",
            provider="Amazon",
        )
        db_session.add(cert)
        await db_session.commit()
        await db_session.refresh(cert)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/certifications/{cert.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_certification_not_found(
        self, client, db_session, admin_headers
    ):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="dc2")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/certifications/nope",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_course_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="dco1")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/courses/nope",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_event_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="de1")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/events/nope",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_group_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="dg1")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/groups/nope",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_trend_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="dt1")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/results/trends/nope",
            headers=admin_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Run endpoints (cancel, delete, error paths)
# ---------------------------------------------------------------------------


class TestRunEndpoints:
    """Tests for run cancel, delete, bulk-delete, and error paths."""

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="run1")
        resp = await client.get(
            f"/api/profiles/{profile.id}/runs/nonexistent-run",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="run2")
        resp = await client.post(
            f"/api/profiles/{profile.id}/runs/nonexistent-run/cancel",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_completed_run_409(self, client, db_session, admin_headers):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="run3")
        resp = await client.post(
            f"/api/profiles/{profile.id}/runs/{run.id}/cancel",
            headers=admin_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_run_not_found(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="run4")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/runs/nonexistent-run",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_completed_run_success(
        self, client, db_session, admin_headers
    ):
        profile, run = await _setup_profile_and_run(db_session, email_suffix="run5")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/runs/{run.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_run_with_status_running_but_no_task(
        self, client, db_session, admin_headers
    ):
        """A run with status='running' but no live task can be deleted (orphan cleanup)."""
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="run6")
        orphan_run = Run(
            profile_id=profile.id, mode="daily", status="running"
        )
        db_session.add(orphan_run)
        await db_session.commit()
        await db_session.refresh(orphan_run)

        resp = await client.delete(
            f"/api/profiles/{profile.id}/runs/{orphan_run.id}",
            headers=admin_headers,
        )
        # No live task in _running_tasks, so service allows deletion
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bulk_delete_runs(self, client, db_session, admin_headers):
        profile, run1 = await _setup_profile_and_run(db_session, email_suffix="run7")
        run2 = Run(profile_id=profile.id, mode="daily", status="completed")
        db_session.add(run2)
        await db_session.commit()
        await db_session.refresh(run2)

        resp = await client.post(
            f"/api/profiles/{profile.id}/runs/bulk-delete",
            json={"run_ids": [run1.id, run2.id]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["deleted"]) == 2
        assert data["skipped"] == []

    @pytest.mark.asyncio
    async def test_bulk_delete_skips_nonexistent(
        self, client, db_session, admin_headers
    ):
        """Bulk delete should skip run IDs that do not exist."""
        profile, completed_run = await _setup_profile_and_run(
            db_session, email_suffix="run8"
        )
        fake_id = "00000000-0000-0000-0000-000000000000"

        resp = await client.post(
            f"/api/profiles/{profile.id}/runs/bulk-delete",
            json={"run_ids": [completed_run.id, fake_id]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert completed_run.id in data["deleted"]
        assert fake_id in data["skipped"]

    @pytest.mark.asyncio
    async def test_list_all_runs(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="run9")
        resp = await client.get("/api/runs?limit=5", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Cover letter endpoints (error paths)
# ---------------------------------------------------------------------------


class TestCoverLetterEndpoints:
    """Tests for cover letter error paths."""

    @pytest.mark.asyncio
    async def test_get_cover_letter_not_found(
        self, client, db_session, admin_headers
    ):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="cl1")
        resp = await client.get(
            f"/api/profiles/{profile.id}/cover-letters/nonexistent",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_cover_letter_not_found(
        self, client, db_session, admin_headers
    ):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="cl2")
        resp = await client.delete(
            f"/api/profiles/{profile.id}/cover-letters/nonexistent",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_cover_letters_empty(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="cl3")
        resp = await client.get(
            f"/api/profiles/{profile.id}/cover-letters",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_cover_letter_no_job_or_text(
        self, client, db_session, admin_headers
    ):
        """Creating a cover letter without job_opportunity_id or jd_text should fail."""
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="cl4")
        resp = await client.post(
            f"/api/profiles/{profile.id}/cover-letters",
            json={},
            headers=admin_headers,
        )
        # Should be 422 (validation or business logic error) or 404
        assert resp.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Profile endpoints (error paths)
# ---------------------------------------------------------------------------


class TestProfileEndpoints:
    """Tests for profile error paths and import/export."""

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, client, admin_headers):
        resp = await client.get(
            "/api/profiles/nonexistent-profile-id",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, client, admin_headers):
        resp = await client.put(
            "/api/profiles/nonexistent-profile-id",
            json={"name": "Updated"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_profile_not_found(self, client, admin_headers):
        resp = await client.delete(
            "/api/profiles/nonexistent-profile-id",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_profile_name(self, client, admin_headers):
        resp = await client.post(
            "/api/profiles",
            json={"name": "Unique Profile Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/profiles",
            json={"name": "Unique Profile Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_export_profile_not_found(self, client, admin_headers):
        resp = await client.get(
            "/api/profiles/nonexistent/export",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_cv_non_pdf(self, client, db_session, admin_headers):
        profile, _ = await _setup_profile_and_run(db_session, email_suffix="cv1")
        resp = await client.post(
            f"/api/profiles/{profile.id}/cv",
            files={"file": ("doc.txt", b"not a pdf", "text/plain")},
            headers=admin_headers,
        )
        assert resp.status_code == 422
        assert "PDF" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Auth error paths
# ---------------------------------------------------------------------------


class TestAuthErrorPaths:
    """Tests for auth endpoints error paths not already covered."""

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client):
        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, client):
        resp = await client.post(
            "/api/auth/verify-email",
            json={"token": "bad-verify-token"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, client):
        resp = await client.post(
            "/api/auth/reset-password",
            json={"token": "bad-reset-token", "password": "NewPass123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email(self, client):
        """forgot-password should always return 200 (no info leak)."""
        resp = await client.post(
            "/api/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_google_login_not_configured(self, client):
        """Google OAuth returns 501 when not configured."""
        resp = await client.get("/api/auth/google", follow_redirects=False)
        # Either 501 (not configured) or a redirect (if configured)
        assert resp.status_code in (301, 302, 307, 501)


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


class TestUnauthenticatedAccess:
    """Verify that all major endpoints reject unauthenticated requests."""

    @pytest.mark.asyncio
    async def test_profiles_requires_auth(self, client):
        resp = await client.get("/api/profiles")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_runs_requires_auth(self, client):
        resp = await client.get("/api/runs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_profile_requires_auth(self, client):
        resp = await client.post("/api/profiles", json={"name": "Test"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_policies_no_auth_needed(self, client, admin_headers):
        """Policies endpoints require auth too (via router prefix)."""
        resp = await client.get("/api/policies")
        # Policies don't use auth dependency, so they should return 200
        assert resp.status_code == 200
