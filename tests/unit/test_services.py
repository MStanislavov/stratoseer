"""Unit tests for all service modules with mocked database sessions."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to create mock ORM instances
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_run(
    id="run-1",
    profile_id="prof-1",
    mode="daily",
    status="completed",
    started_at=_NOW,
    finished_at=_NOW,
    verifier_status="pass",
    created_at=_NOW,
):
    run = MagicMock()
    run.id = id
    run.profile_id = profile_id
    run.mode = mode
    run.status = status
    run.started_at = started_at
    run.finished_at = finished_at
    run.verifier_status = verifier_status
    run.created_at = created_at
    return run


def _make_profile(
    id="prof-1",
    owner_id="user-1",
    name="Architect",
    targets='["backend", "cloud"]',
    constraints='["remote only"]',
    skills='["Python", "AWS"]',
    cv_path=None,
    cv_data=None,
    cv_filename=None,
    cv_summary=None,
    cv_summary_hash=None,
    preferred_titles='["Senior Engineer"]',
    industries='["tech"]',
    locations='["US"]',
    work_arrangement="remote",
    event_attendance="no preference",
    event_topics=None,
    target_certifications=None,
    learning_format=None,
    created_at=_NOW,
    updated_at=_NOW,
):
    p = MagicMock()
    p.id = id
    p.owner_id = owner_id
    p.name = name
    p.targets = targets
    p.constraints = constraints
    p.skills = skills
    p.cv_path = cv_path
    p.cv_data = cv_data
    p.cv_filename = cv_filename
    p.cv_summary = cv_summary
    p.cv_summary_hash = cv_summary_hash
    p.preferred_titles = preferred_titles
    p.industries = industries
    p.locations = locations
    p.work_arrangement = work_arrangement
    p.event_attendance = event_attendance
    p.event_topics = event_topics
    p.target_certifications = target_certifications
    p.learning_format = learning_format
    p.created_at = created_at
    p.updated_at = updated_at
    return p


def _make_user(
    id="user-1",
    first_name="Alice",
    last_name="Test",
    email="alice@test.com",
    password_hash="$hashed$",
    role="user",
    google_id=None,
    email_verified=False,
    encrypted_api_key=None,
    free_runs_used=0,
    created_at=_NOW,
    last_login_at=None,
):
    u = MagicMock()
    u.id = id
    u.first_name = first_name
    u.last_name = last_name
    u.email = email
    u.password_hash = password_hash
    u.role = role
    u.google_id = google_id
    u.email_verified = email_verified
    u.encrypted_api_key = encrypted_api_key
    u.free_runs_used = free_runs_used
    u.created_at = created_at
    u.last_login_at = last_login_at
    return u


def _make_job(
    id="job-1",
    profile_id="prof-1",
    run_id="run-1",
    title="Senior Engineer",
    company="ACME",
    url="https://example.com/job",
    description="Build things",
    location="Remote",
    salary_range="100-150k",
    source_query="python backend",
    created_at=_NOW,
):
    j = MagicMock()
    j.id = id
    j.profile_id = profile_id
    j.run_id = run_id
    j.title = title
    j.company = company
    j.url = url
    j.description = description
    j.location = location
    j.salary_range = salary_range
    j.source_query = source_query
    j.created_at = created_at
    return j


def _make_cover_letter(
    id="cl-1",
    profile_id="prof-1",
    job_opportunity_id="job-1",
    run_id="run-1",
    content="Dear Hiring Manager...",
    created_at=_NOW,
):
    cl = MagicMock()
    cl.id = id
    cl.profile_id = profile_id
    cl.job_opportunity_id = job_opportunity_id
    cl.run_id = run_id
    cl.content = content
    cl.created_at = created_at
    return cl


def _make_refresh_token(
    user_id="user-1",
    token_hash="abc123",
    expires_at=None,
    revoked=False,
):
    rt = MagicMock()
    rt.user_id = user_id
    rt.token_hash = token_hash
    rt.expires_at = expires_at or datetime(2027, 1, 1, tzinfo=timezone.utc)
    rt.revoked = revoked
    return rt


def _mock_db():
    """Create a mock AsyncSession with standard result chains.

    db.add and db.delete are synchronous on a real AsyncSession,
    so use plain MagicMock for those to avoid coroutine warnings.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _mock_execute_result(items):
    """Build a mock result for db.execute().scalars().all() pattern."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    result.scalars.return_value.first.return_value = items[0] if items else None
    return result


def _mock_execute_scalar_one(value):
    """Build a mock result for db.execute().scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    return result


# ===================================================================
# RunService
# ===================================================================

class TestRunToRead:
    def test_converts_run_to_read_schema(self):
        from app.services.run_service import run_to_read

        run = _make_run()
        read = run_to_read(run)
        assert read.id == "run-1"
        assert read.profile_id == "prof-1"
        assert read.mode == "daily"
        assert read.status == "completed"
        assert read.started_at == _NOW
        assert read.finished_at == _NOW
        assert read.verifier_status == "pass"
    def test_handles_none_optional_fields(self):
        from app.services.run_service import run_to_read

        run = _make_run(
            started_at=None, finished_at=None,
            verifier_status=None,
        )
        read = run_to_read(run)
        assert read.started_at is None
        assert read.finished_at is None
        assert read.verifier_status is None


class TestParseProfileHelpers:
    def test_parse_targets_json_list(self):
        from app.services.run_service import _parse_profile_targets

        profile = _make_profile(targets='["a","b"]')
        assert _parse_profile_targets(profile) == ["a", "b"]

    def test_parse_targets_csv_fallback(self):
        from app.services.run_service import _parse_profile_targets

        profile = _make_profile(targets="a, b, c")
        assert _parse_profile_targets(profile) == ["a", "b", "c"]

    def test_parse_targets_none_profile(self):
        from app.services.run_service import _parse_profile_targets

        assert _parse_profile_targets(None) == []

    def test_parse_targets_empty(self):
        from app.services.run_service import _parse_profile_targets

        profile = _make_profile(targets=None)
        assert _parse_profile_targets(profile) == []

    def test_parse_targets_json_single_string(self):
        from app.services.run_service import _parse_profile_targets

        profile = _make_profile(targets='"single"')
        assert _parse_profile_targets(profile) == ["single"]

    def test_parse_skills_json_list(self):
        from app.services.run_service import _parse_profile_skills

        profile = _make_profile(skills='["Python", "Go"]')
        assert _parse_profile_skills(profile) == ["Python", "Go"]

    def test_parse_skills_none(self):
        from app.services.run_service import _parse_profile_skills

        assert _parse_profile_skills(None) == []

    def test_parse_constraints_json_list(self):
        from app.services.run_service import _parse_profile_constraints

        profile = _make_profile(constraints='["remote"]')
        assert _parse_profile_constraints(profile) == ["remote"]

    def test_parse_constraints_csv(self):
        from app.services.run_service import _parse_profile_constraints

        profile = _make_profile(constraints="remote, flexible")
        assert _parse_profile_constraints(profile) == ["remote", "flexible"]


class TestParseJsonList:
    def test_parses_valid_list(self):
        from app.services.run_service import _parse_json_list

        profile = _make_profile(preferred_titles='["A","B"]')
        assert _parse_json_list(profile, "preferred_titles") == ["A", "B"]

    def test_returns_empty_for_none_profile(self):
        from app.services.run_service import _parse_json_list

        assert _parse_json_list(None, "preferred_titles") == []

    def test_returns_empty_for_missing_field(self):
        from app.services.run_service import _parse_json_list

        profile = MagicMock(spec=[])
        assert _parse_json_list(profile, "nonexistent") == []

    def test_returns_empty_for_invalid_json(self):
        from app.services.run_service import _parse_json_list

        profile = _make_profile(preferred_titles="not json")
        assert _parse_json_list(profile, "preferred_titles") == []


