"""Tests for the BYOK settings API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.user import User


@pytest.mark.asyncio
async def test_get_api_key_status_no_key(client, admin_headers):
    """Verify that the API key status endpoint reports no key when none is stored.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    resp = await client.get("/api/settings/api-key-status", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is False
    assert data["free_runs_used"] == 0
    assert data["free_run_limit"] >= 1
    assert data["key_last_four"] is None


@pytest.mark.asyncio
async def test_save_api_key(client, admin_headers, db_session):
    """Verify saving a valid API key stores it and reports the last four digits.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
        db_session: The test database session.
    """
    with patch(
        "app.services.api_key_service.validate_openai_key",
        new_callable=AsyncMock,
        return_value=True,
    ):
        resp = await client.put(
            "/api/settings/api-key",
            json={"api_key": "sk-test-valid-key-1234567890"},
            headers=admin_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is True
    assert data["key_last_four"] is not None
    assert data["key_last_four"].endswith("7890")


@pytest.mark.asyncio
async def test_save_invalid_key_returns_422(client, admin_headers):
    """Verify that saving an invalid API key returns 422.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    with patch(
        "app.services.api_key_service.validate_openai_key",
        new_callable=AsyncMock,
        return_value=False,
    ):
        resp = await client.put(
            "/api/settings/api-key",
            json={"api_key": "sk-invalid-key-0000000000"},
            headers=admin_headers,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_api_key(client, admin_headers, db_session):
    """Verify deleting a stored API key removes it and reports has_api_key=False.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
        db_session: The test database session.
    """
    # Save a key first
    with patch(
        "app.services.api_key_service.validate_openai_key",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await client.put(
            "/api/settings/api-key",
            json={"api_key": "sk-test-delete-key-123456"},
            headers=admin_headers,
        )

    # Delete it
    resp = await client.delete("/api/settings/api-key", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["detail"] == "API key removed"

    # Verify it's gone
    status_resp = await client.get("/api/settings/api-key-status", headers=admin_headers)
    assert status_resp.json()["has_api_key"] is False


@pytest.mark.asyncio
async def test_key_too_short_returns_422(client, admin_headers):
    """Verify that a key shorter than the minimum length returns 422.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    resp = await client.put(
        "/api/settings/api-key",
        json={"api_key": "short"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_encrypted_key_not_plaintext(client, admin_headers, db_session):
    """The stored value in DB should not be the plaintext key."""
    plain_key = "sk-test-encryption-check-123"
    with patch(
        "app.services.api_key_service.validate_openai_key",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await client.put(
            "/api/settings/api-key",
            json={"api_key": plain_key},
            headers=admin_headers,
        )

    # Read the user row directly
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "admin@test.com"))
    user = result.scalar_one()
    assert user.encrypted_api_key is not None
    assert user.encrypted_api_key != plain_key
