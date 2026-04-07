"""Tests for CV summary caching (KAN-8)."""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.profile import UserProfile
from app.services.profile_service import ensure_cv_summary, upload_cv

FAKE_CV_TEXT = "John Doe\nSenior Software Engineer\nPython, AWS, Docker"
FAKE_SUMMARY = "Professional summary of John Doe, a Senior Software Engineer."
FAKE_PDF_BYTES = b"%PDF-fake-cv-bytes"


@pytest.mark.asyncio
async def test_upload_cv_invalidates_summary(client, admin_headers, db_session):
    """Uploading a CV should set cv_summary and cv_summary_hash to None."""
    # Create profile
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]

    # Pre-populate a cached summary directly in DB
    profile = await db_session.get(UserProfile, profile_id)
    profile.cv_summary = "old summary"
    profile.cv_summary_hash = "oldhash"
    await db_session.commit()

    # Upload a CV via the service (mock background task to avoid LLM call)
    with patch("app.services.profile_service._background_summarize", new_callable=AsyncMock):
        result = await upload_cv(db_session, profile_id, "resume.pdf", FAKE_PDF_BYTES)

    assert result is not None
    await db_session.refresh(profile)
    assert profile.cv_summary is None
    assert profile.cv_summary_hash is None


@pytest.mark.asyncio
async def test_ensure_cv_summary_generates_on_miss(db_session, client, admin_headers):
    """ensure_cv_summary should call LLM and cache when no summary exists."""
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]

    profile = await db_session.get(UserProfile, profile_id)
    profile.cv_data = FAKE_PDF_BYTES
    await db_session.commit()

    with (
        patch(
            "app.services.profile_service.extract_text_from_pdf",
            return_value=FAKE_CV_TEXT,
        ),
        patch(
            "app.services.cover_letter_service.summarize_cv",
            new_callable=AsyncMock,
            return_value=FAKE_SUMMARY,
        ) as mock_summarize,
    ):
        result = await ensure_cv_summary(db_session, profile)

    assert result == FAKE_SUMMARY
    mock_summarize.assert_awaited_once_with(FAKE_CV_TEXT, settings.api_key)
    await db_session.refresh(profile)
    assert profile.cv_summary == FAKE_SUMMARY
    assert profile.cv_summary_hash == hashlib.sha256(FAKE_PDF_BYTES).hexdigest()


@pytest.mark.asyncio
async def test_ensure_cv_summary_returns_cached(db_session, client, admin_headers):
    """ensure_cv_summary should return cached value without calling LLM."""
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]

    cv_hash = hashlib.sha256(FAKE_PDF_BYTES).hexdigest()
    profile = await db_session.get(UserProfile, profile_id)
    profile.cv_data = FAKE_PDF_BYTES
    profile.cv_summary = FAKE_SUMMARY
    profile.cv_summary_hash = cv_hash
    await db_session.commit()

    with patch(
        "app.services.cover_letter_service.summarize_cv",
        new_callable=AsyncMock,
    ) as mock_summarize:
        result = await ensure_cv_summary(db_session, profile)

    assert result == FAKE_SUMMARY
    mock_summarize.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_cv_summary_regenerates_on_stale_hash(db_session, client, admin_headers):
    """ensure_cv_summary should regenerate when cv_data hash no longer matches."""
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]

    profile = await db_session.get(UserProfile, profile_id)
    profile.cv_data = FAKE_PDF_BYTES
    profile.cv_summary = "stale summary"
    profile.cv_summary_hash = "wrong_hash"
    await db_session.commit()

    new_summary = "Updated professional summary."
    with (
        patch(
            "app.services.profile_service.extract_text_from_pdf",
            return_value=FAKE_CV_TEXT,
        ),
        patch(
            "app.services.cover_letter_service.summarize_cv",
            new_callable=AsyncMock,
            return_value=new_summary,
        ) as mock_summarize,
    ):
        result = await ensure_cv_summary(db_session, profile)

    assert result == new_summary
    mock_summarize.assert_awaited_once()
    await db_session.refresh(profile)
    assert profile.cv_summary == new_summary


@pytest.mark.asyncio
async def test_ensure_cv_summary_falls_back_on_llm_failure(db_session, client, admin_headers):
    """If LLM fails, ensure_cv_summary should fall back to raw extracted text."""
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]

    profile = await db_session.get(UserProfile, profile_id)
    profile.cv_data = FAKE_PDF_BYTES
    await db_session.commit()

    with (
        patch(
            "app.services.profile_service.extract_text_from_pdf",
            return_value=FAKE_CV_TEXT,
        ),
        patch(
            "app.services.cover_letter_service.summarize_cv",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unavailable"),
        ),
    ):
        result = await ensure_cv_summary(db_session, profile)

    assert result == FAKE_CV_TEXT
    await db_session.refresh(profile)
    assert profile.cv_summary == FAKE_CV_TEXT


@pytest.mark.asyncio
async def test_ensure_cv_summary_empty_when_no_cv(db_session, client, admin_headers):
    """ensure_cv_summary should return empty string when no CV is uploaded."""
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]

    profile = await db_session.get(UserProfile, profile_id)
    result = await ensure_cv_summary(db_session, profile)

    assert result == ""


@pytest.mark.asyncio
async def test_has_cv_summary_in_profile_response(client, admin_headers, db_session):
    """ProfileRead should include has_cv_summary field."""
    resp = await client.post(
        "/api/profiles",
        json={"name": "Test", "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = resp.json()["id"]
    assert resp.json()["has_cv_summary"] is False

    # Set a cached summary directly
    profile = await db_session.get(UserProfile, profile_id)
    profile.cv_summary = FAKE_SUMMARY
    await db_session.commit()

    resp = await client.get(f"/api/profiles/{profile_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["has_cv_summary"] is True