class TestListAllRuns:
    async def test_returns_run_reads(self):
        from app.services.run_service import list_all_runs

        db = _mock_db()
        run1, run2 = _make_run(id="r1"), _make_run(id="r2")
        db.execute.return_value = _mock_execute_result([run1, run2])

        result = await list_all_runs(db, limit=10)
        assert len(result) == 2
        assert result[0].id == "r1"
        assert result[1].id == "r2"

    async def test_returns_empty_list(self):
        from app.services.run_service import list_all_runs

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([])
        result = await list_all_runs(db, limit=5)
        assert result == []

    async def test_filters_by_owner_id(self):
        from app.services.run_service import list_all_runs

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([_make_run()])
        result = await list_all_runs(db, limit=10, owner_id="user-1")
        assert len(result) == 1
        db.execute.assert_called_once()


class TestListRuns:
    async def test_returns_runs_for_profile(self):
        from app.services.run_service import list_runs

        db = _mock_db()
        run = _make_run(profile_id="prof-1")
        db.execute.return_value = _mock_execute_result([run])

        result = await list_runs(db, "prof-1")
        assert len(result) == 1
        assert result[0].profile_id == "prof-1"


class TestGetRun:
    async def test_returns_run_read_when_found(self):
        from app.services.run_service import get_run

        db = _mock_db()
        run = _make_run(id="run-1", profile_id="prof-1")
        db.get.return_value = run

        result = await get_run(db, "prof-1", "run-1")
        assert result is not None
        assert result.id == "run-1"

    async def test_returns_none_when_not_found(self):
        from app.services.run_service import get_run

        db = _mock_db()
        db.get.return_value = None
        result = await get_run(db, "prof-1", "run-1")
        assert result is None

    async def test_returns_none_when_wrong_profile(self):
        from app.services.run_service import get_run

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="other-prof")
        result = await get_run(db, "prof-1", "run-1")
        assert result is None


class TestCreateRun:
    async def test_raises_lookup_error_when_profile_missing(self):
        from app.schemas.run import RunCreate
        from app.services.run_service import create_run

        db = _mock_db()
        db.get.return_value = None
        user = _make_user(role="admin")
        body = RunCreate(mode="daily")

        with pytest.raises(LookupError, match="Profile not found"):
            await create_run(db, "prof-1", body, user)

    @patch("app.services.run_service.resolve_api_key", return_value="sk-test")
    async def test_raises_value_error_when_profile_incomplete(self, mock_key):
        from app.schemas.run import RunCreate
        from app.services.run_service import create_run

        db = _mock_db()
        profile = _make_profile(targets=None, skills=None, preferred_titles=None, cv_data=None)
        db.get.return_value = profile
        user = _make_user(role="admin")
        body = RunCreate(mode="daily")

        with pytest.raises(ValueError, match="Profile is incomplete"):
            await create_run(db, "prof-1", body, user)

    @patch("app.services.run_service.resolve_api_key", return_value="sk-test")
    @patch("app.services.run_service.execute_run", new_callable=AsyncMock)
    @patch("app.services.run_service.asyncio")
    async def test_creates_run_successfully(self, mock_asyncio, mock_exec, mock_key):
        from app.schemas.run import RunCreate
        from app.services.run_service import create_run

        db = _mock_db()
        profile = _make_profile(cv_data=b"fake-pdf")
        db.get.return_value = profile

        mock_run = _make_run(id="new-run", status="pending")
        # After db.commit + db.refresh, the run should have an id
        async def _refresh(obj):
            obj.id = "new-run"
            obj.profile_id = "prof-1"
            obj.mode = "daily"
            obj.status = "pending"
            obj.started_at = None
            obj.finished_at = None
            obj.verifier_status = None
            pass

        db.refresh = AsyncMock(side_effect=_refresh)

        mock_task = MagicMock()
        mock_asyncio.create_task.return_value = mock_task

        user = _make_user(role="admin")
        body = RunCreate(mode="daily")
        result = await create_run(db, "prof-1", body, user)

        assert result.status == "pending"
        db.add.assert_called_once()
        db.commit.assert_called_once()


class TestCancelRun:
    async def test_raises_lookup_error_when_not_found(self):
        from app.services.run_service import cancel_run

        db = _mock_db()
        db.get.return_value = None
        with pytest.raises(LookupError, match="Run not found"):
            await cancel_run(db, "prof-1", "run-1")

    async def test_raises_lookup_error_when_wrong_profile(self):
        from app.services.run_service import cancel_run

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="other")
        with pytest.raises(LookupError, match="Run not found"):
            await cancel_run(db, "prof-1", "run-1")

    @patch("app.services.run_service._running_tasks", {})
    async def test_cancels_active_task(self):
        from app.services.run_service import _running_tasks, cancel_run

        db = _mock_db()
        run = _make_run(id="run-1", profile_id="prof-1", status="running")
        db.get.return_value = run

        mock_task = MagicMock()
        mock_task.done.return_value = False
        _running_tasks["run-1"] = mock_task

        result = await cancel_run(db, "prof-1", "run-1")
        mock_task.cancel.assert_called_once()
        assert result["detail"] == "Cancellation requested"

    @patch("app.services.run_service._running_tasks", {})
    async def test_marks_orphaned_run_cancelled(self):
        from app.services.run_service import cancel_run

        db = _mock_db()
        run = _make_run(id="run-1", profile_id="prof-1", status="running")
        db.get.return_value = run

        result = await cancel_run(db, "prof-1", "run-1")
        assert "Orphaned" in result["detail"]
        assert run.status == "cancelled"
        db.commit.assert_called_once()

    @patch("app.services.run_service._running_tasks", {})
    async def test_raises_when_not_executing(self):
        from app.services.run_service import cancel_run

        db = _mock_db()
        run = _make_run(id="run-1", profile_id="prof-1", status="completed")
        db.get.return_value = run

        with pytest.raises(ValueError, match="not currently executing"):
            await cancel_run(db, "prof-1", "run-1")


class TestDeleteRun:
    async def test_raises_lookup_error_when_not_found(self):
        from app.services.run_service import delete_run

        db = _mock_db()
        db.get.return_value = None
        with pytest.raises(LookupError, match="Run not found"):
            await delete_run(db, "prof-1", "run-1")

    @patch("app.services.run_service._running_tasks", {})
    async def test_raises_when_still_executing(self):
        from app.services.run_service import _running_tasks, delete_run

        db = _mock_db()
        run = _make_run(id="run-1", profile_id="prof-1", status="running")
        db.get.return_value = run

        task = MagicMock()
        task.done.return_value = False
        _running_tasks["run-1"] = task

        with pytest.raises(ValueError, match="still executing"):
            await delete_run(db, "prof-1", "run-1")

    @patch("app.services.run_service._running_tasks", {})
    @patch("app.services.run_service.asyncio")
    async def test_deletes_run_and_results(self, mock_asyncio):
        from app.services.run_service import delete_run

        mock_asyncio.to_thread = AsyncMock()
        db = _mock_db()
        run = _make_run(id="run-1", profile_id="prof-1", status="completed")
        db.get.return_value = run

        result = await delete_run(db, "prof-1", "run-1")
        assert result is True
        db.delete.assert_called_once_with(run)
        db.commit.assert_called_once()
        # Should have called execute multiple times for cascading deletes
        assert db.execute.call_count >= 3


class TestBulkDeleteRuns:
    @patch("app.services.run_service.delete_run", new_callable=AsyncMock)
    async def test_deletes_valid_skips_invalid(self, mock_delete):
        from app.services.run_service import bulk_delete_runs

        mock_delete.side_effect = [None, LookupError("not found"), None]
        db = _mock_db()

        result = await bulk_delete_runs(db, "prof-1", ["r1", "r2", "r3"])
        assert result["deleted"] == ["r1", "r3"]
        assert result["skipped"] == ["r2"]

    @patch("app.services.run_service.delete_run", new_callable=AsyncMock)
    async def test_all_skipped(self, mock_delete):
        from app.services.run_service import bulk_delete_runs

        mock_delete.side_effect = ValueError("executing")
        db = _mock_db()

        result = await bulk_delete_runs(db, "prof-1", ["r1"])
        assert result["deleted"] == []
        assert result["skipped"] == ["r1"]


