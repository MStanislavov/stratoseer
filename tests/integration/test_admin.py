"""Tests for admin endpoints."""

import pytest


@pytest.mark.asyncio
async def test_admin_list_users(client, admin_headers):
    resp = await client.get("/api/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert data["total"] >= 1
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_admin_forbidden_for_regular_user(client, auth_headers):
    resp = await client.get("/api/admin/users", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_unauthenticated(client):
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 401
