"""Tests for authentication endpoints."""

import pytest


@pytest.mark.asyncio
async def test_register_success(client):
    """Verify successful user registration returns tokens and the first user is admin.

    Args:
        client: The httpx test client.
    """
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "password": "StrongPass1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "john@example.com"
    # First user should be admin
    assert data["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_register_second_user_is_regular(client):
    """Verify the second registered user receives the regular 'user' role.

    Args:
        client: The httpx test client.
    """
    # First user = admin
    await client.post(
        "/api/auth/register",
        json={
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@example.com",
            "password": "AdminPass1",
        },
    )
    # Second user = regular
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": "Regular",
            "last_name": "User",
            "email": "regular@example.com",
            "password": "UserPass1",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "user"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    """Verify that registering with an already-used email returns 409.

    Args:
        client: The httpx test client.
    """
    body = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "password": "StrongPass1",
    }
    await client.post("/api/auth/register", json=body)
    resp = await client.post("/api/auth/register", json=body)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client):
    """Verify that a weak password is rejected with 422.

    Args:
        client: The httpx test client.
    """
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "password": "weak",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client):
    """Verify successful login returns an access token.

    Args:
        client: The httpx test client.
    """
    await client.post(
        "/api/auth/register",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "password": "StrongPass1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "john@example.com", "password": "StrongPass1"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """Verify that logging in with an incorrect password returns 401.

    Args:
        client: The httpx test client.
    """
    await client.post(
        "/api/auth/register",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "password": "StrongPass1",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "john@example.com", "password": "WrongPass1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client):
    """Verify that logging in with an unregistered email returns 401.

    Args:
        client: The httpx test client.
    """
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "SomePass1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, admin_headers):
    """Verify the /auth/me endpoint returns the authenticated user's email.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
    """
    resp = await client.get("/api/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client):
    """Verify that /auth/me without a token returns 401.

    Args:
        client: The httpx test client.
    """
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client):
    """Verify that a valid refresh token returns a new access token.

    Args:
        client: The httpx test client.
    """
    reg = await client.post(
        "/api/auth/register",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "password": "StrongPass1",
        },
    )
    refresh = reg.json()["refresh_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_logout(client):
    """Verify that logout revokes the refresh token so it cannot be reused.

    Args:
        client: The httpx test client.
    """
    reg = await client.post(
        "/api/auth/register",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "password": "StrongPass1",
        },
    )
    refresh = reg.json()["refresh_token"]
    resp = await client.post("/api/auth/logout", json={"refresh_token": refresh})
    assert resp.status_code == 200

    # Refresh with revoked token should fail
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth(client):
    """Verify that accessing a protected endpoint without auth returns 401.

    Args:
        client: The httpx test client.
    """
    resp = await client.get("/api/profiles")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_profile_ownership(client, admin_headers, auth_headers):
    """Verify that profile ownership is enforced: users cannot access other users' profiles.

    Args:
        client: The httpx test client.
        admin_headers: Auth headers for the admin user.
        auth_headers: Auth headers for a regular user.
    """
    # Admin creates a profile
    resp = await client.post(
        "/api/profiles",
        json={"name": "Admin Profile"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    admin_profile_id = resp.json()["id"]

    # Regular user cannot access admin's profile
    resp = await client.get(f"/api/profiles/{admin_profile_id}", headers=auth_headers)
    assert resp.status_code == 403

    # Regular user creates own profile
    resp = await client.post(
        "/api/profiles",
        json={"name": "User Profile"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Regular user's profile list shows only their profile
    resp = await client.get("/api/profiles", headers=auth_headers)
    assert resp.status_code == 200
    profiles = resp.json()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "User Profile"

    # Admin sees all profiles
    resp = await client.get("/api/profiles", headers=admin_headers)
    assert len(resp.json()) == 2