class TestBuildGraph:
    def test_defaults_to_daily(self):
        from app.services.run_service import _build_graph

        with patch("app.services.run_service.build_daily_graph") as mock_daily:
            mock_daily.return_value = MagicMock()
            _build_graph("daily", MagicMock(), MagicMock(), MagicMock())
            mock_daily.assert_called_once()

    def test_selects_weekly_builder(self):
        from app.services.run_service import _build_graph

        with patch("app.services.run_service.build_weekly_graph") as mock_weekly:
            mock_weekly.return_value = MagicMock()
            _build_graph("weekly", MagicMock(), MagicMock(), MagicMock())
            mock_weekly.assert_called_once()

    def test_selects_cover_letter_builder(self):
        from app.services.run_service import _build_graph

        with patch("app.services.run_service.build_cover_letter_graph") as mock_cl:
            mock_cl.return_value = MagicMock()
            _build_graph("cover_letter", MagicMock(), MagicMock(), MagicMock())
            mock_cl.assert_called_once()

    def test_unknown_mode_falls_back_to_daily(self):
        from app.services.run_service import _build_graph

        with patch("app.services.run_service.build_daily_graph") as mock_daily:
            mock_daily.return_value = MagicMock()
            _build_graph("unknown_mode", MagicMock(), MagicMock(), MagicMock())
            mock_daily.assert_called_once()


# ===================================================================
# AuthService
# ===================================================================

class TestRegisterUser:
    @patch("app.services.auth_service.send_verification_email")
    @patch("app.services.auth_service.create_email_verify_token", return_value="vtok")
    @patch("app.services.auth_service.create_refresh_token", return_value="rt-new")
    @patch("app.services.auth_service.create_access_token", return_value="at-new")
    @patch("app.services.auth_service.hash_password", return_value="$hashed$")
    async def test_first_user_becomes_admin(
        self, mock_hash, mock_at, mock_rt, mock_vt, mock_send
    ):
        from app.schemas.auth import RegisterRequest
        from app.services.auth_service import register_user

        db = _mock_db()
        # Email not taken
        db.execute.side_effect = [
            _mock_execute_scalar_one(None),   # email check
            _mock_execute_scalar_one(0),       # user count = 0
            MagicMock(),                       # _store_refresh_token decode
        ]

        # Mock _store_refresh_token's inner decode_token
        with patch("app.services.auth_service._store_refresh_token", new_callable=AsyncMock):
            body = RegisterRequest(
                first_name="A", last_name="B",
                email="a@b.com", password="Password1",
            )
            user, access, refresh = await register_user(db, body)

        assert access == "at-new"
        assert refresh == "rt-new"
        db.add.assert_called_once()

    async def test_duplicate_email_raises(self):
        from app.schemas.auth import RegisterRequest
        from app.services.auth_service import register_user

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(_make_user())

        body = RegisterRequest(
            first_name="A", last_name="B",
            email="a@b.com", password="Password1",
        )
        with pytest.raises(ValueError, match="Email already registered"):
            await register_user(db, body)


class TestLoginUser:
    @patch("app.services.auth_service._store_refresh_token", new_callable=AsyncMock)
    @patch("app.services.auth_service.create_refresh_token", return_value="rt")
    @patch("app.services.auth_service.create_access_token", return_value="at")
    @patch("app.services.auth_service.verify_password", return_value=True)
    async def test_valid_credentials(self, mock_verify, mock_at, mock_rt, mock_store):
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import login_user

        db = _mock_db()
        user = _make_user()
        db.execute.return_value = _mock_execute_scalar_one(user)

        body = LoginRequest(email="alice@test.com", password="Password1")
        returned_user, access, refresh = await login_user(db, body)

        assert access == "at"
        assert refresh == "rt"
        assert returned_user is user

    async def test_invalid_email(self):
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import login_user

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)

        body = LoginRequest(email="bad@test.com", password="Pass1")
        with pytest.raises(ValueError, match="Invalid email or password"):
            await login_user(db, body)

    @patch("app.services.auth_service.verify_password", return_value=False)
    async def test_wrong_password(self, mock_verify):
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import login_user

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(_make_user())

        body = LoginRequest(email="alice@test.com", password="WrongPass1")
        with pytest.raises(ValueError, match="Invalid email or password"):
            await login_user(db, body)

    async def test_user_with_no_password_hash(self):
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import login_user

        db = _mock_db()
        user = _make_user(password_hash=None)
        db.execute.return_value = _mock_execute_scalar_one(user)

        body = LoginRequest(email="alice@test.com", password="Pass1")
        with pytest.raises(ValueError, match="Invalid email or password"):
            await login_user(db, body)


class TestRefreshTokens:
    @patch("app.services.auth_service._store_refresh_token", new_callable=AsyncMock)
    @patch("app.services.auth_service.create_refresh_token", return_value="rt-new")
    @patch("app.services.auth_service.create_access_token", return_value="at-new")
    @patch("app.services.auth_service.decode_token")
    async def test_valid_refresh(self, mock_decode, mock_at, mock_rt, mock_store):
        from app.services.auth_service import refresh_tokens

        mock_decode.return_value = {"sub": "user-1", "type": "refresh", "exp": 9999999999}
        db = _mock_db()

        stored_rt = _make_refresh_token()
        user = _make_user()
        db.execute.side_effect = [
            _mock_execute_scalar_one(stored_rt),  # find stored token
            _mock_execute_scalar_one(user),        # find user
            MagicMock(),                            # store new token
        ]

        new_access, new_refresh = await refresh_tokens(db, "old-rt")
        assert new_access == "at-new"
        assert new_refresh == "rt-new"
        assert stored_rt.revoked is True

    @patch("app.services.auth_service.decode_token", side_effect=Exception("bad"))
    async def test_invalid_token_raises(self, mock_decode):
        from jose import JWTError

        # Patch to raise JWTError specifically
        with patch("app.services.auth_service.decode_token", side_effect=JWTError("bad")):
            from app.services.auth_service import refresh_tokens

            db = _mock_db()
            with pytest.raises(ValueError, match="Invalid refresh token"):
                await refresh_tokens(db, "bad-token")

    @patch("app.services.auth_service.decode_token")
    async def test_wrong_token_type_raises(self, mock_decode):
        from app.services.auth_service import refresh_tokens

        mock_decode.return_value = {"type": "access", "sub": "u1"}
        db = _mock_db()
        with pytest.raises(ValueError, match="Invalid token type"):
            await refresh_tokens(db, "some-token")

    @patch("app.services.auth_service.decode_token")
    async def test_revoked_token_raises(self, mock_decode):
        from app.services.auth_service import refresh_tokens

        mock_decode.return_value = {"type": "refresh", "sub": "u1", "exp": 9999999999}
        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)

        with pytest.raises(ValueError, match="Token revoked or not found"):
            await refresh_tokens(db, "revoked-rt")

    @patch("app.services.auth_service.decode_token")
    async def test_expired_stored_token_raises(self, mock_decode):
        from app.services.auth_service import refresh_tokens

        mock_decode.return_value = {"type": "refresh", "sub": "u1", "exp": 9999999999}
        db = _mock_db()
        rt = _make_refresh_token(expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        db.execute.return_value = _mock_execute_scalar_one(rt)

        with pytest.raises(ValueError, match="Token expired"):
            await refresh_tokens(db, "expired-rt")

    @patch("app.services.auth_service.decode_token")
    async def test_user_not_found_after_revoke_raises(self, mock_decode):
        from app.services.auth_service import refresh_tokens

        mock_decode.return_value = {"type": "refresh", "sub": "u-gone", "exp": 9999999999}
        db = _mock_db()
        stored_rt = _make_refresh_token()
        db.execute.side_effect = [
            _mock_execute_scalar_one(stored_rt),
            _mock_execute_scalar_one(None),  # user not found
        ]

        with pytest.raises(ValueError, match="User not found"):
            await refresh_tokens(db, "some-rt")


class TestLogoutUser:
    async def test_revokes_token(self):
        from app.services.auth_service import logout_user

        db = _mock_db()
        stored_rt = _make_refresh_token()
        db.execute.return_value = _mock_execute_scalar_one(stored_rt)

        await logout_user(db, "rt-value")
        assert stored_rt.revoked is True
        db.commit.assert_called_once()

    async def test_noop_when_token_not_found(self):
        from app.services.auth_service import logout_user

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)

        await logout_user(db, "nonexistent")
        db.commit.assert_not_called()


class TestGoogleLogin:
    @patch("app.services.auth_service._store_refresh_token", new_callable=AsyncMock)
    @patch("app.services.auth_service.create_refresh_token", return_value="rt")
    @patch("app.services.auth_service.create_access_token", return_value="at")
    async def test_existing_user_by_google_id(self, mock_at, mock_rt, mock_store):
        from app.services.auth_service import google_login

        db = _mock_db()
        user = _make_user(google_id="g-123")
        db.execute.return_value = _mock_execute_scalar_one(user)

        google_info = {"google_id": "g-123", "email": "a@g.com"}
        returned_user, access, refresh = await google_login(db, google_info)
        assert access == "at"
        assert returned_user is user

    @patch("app.services.auth_service._store_refresh_token", new_callable=AsyncMock)
    @patch("app.services.auth_service.create_refresh_token", return_value="rt")
    @patch("app.services.auth_service.create_access_token", return_value="at")
    async def test_links_existing_email_account(self, mock_at, mock_rt, mock_store):
        from app.services.auth_service import google_login

        db = _mock_db()
        user = _make_user(google_id=None)
        # First query: no user by google_id; second query: user by email
        db.execute.side_effect = [
            _mock_execute_scalar_one(None),
            _mock_execute_scalar_one(user),
            MagicMock(),  # store rt
        ]

        google_info = {"google_id": "g-new", "email": "alice@test.com", "email_verified": True}
        returned_user, _, _ = await google_login(db, google_info)
        assert returned_user.google_id == "g-new"
        assert returned_user.email_verified is True

    @patch("app.services.auth_service._store_refresh_token", new_callable=AsyncMock)
    @patch("app.services.auth_service.create_refresh_token", return_value="rt")
    @patch("app.services.auth_service.create_access_token", return_value="at")
    async def test_creates_new_user_as_admin_if_first(self, mock_at, mock_rt, mock_store):
        from app.services.auth_service import google_login

        db = _mock_db()
        # No user by google_id, no user by email, user count = 0
        db.execute.side_effect = [
            _mock_execute_scalar_one(None),   # google_id lookup
            _mock_execute_scalar_one(None),   # email lookup
            _mock_execute_scalar_one(0),      # user count
            MagicMock(),                       # store rt
        ]

        google_info = {
            "google_id": "g-brand-new",
            "email": "new@test.com",
            "first_name": "New",
            "last_name": "User",
            "email_verified": True,
        }
        # The db.flush needs to work on the newly-created user mock
        async def _flush():
            pass

        db.flush = AsyncMock(side_effect=_flush)
        _, access, _ = await google_login(db, google_info)
        assert access == "at"
        db.add.assert_called_once()


class TestVerifyEmail:
    @patch("app.services.auth_service.decode_token")
    async def test_verifies_email(self, mock_decode):
        from app.services.auth_service import verify_email

        mock_decode.return_value = {"type": "email_verify", "sub": "u1"}
        db = _mock_db()
        user = _make_user(email_verified=False)
        db.execute.return_value = _mock_execute_scalar_one(user)

        await verify_email(db, "vtok")
        assert user.email_verified is True
        db.commit.assert_called_once()

    @patch("app.services.auth_service.decode_token")
    async def test_wrong_type_raises(self, mock_decode):
        from app.services.auth_service import verify_email

        mock_decode.return_value = {"type": "access", "sub": "u1"}
        db = _mock_db()
        with pytest.raises(ValueError, match="Invalid token type"):
            await verify_email(db, "bad-tok")

    async def test_bad_token_raises(self):
        from jose import JWTError

        with patch("app.services.auth_service.decode_token", side_effect=JWTError("x")):
            from app.services.auth_service import verify_email

            db = _mock_db()
            with pytest.raises(ValueError, match="Invalid or expired"):
                await verify_email(db, "bad")

    @patch("app.services.auth_service.decode_token")
    async def test_user_not_found_raises(self, mock_decode):
        from app.services.auth_service import verify_email

        mock_decode.return_value = {"type": "email_verify", "sub": "u-gone"}
        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)

        with pytest.raises(ValueError, match="User not found"):
            await verify_email(db, "tok")


class TestForgotPassword:
    @patch("app.services.auth_service.send_password_reset_email")
    @patch("app.services.auth_service.create_password_reset_token", return_value="rst-tok")
    async def test_sends_email_when_user_exists(self, mock_tok, mock_send):
        from app.services.auth_service import forgot_password

        db = _mock_db()
        user = _make_user()
        db.execute.return_value = _mock_execute_scalar_one(user)

        await forgot_password(db, "alice@test.com")
        mock_send.assert_called_once_with("alice@test.com", "rst-tok")

    async def test_silent_when_user_not_found(self):
        from app.services.auth_service import forgot_password

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)
        # Should not raise
        await forgot_password(db, "nonexistent@test.com")

    @patch("app.services.auth_service.send_password_reset_email", side_effect=Exception("smtp"))
    @patch("app.services.auth_service.create_password_reset_token", return_value="tok")
    async def test_suppresses_email_error(self, mock_tok, mock_send):
        from app.services.auth_service import forgot_password

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(_make_user())
        # Should not raise despite email failure
        await forgot_password(db, "alice@test.com")


class TestResetPassword:
    @patch("app.services.auth_service.hash_password", return_value="$new_hash$")
    @patch("app.services.auth_service.decode_token")
    async def test_resets_password(self, mock_decode, mock_hash):
        from app.services.auth_service import reset_password

        mock_decode.return_value = {"type": "password_reset", "sub": "u1"}
        db = _mock_db()
        user = _make_user()
        db.execute.return_value = _mock_execute_scalar_one(user)

        await reset_password(db, "rst-tok", "NewPass123")
        assert user.password_hash == "$new_hash$"
        db.commit.assert_called_once()

    @patch("app.services.auth_service.decode_token")
    async def test_wrong_type_raises(self, mock_decode):
        from app.services.auth_service import reset_password

        mock_decode.return_value = {"type": "access", "sub": "u1"}
        db = _mock_db()
        with pytest.raises(ValueError, match="Invalid token type"):
            await reset_password(db, "tok", "NewPass1")

    async def test_bad_token_raises(self):
        from jose import JWTError

        with patch("app.services.auth_service.decode_token", side_effect=JWTError("x")):
            from app.services.auth_service import reset_password

            db = _mock_db()
            with pytest.raises(ValueError, match="Invalid or expired"):
                await reset_password(db, "bad", "Pass1")

    @patch("app.services.auth_service.decode_token")
    async def test_user_not_found_raises(self, mock_decode):
        from app.services.auth_service import reset_password

        mock_decode.return_value = {"type": "password_reset", "sub": "u-gone"}
        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)

        with pytest.raises(ValueError, match="User not found"):
            await reset_password(db, "tok", "Pass1")


# ===================================================================
# CoverLetterService
# ===================================================================

class TestClToRead:
    def test_converts_with_job(self):
        from app.services.cover_letter_service import cl_to_read

        cl = _make_cover_letter()
        job = _make_job()
        read = cl_to_read(cl, job)
        assert read.id == "cl-1"
        assert read.job_title == "Senior Engineer"
        assert read.job_company == "ACME"
        assert read.job_url == "https://example.com/job"

    def test_converts_without_job(self):
        from app.services.cover_letter_service import cl_to_read

        cl = _make_cover_letter()
        read = cl_to_read(cl, None)
        assert read.job_title is None
        assert read.job_company is None
        assert read.job_url is None


class TestResolveJobOpportunity:
    async def test_returns_empty_when_no_id(self):
        from app.services.cover_letter_service import resolve_job_opportunity

        db = _mock_db()
        job_dict, jd, job_orm = await resolve_job_opportunity(db, None, "prof-1", "some jd")
        assert job_dict == {}
        assert jd == "some jd"
        assert job_orm is None

    async def test_returns_job_details(self):
        from app.services.cover_letter_service import resolve_job_opportunity

        db = _mock_db()
        job = _make_job()
        db.get.return_value = job

        job_dict, jd, job_orm = await resolve_job_opportunity(
            db, "job-1", "prof-1", ""
        )
        assert job_dict["title"] == "Senior Engineer"
        assert jd == "Build things"  # falls back to description
        assert job_orm is job

    async def test_raises_when_job_not_found(self):
        from app.services.cover_letter_service import resolve_job_opportunity

        db = _mock_db()
        db.get.return_value = None
        with pytest.raises(LookupError, match="Job opportunity not found"):
            await resolve_job_opportunity(db, "bad-id", "prof-1", "")

    async def test_raises_when_wrong_profile(self):
        from app.services.cover_letter_service import resolve_job_opportunity

        db = _mock_db()
        db.get.return_value = _make_job(profile_id="other-prof")
        with pytest.raises(LookupError, match="Job opportunity not found"):
            await resolve_job_opportunity(db, "job-1", "prof-1", "")

    async def test_preserves_explicit_jd_text(self):
        from app.services.cover_letter_service import resolve_job_opportunity

        db = _mock_db()
        db.get.return_value = _make_job()
        _, jd, _ = await resolve_job_opportunity(db, "job-1", "prof-1", "Custom JD")
        assert jd == "Custom JD"


class TestReadCvContent:
    @patch("app.services.profile_service.extract_text_from_pdf", return_value="CV text here")
    async def test_extracts_text_from_cv(self, mock_extract):
        from app.services.cover_letter_service import read_cv_content

        result = await read_cv_content(b"pdf-bytes")
        assert result == "CV text here"

    async def test_falls_back_to_skills(self):
        from app.services.cover_letter_service import read_cv_content

        result = await read_cv_content(None, skills_fallback="Python, Go")
        assert result == "Python, Go"

    @patch(
        "app.services.profile_service.extract_text_from_pdf",
        side_effect=Exception("bad pdf"),
    )
    async def test_falls_back_on_exception(self, mock_extract):
        from app.services.cover_letter_service import read_cv_content

        result = await read_cv_content(b"bad-bytes", skills_fallback="fallback")
        assert result == "fallback"


class TestCreateCoverLetter:
    async def test_raises_when_profile_not_found(self):
        from app.schemas.cover_letter import CoverLetterCreate
        from app.services.cover_letter_service import create_cover_letter

        db = _mock_db()
        db.get.return_value = None
        user = _make_user(role="admin")
        body = CoverLetterCreate(jd_text="Build things")

        with pytest.raises(LookupError, match="Profile not found"):
            await create_cover_letter(db, "prof-1", body, user)

    @patch("app.services.api_key_service.resolve_api_key", return_value="sk-test")
    async def test_raises_when_no_cv(self, mock_key):
        from app.schemas.cover_letter import CoverLetterCreate
        from app.services.cover_letter_service import create_cover_letter

        db = _mock_db()
        profile = _make_profile(cv_data=None)
        db.get.return_value = profile
        user = _make_user(role="admin")
        body = CoverLetterCreate(jd_text="Build things")

        with pytest.raises(ValueError, match="upload a CV"):
            await create_cover_letter(db, "prof-1", body, user)

    @patch("app.services.api_key_service.resolve_api_key", return_value="sk-test")
    async def test_raises_when_no_jd_and_no_job_id(self, mock_key):
        from app.schemas.cover_letter import CoverLetterCreate
        from app.services.cover_letter_service import create_cover_letter

        db = _mock_db()
        profile = _make_profile(cv_data=b"pdf-content")
        db.get.return_value = profile
        user = _make_user(role="admin")
        body = CoverLetterCreate()

        with pytest.raises(ValueError, match="job_opportunity_id or jd_text"):
            await create_cover_letter(db, "prof-1", body, user)


class TestListCoverLetters:
    async def test_returns_cover_letters_with_jobs(self):
        from app.services.cover_letter_service import list_cover_letters

        db = _mock_db()
        cl = _make_cover_letter()
        job = _make_job()
        mock_result = MagicMock()
        mock_result.all.return_value = [(cl, job)]
        db.execute.return_value = mock_result

        result = await list_cover_letters(db, "prof-1")
        assert len(result) == 1
        assert result[0].job_title == "Senior Engineer"

    async def test_returns_empty(self):
        from app.services.cover_letter_service import list_cover_letters

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        result = await list_cover_letters(db, "prof-1")
        assert result == []


class TestGetCoverLetter:
    async def test_returns_cover_letter(self):
        from app.services.cover_letter_service import get_cover_letter

        db = _mock_db()
        cl = _make_cover_letter()
        job = _make_job()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (cl, job)
        db.execute.return_value = mock_result

        result = await get_cover_letter(db, "prof-1", "cl-1")
        assert result is not None
        assert result.id == "cl-1"

    async def test_returns_none_when_not_found(self):
        from app.services.cover_letter_service import get_cover_letter

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await get_cover_letter(db, "prof-1", "cl-missing")
        assert result is None


class TestDeleteCoverLetter:
    async def test_deletes_cover_letter(self):
        from app.services.cover_letter_service import delete_cover_letter

        db = _mock_db()
        cl = _make_cover_letter(profile_id="prof-1")
        db.get.return_value = cl

        result = await delete_cover_letter(db, "prof-1", "cl-1")
        assert result is True
        db.delete.assert_called_once_with(cl)
        db.commit.assert_called_once()

    async def test_returns_false_when_not_found(self):
        from app.services.cover_letter_service import delete_cover_letter

        db = _mock_db()
        db.get.return_value = None

        result = await delete_cover_letter(db, "prof-1", "cl-missing")
        assert result is False

    async def test_returns_false_when_wrong_profile(self):
        from app.services.cover_letter_service import delete_cover_letter

        db = _mock_db()
        db.get.return_value = _make_cover_letter(profile_id="other-prof")

        result = await delete_cover_letter(db, "prof-1", "cl-1")
        assert result is False


# ===================================================================
# AuditService
# ===================================================================

class TestGetRunOrRaise:
    async def test_returns_run(self):
        from app.services.audit_service import _get_run_or_raise

        db = _mock_db()
        run = _make_run(profile_id="prof-1")
        db.get.return_value = run

        result = await _get_run_or_raise(db, "run-1", "prof-1")
        assert result is run

    async def test_raises_when_not_found(self):
        from app.services.audit_service import _get_run_or_raise

        db = _mock_db()
        db.get.return_value = None
        with pytest.raises(LookupError, match="Run not found"):
            await _get_run_or_raise(db, "run-1", "prof-1")

    async def test_raises_when_wrong_profile(self):
        from app.services.audit_service import _get_run_or_raise

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="other")
        with pytest.raises(LookupError, match="Run not found"):
            await _get_run_or_raise(db, "run-1", "prof-1")


class TestGetAuditTrail:
    @patch("app.services.audit_service.AuditWriter")
    async def test_returns_events(self, mock_writer_cls):
        from app.services.audit_service import get_audit_trail

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_log = AsyncMock(return_value=[{"event_type": "agent_start"}])
        mock_writer_cls.return_value = mock_writer

        result = await get_audit_trail(db, "prof-1", "run-1")
        assert result["run_id"] == "run-1"
        assert len(result["events"]) == 1


class TestGetVerifierReport:
    @patch("app.services.audit_service.AuditWriter")
    async def test_returns_report(self, mock_writer_cls):
        from app.services.audit_service import get_verifier_report

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_bundle = AsyncMock(
            return_value={"verifier_report": {"status": "pass"}}
        )
        mock_writer_cls.return_value = mock_writer

        result = await get_verifier_report(db, "prof-1", "run-1")
        assert result["status"] == "pass"

    @patch("app.services.audit_service.AuditWriter")
    async def test_raises_when_no_bundle(self, mock_writer_cls):
        from app.services.audit_service import get_verifier_report

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_bundle = AsyncMock(return_value=None)
        mock_writer_cls.return_value = mock_writer

        with pytest.raises(LookupError, match="No audit bundle"):
            await get_verifier_report(db, "prof-1", "run-1")


class TestGetExecutiveInsights:
    @patch("app.services.audit_service.AuditWriter")
    async def test_returns_insights(self, mock_writer_cls):
        from app.services.audit_service import get_executive_insights

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_bundle = AsyncMock(return_value={
            "final_artifacts": {
                "strategic_recommendations": ["hire more"],
                "ceo_summary": "All good",
                "risk_assessments": ["low risk"],
                "cfo_summary": "Budget ok",
            }
        })
        mock_writer_cls.return_value = mock_writer

        result = await get_executive_insights(db, "prof-1", "run-1")
        assert result["ceo_summary"] == "All good"
        assert result["cfo_summary"] == "Budget ok"
        assert len(result["strategic_recommendations"]) == 1

    @patch("app.services.audit_service.AuditWriter")
    async def test_raises_when_no_bundle(self, mock_writer_cls):
        from app.services.audit_service import get_executive_insights

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_bundle = AsyncMock(return_value=None)
        mock_writer_cls.return_value = mock_writer

        with pytest.raises(LookupError, match="No audit bundle"):
            await get_executive_insights(db, "prof-1", "run-1")


class TestGetTokenUsage:
    @patch("app.services.audit_service.AuditWriter")
    async def test_returns_usage_data(self, mock_writer_cls):
        from app.services.audit_service import get_token_usage

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        usage_data = {"total_tokens": 5000, "agents": {}}
        mock_writer = MagicMock()
        mock_writer.read_log = AsyncMock(return_value=[
            {"event_type": "agent_start", "data": {}},
            {"event_type": "token_usage_summary", "data": usage_data},
        ])
        mock_writer_cls.return_value = mock_writer

        result = await get_token_usage(db, "prof-1", "run-1")
        assert result["total_tokens"] == 5000

    @patch("app.services.audit_service.AuditWriter")
    async def test_raises_when_no_usage(self, mock_writer_cls):
        from app.services.audit_service import get_token_usage

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_log = AsyncMock(return_value=[
            {"event_type": "agent_start", "data": {}},
        ])
        mock_writer_cls.return_value = mock_writer

        with pytest.raises(LookupError, match="No token usage data"):
            await get_token_usage(db, "prof-1", "run-1")


class TestDiffRuns:
    @patch("app.services.audit_service.DiffEngine")
    @patch("app.services.audit_service.AuditWriter")
    async def test_returns_diff(self, mock_writer_cls, mock_diff_cls):
        from app.services.audit_service import diff_runs

        db = _mock_db()
        run1 = _make_run(id="run-1", profile_id="prof-1")
        run2 = _make_run(id="run-2", profile_id="prof-1")
        db.get.side_effect = [run1, run2]

        mock_diff = MagicMock()
        mock_diff.diff_runs = AsyncMock(return_value={"changes": []})
        mock_diff_cls.return_value = mock_diff

        result = await diff_runs(db, "prof-1", "run-1", "run-2")
        assert result == {"changes": []}

    async def test_raises_when_first_run_not_found(self):
        from app.services.audit_service import diff_runs

        db = _mock_db()
        db.get.return_value = None
        with pytest.raises(LookupError):
            await diff_runs(db, "prof-1", "run-bad", "run-2")


class TestReplayRun:
    @patch("app.services.audit_service.AuditWriter")
    @patch("app.services.audit_service.ReplayEngine")
    async def test_strict_replay(self, mock_replay_cls, mock_writer_cls):
        from app.services.audit_service import replay_run

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_replay = MagicMock()
        mock_replay.replay_strict = AsyncMock(return_value={"result": {}})
        mock_replay_cls.return_value = mock_replay

        mock_writer = MagicMock()
        mock_writer.create_run_bundle = AsyncMock()
        mock_writer_cls.return_value = mock_writer

        result = await replay_run(db, "prof-1", "run-1", "strict")
        assert result == {"result": {}}
        mock_replay.replay_strict.assert_called_once()

    @patch("app.services.audit_service.AuditWriter")
    @patch("app.services.audit_service.ReplayEngine")
    async def test_refresh_replay(self, mock_replay_cls, mock_writer_cls):
        from app.services.audit_service import replay_run

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_bundle = AsyncMock(
            return_value={"final_artifacts": {"data": "old"}}
        )
        mock_writer.create_run_bundle = AsyncMock()
        mock_writer_cls.return_value = mock_writer

        mock_replay = MagicMock()
        mock_replay.replay_refresh = AsyncMock(return_value={"result": {}})
        mock_replay_cls.return_value = mock_replay

        result = await replay_run(db, "prof-1", "run-1", "refresh")
        assert result == {"result": {}}
        mock_replay.replay_refresh.assert_called_once()

    @patch("app.services.audit_service.AuditWriter")
    @patch("app.services.audit_service.ReplayEngine")
    async def test_refresh_raises_when_no_bundle(self, mock_replay_cls, mock_writer_cls):
        from app.services.audit_service import replay_run

        db = _mock_db()
        db.get.return_value = _make_run(profile_id="prof-1")

        mock_writer = MagicMock()
        mock_writer.read_bundle = AsyncMock(return_value=None)
        mock_writer_cls.return_value = mock_writer

        with pytest.raises(LookupError, match="No audit bundle"):
            await replay_run(db, "prof-1", "run-1", "refresh")


# ===================================================================
# PolicyService
# ===================================================================

class TestListPolicies:
    @patch("app.services.policy_service.settings")
    def test_returns_policies(self, mock_settings, tmp_path):
        from app.services.policy_service import list_policies

        # Create temp yaml files
        policy_dir = tmp_path / "policy"
        policy_dir.mkdir()
        (policy_dir / "budgets.yaml").write_text("max_tokens: 1000")
        (policy_dir / "sources.yaml").write_text("sources: []")
        mock_settings.policy_dir = policy_dir

        policies = list_policies()
        assert len(policies) == 2
        names = {p.name for p in policies}
        assert "budgets" in names
        assert "sources" in names

    @patch("app.services.policy_service.settings")
    def test_returns_empty_when_dir_missing(self, mock_settings, tmp_path):
        from app.services.policy_service import list_policies

        mock_settings.policy_dir = tmp_path / "nonexistent"
        assert list_policies() == []


class TestGetPolicy:
    @patch("app.services.policy_service.settings")
    def test_returns_policy(self, mock_settings, tmp_path):
        from app.services.policy_service import get_policy

        policy_dir = tmp_path / "policy"
        policy_dir.mkdir()
        (policy_dir / "budgets.yaml").write_text("max_tokens: 1000")
        mock_settings.policy_dir = policy_dir

        result = get_policy("budgets")
        assert result is not None
        assert result.name == "budgets"
        assert result.content["max_tokens"] == 1000

    @patch("app.services.policy_service.settings")
    def test_returns_none_when_not_found(self, mock_settings, tmp_path):
        from app.services.policy_service import get_policy

        mock_settings.policy_dir = tmp_path / "policy"
        assert get_policy("nonexistent") is None


# ===================================================================
# ResultService
# ===================================================================

class TestListJobs:
    async def test_returns_jobs(self):
        from app.services.result_service import list_jobs

        db = _mock_db()
        job = _make_job()
        db.execute.return_value = _mock_execute_result([job])

        result = await list_jobs(db, "prof-1")
        assert len(result) == 1
        assert result[0].title == "Senior Engineer"

    async def test_filters_by_run_id(self):
        from app.services.result_service import list_jobs

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([])

        result = await list_jobs(db, "prof-1", run_id="run-1")
        assert result == []
        db.execute.assert_called_once()

    async def test_returns_empty(self):
        from app.services.result_service import list_jobs

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([])
        result = await list_jobs(db, "prof-1")
        assert result == []


class TestListCertifications:
    async def test_returns_certifications(self):
        from app.services.result_service import list_certifications

        db = _mock_db()
        cert = MagicMock(
            id="c1", profile_id="prof-1", run_id="run-1",
            title="AWS SA", provider="Amazon", url="https://aws.com",
            description="Cloud cert", cost="$300", duration="3 months",
            created_at=_NOW,
        )
        db.execute.return_value = _mock_execute_result([cert])

        result = await list_certifications(db, "prof-1")
        assert len(result) == 1
        assert result[0].title == "AWS SA"


class TestListCourses:
    async def test_returns_courses(self):
        from app.services.result_service import list_courses

        db = _mock_db()
        course = MagicMock(
            id="co1", profile_id="prof-1", run_id="run-1",
            title="Python 101", platform="Udemy", url="https://udemy.com",
            description="Learn Python", cost="$20", duration="10h",
            created_at=_NOW,
        )
        db.execute.return_value = _mock_execute_result([course])

        result = await list_courses(db, "prof-1")
        assert len(result) == 1
        assert result[0].title == "Python 101"


class TestListEvents:
    async def test_returns_events(self):
        from app.services.result_service import list_events

        db = _mock_db()
        event = MagicMock(
            id="e1", profile_id="prof-1", run_id="run-1",
            title="PyCon", organizer="PSF", url="https://pycon.org",
            description="Python conf", event_date="2026-05-01",
            location="Pittsburgh", created_at=_NOW,
        )
        db.execute.return_value = _mock_execute_result([event])

        result = await list_events(db, "prof-1")
        assert len(result) == 1
        assert result[0].title == "PyCon"


class TestListGroups:
    async def test_returns_groups(self):
        from app.services.result_service import list_groups

        db = _mock_db()
        group = MagicMock(
            id="g1", profile_id="prof-1", run_id="run-1",
            title="Python Devs", platform="LinkedIn", url="https://linkedin.com",
            description="A group", member_count=500,
            created_at=_NOW,
        )
        db.execute.return_value = _mock_execute_result([group])

        result = await list_groups(db, "prof-1")
        assert len(result) == 1
        assert result[0].title == "Python Devs"
        assert result[0].member_count == 500


class TestListTrends:
    async def test_returns_trends(self):
        from app.services.result_service import list_trends

        db = _mock_db()
        trend = MagicMock(
            id="t1", profile_id="prof-1", run_id="run-1",
            title="AI Trend", category="tech", url="https://ai.com",
            description="Growing", relevance="high", source="HN",
            created_at=_NOW,
        )
        db.execute.return_value = _mock_execute_result([trend])

        result = await list_trends(db, "prof-1")
        assert len(result) == 1
        assert result[0].title == "AI Trend"
        assert result[0].relevance == "high"


class TestUpdateResultTitle:
    @patch("app.services.result_service._get_by_id", new_callable=AsyncMock)
    async def test_updates_title(self, mock_get):
        from app.services.result_service import update_result_title

        db = _mock_db()
        item = MagicMock(id="j1", profile_id="prof-1", title="Old")
        mock_get.return_value = item

        result = await update_result_title(db, MagicMock, "prof-1", "j1", "New Title")
        assert item.title == "New Title"
        db.commit.assert_called_once()

    @patch("app.services.result_service._get_by_id", new_callable=AsyncMock)
    async def test_returns_none_when_not_found(self, mock_get):
        from app.services.result_service import update_result_title

        mock_get.return_value = None
        db = _mock_db()

        result = await update_result_title(db, MagicMock, "prof-1", "j1", "New")
        assert result is None


class TestDeleteResult:
    @patch("app.services.result_service._get_by_id", new_callable=AsyncMock)
    async def test_deletes_item(self, mock_get):
        from app.services.result_service import delete_result

        db = _mock_db()
        item = MagicMock(id="j1", profile_id="prof-1")
        mock_get.return_value = item

        result = await delete_result(db, MagicMock, "prof-1", "j1")
        assert result is True
        db.delete.assert_called_once_with(item)
        db.commit.assert_called_once()

    @patch("app.services.result_service._get_by_id", new_callable=AsyncMock)
    async def test_returns_false_when_not_found(self, mock_get):
        from app.services.result_service import delete_result

        mock_get.return_value = None
        db = _mock_db()

        result = await delete_result(db, MagicMock, "prof-1", "j1")
        assert result is False


class TestCountCoverLettersForJob:
    async def test_returns_count(self):
        from app.services.result_service import count_cover_letters_for_job

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        db.execute.return_value = mock_result

        count = await count_cover_letters_for_job(db, "prof-1", "job-1")
        assert count == 3


class TestDeleteJobCascade:
    async def test_deletes_job_and_cover_letters(self):
        from app.services.result_service import delete_job_cascade

        db = _mock_db()
        job = _make_job()
        db.execute.side_effect = [
            _mock_execute_scalar_one(job),  # _get_by_id
            MagicMock(),                     # delete cover letters
        ]

        result = await delete_job_cascade(db, "prof-1", "job-1")
        assert result is True
        db.delete.assert_called_once_with(job)
        db.commit.assert_called_once()

    async def test_returns_false_when_job_not_found(self):
        from app.services.result_service import delete_job_cascade

        db = _mock_db()
        db.execute.return_value = _mock_execute_scalar_one(None)

        result = await delete_job_cascade(db, "prof-1", "job-1")
        assert result is False


# ===================================================================
# ProfileService
# ===================================================================

class TestSerializeDeserialize:
    def test_serialize_list(self):
        from app.services.profile_service import _serialize_list

        assert _serialize_list(["a", "b"]) == '["a", "b"]'
        assert _serialize_list(None) is None

    def test_deserialize_list(self):
        from app.services.profile_service import _deserialize_list

        assert _deserialize_list('["a", "b"]') == ["a", "b"]
        assert _deserialize_list(None) is None


class TestProfileToRead:
    def test_converts_profile(self):
        from app.services.profile_service import profile_to_read

        profile = _make_profile()
        read = profile_to_read(profile)
        assert read.id == "prof-1"
        assert read.name == "Architect"
        assert read.targets == ["backend", "cloud"]
        assert read.skills == ["Python", "AWS"]


class TestCheckNameUnique:
    async def test_raises_when_duplicate(self):
        from app.services.profile_service import _check_name_unique

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([_make_profile()])

        with pytest.raises(ValueError, match="already exists"):
            await _check_name_unique(db, "user-1", "Architect")

    async def test_passes_when_unique(self):
        from app.services.profile_service import _check_name_unique

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([])

        # Should not raise
        await _check_name_unique(db, "user-1", "Unique Name")


class TestCreateProfile:
    @patch("app.services.profile_service._check_name_unique", new_callable=AsyncMock)
    async def test_creates_profile(self, mock_check):
        from app.schemas.profile import ProfileCreate
        from app.services.profile_service import create_profile

        db = _mock_db()
        profile = _make_profile()

        async def _refresh(obj):
            obj.id = "prof-new"
            obj.name = "NewProf"
            obj.targets = '["a"]'
            obj.constraints = None
            obj.skills = None
            obj.cv_filename = None
            obj.cv_summary = None
            obj.preferred_titles = None
            obj.industries = None
            obj.locations = None
            obj.work_arrangement = None
            obj.event_attendance = "no preference"
            obj.event_topics = None
            obj.target_certifications = None
            obj.learning_format = None
            obj.created_at = _NOW
            obj.updated_at = _NOW

        db.refresh = AsyncMock(side_effect=_refresh)
        body = ProfileCreate(name="NewProf", targets=["a"])

        result = await create_profile(db, body, owner_id="user-1")
        db.add.assert_called_once()
        db.commit.assert_called_once()


class TestListProfiles:
    async def test_returns_profiles(self):
        from app.services.profile_service import list_profiles

        db = _mock_db()
        p1 = _make_profile(id="p1", name="A")
        p2 = _make_profile(id="p2", name="B")
        db.execute.return_value = _mock_execute_result([p1, p2])

        result = await list_profiles(db)
        assert len(result) == 2

    async def test_filters_by_owner(self):
        from app.services.profile_service import list_profiles

        db = _mock_db()
        db.execute.return_value = _mock_execute_result([_make_profile()])

        result = await list_profiles(db, owner_id="user-1")
        assert len(result) == 1
        db.execute.assert_called_once()


class TestGetProfile:
    async def test_returns_profile(self):
        from app.services.profile_service import get_profile

        db = _mock_db()
        db.get.return_value = _make_profile()

        result = await get_profile(db, "prof-1")
        assert result is not None
        assert result.id == "prof-1"

    async def test_returns_none_when_not_found(self):
        from app.services.profile_service import get_profile

        db = _mock_db()
        db.get.return_value = None

        result = await get_profile(db, "prof-missing")
        assert result is None


class TestUpdateProfile:
    async def test_updates_fields(self):
        from app.schemas.profile import ProfileUpdate
        from app.services.profile_service import update_profile

        db = _mock_db()
        profile = _make_profile()
        db.get.return_value = profile
        # Mock _check_name_unique
        db.execute.return_value = _mock_execute_result([])

        async def _refresh(obj):
            pass

        db.refresh = AsyncMock(side_effect=_refresh)

        body = ProfileUpdate(name="Updated Name")
        with patch("app.services.profile_service._check_name_unique", new_callable=AsyncMock):
            result = await update_profile(db, "prof-1", body)

        db.commit.assert_called_once()

    async def test_returns_none_when_not_found(self):
        from app.schemas.profile import ProfileUpdate
        from app.services.profile_service import update_profile

        db = _mock_db()
        db.get.return_value = None

        body = ProfileUpdate(name="X")
        result = await update_profile(db, "prof-missing", body)
        assert result is None


class TestDeleteProfile:
    @patch("app.services.profile_service.asyncio")
    async def test_deletes_profile_and_cascades(self, mock_asyncio):
        from app.services.profile_service import delete_profile

        mock_asyncio.to_thread = AsyncMock()
        db = _mock_db()
        profile = _make_profile()
        db.get.return_value = profile

        run_result = MagicMock()
        run_result.all.return_value = [("run-1",), ("run-2",)]
        db.execute.side_effect = [
            run_result,      # select run IDs
            MagicMock(),     # delete cover letters
            MagicMock(),     # delete jobs
            MagicMock(),     # delete certs
            MagicMock(),     # delete courses
            MagicMock(),     # delete events
            MagicMock(),     # delete groups
            MagicMock(),     # delete trends
            MagicMock(),     # delete runs
        ]

        result = await delete_profile(db, "prof-1")
        assert result is True
        db.delete.assert_called_once_with(profile)
        db.commit.assert_called_once()

    async def test_returns_false_when_not_found(self):
        from app.services.profile_service import delete_profile

        db = _mock_db()
        db.get.return_value = None
        result = await delete_profile(db, "prof-missing")
        assert result is False


class TestUploadCv:
    @patch("app.services.profile_service._background_tasks", set())
    @patch("app.services.profile_service.asyncio")
    async def test_uploads_cv(self, mock_asyncio):
        from app.services.profile_service import upload_cv

        mock_task = MagicMock()
        mock_task.add_done_callback = MagicMock()
        mock_asyncio.create_task.return_value = mock_task

        db = _mock_db()
        profile = _make_profile()
        db.get.return_value = profile

        async def _refresh(obj):
            pass

        db.refresh = AsyncMock(side_effect=_refresh)

        result = await upload_cv(db, "prof-1", "resume.pdf", b"pdf-content")
        assert profile.cv_data == b"pdf-content"
        assert profile.cv_filename == "resume.pdf"
        assert profile.cv_summary is None
        assert profile.cv_summary_hash is None
        db.commit.assert_called_once()

    async def test_returns_none_when_not_found(self):
        from app.services.profile_service import upload_cv

        db = _mock_db()
        db.get.return_value = None

        result = await upload_cv(db, "prof-missing", "f.pdf", b"data")
        assert result is None


class TestExtractTextFromPdf:
    @patch("app.services.profile_service.PdfReader")
    def test_extracts_text_from_bytes(self, mock_reader_cls):
        from app.services.profile_service import extract_text_from_pdf

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 content"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        result = extract_text_from_pdf(b"fake-pdf-bytes")
        assert "Page 1 content" in result

    @patch("app.services.profile_service.PdfReader")
    def test_handles_empty_pages(self, mock_reader_cls):
        from app.services.profile_service import extract_text_from_pdf

        mock_page = MagicMock()
        mock_page.extract_text.return_value = None
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        result = extract_text_from_pdf(b"fake-pdf")
        assert result == ""


class TestExportProfile:
    async def test_exports_profile(self):
        from app.services.profile_service import export_profile

        db = _mock_db()
        db.get.return_value = _make_profile()

        result = await export_profile(db, "prof-1")
        assert result is not None
        assert result["name"] == "Architect"
        assert result["targets"] == ["backend", "cloud"]

    async def test_returns_none_when_not_found(self):
        from app.services.profile_service import export_profile

        db = _mock_db()
        db.get.return_value = None

        result = await export_profile(db, "prof-missing")
        assert result is None


class TestImportProfile:
    @patch("app.services.profile_service.create_profile", new_callable=AsyncMock)
    async def test_imports_profile(self, mock_create):
        from app.services.profile_service import import_profile

        mock_create.return_value = MagicMock()  # ProfileRead
        db = _mock_db()

        data = {"name": "Imported", "targets": ["a"], "skills": ["Python"]}
        await import_profile(db, data, owner_id="user-1")
        mock_create.assert_called_once()


class TestExtractSkillsFromCv:
    async def test_raises_when_profile_not_found(self):
        from app.services.profile_service import extract_skills_from_cv

        db = _mock_db()
        db.get.return_value = None
        with pytest.raises(LookupError, match="Profile not found"):
            await extract_skills_from_cv(db, "prof-1")

    async def test_raises_when_no_cv_data(self):
        from app.services.profile_service import extract_skills_from_cv

        db = _mock_db()
        db.get.return_value = _make_profile(cv_data=None)
        with pytest.raises(ValueError, match="No CV uploaded"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.extract_text_from_pdf", return_value="")
    async def test_raises_when_cv_text_empty(self, mock_extract):
        from app.services.profile_service import extract_skills_from_cv

        db = _mock_db()
        db.get.return_value = _make_profile(cv_data=b"pdf")
        with pytest.raises(ValueError, match="no readable text"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.settings")
    @patch("app.services.profile_service.extract_text_from_pdf", return_value="Python dev")
    async def test_raises_when_no_api_key(self, mock_extract, mock_settings):
        from app.services.profile_service import extract_skills_from_cv

        mock_settings.api_key = ""
        db = _mock_db()
        db.get.return_value = _make_profile(cv_data=b"pdf")
        with pytest.raises(ValueError, match="API key not configured"):
            await extract_skills_from_cv(db, "prof-1")

    @patch("app.services.profile_service.extract_text_from_pdf", side_effect=Exception("corrupt"))
    async def test_raises_when_pdf_extraction_fails(self, mock_extract):
        from app.services.profile_service import extract_skills_from_cv

        db = _mock_db()
        db.get.return_value = _make_profile(cv_data=b"corrupt-pdf")
        with pytest.raises(ValueError, match="Failed to read CV"):
            await extract_skills_from_cv(db, "prof-1")


class TestEnsureCvSummary:
    async def test_returns_empty_when_no_cv_data(self):
        from app.services.profile_service import ensure_cv_summary

        db = _mock_db()
        profile = _make_profile(cv_data=None)
        result = await ensure_cv_summary(db, profile)
        assert result == ""

    @patch("app.services.profile_service.asyncio")
    async def test_returns_cached_summary(self, mock_asyncio):
        from app.services.profile_service import ensure_cv_summary

        cv_data = b"pdf-content"
        import hashlib
        cv_hash = hashlib.sha256(cv_data).hexdigest()

        mock_asyncio.to_thread = AsyncMock(return_value=cv_hash)

        db = _mock_db()
        profile = _make_profile(
            cv_data=cv_data,
            cv_summary="Cached summary",
            cv_summary_hash=cv_hash,
        )

        result = await ensure_cv_summary(db, profile)
        assert result == "Cached summary"
