import pytest


@pytest.mark.asyncio
async def test_create_profile(client, admin_headers):
    resp = await client.post(
        "/api/profiles",
        json={"name": "Architect", "targets": ["cloud", "infra"], "skills": ["aws"], "preferred_titles": ["Cloud Architect"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Architect"
    assert data["targets"] == ["cloud", "infra"]
    assert data["skills"] == ["aws"]
    assert data["constraints"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_profile_minimal(client, admin_headers):
    resp = await client.post("/api/profiles", json={"name": "Developer", "preferred_titles": ["Developer"]}, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Developer"
    assert data["targets"] is None


@pytest.mark.asyncio
async def test_create_profile_missing_name(client, admin_headers):
    resp = await client.post("/api/profiles", json={"preferred_titles": ["Dev"]}, headers=admin_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_profile_empty_name(client, admin_headers):
    resp = await client.post("/api/profiles", json={"name": "", "preferred_titles": ["Dev"]}, headers=admin_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_profile_name_too_long(client, admin_headers):
    resp = await client.post("/api/profiles", json={"name": "x" * 201, "preferred_titles": ["Dev"]}, headers=admin_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_profiles(client, admin_headers):
    await client.post("/api/profiles", json={"name": "Alpha", "preferred_titles": ["Dev"]}, headers=admin_headers)
    await client.post("/api/profiles", json={"name": "Beta", "preferred_titles": ["Dev"]}, headers=admin_headers)
    resp = await client.get("/api/profiles", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha"
    assert data[1]["name"] == "Beta"


@pytest.mark.asyncio
async def test_get_profile(client, admin_headers):
    create_resp = await client.post(
        "/api/profiles", json={"name": "Architect", "skills": ["python"], "preferred_titles": ["Architect"]}, headers=admin_headers
    )
    profile_id = create_resp.json()["id"]
    resp = await client.get(f"/api/profiles/{profile_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Architect"
    assert resp.json()["skills"] == ["python"]


@pytest.mark.asyncio
async def test_get_profile_not_found(client, admin_headers):
    resp = await client.get("/api/profiles/nonexistent-id", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_profile(client, admin_headers):
    create_resp = await client.post(
        "/api/profiles", json={"name": "Old Name", "targets": ["a"], "preferred_titles": ["Dev"]}, headers=admin_headers
    )
    profile_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/profiles/{profile_id}",
        json={"name": "New Name", "skills": ["go"]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["skills"] == ["go"]
    # targets should remain unchanged
    assert data["targets"] == ["a"]


@pytest.mark.asyncio
async def test_update_profile_not_found(client, admin_headers):
    resp = await client.put(
        "/api/profiles/nonexistent-id", json={"name": "Whatever"}, headers=admin_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile(client, admin_headers):
    create_resp = await client.post("/api/profiles", json={"name": "ToDelete", "preferred_titles": ["Dev"]}, headers=admin_headers)
    profile_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/profiles/{profile_id}", headers=admin_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/profiles/{profile_id}", headers=admin_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile_not_found(client, admin_headers):
    resp = await client.delete("/api/profiles/nonexistent-id", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_profile_partial(client, admin_headers):
    """Only the fields provided in the update body are changed."""
    create_resp = await client.post(
        "/api/profiles",
        json={"name": "Original", "targets": ["t1"], "skills": ["s1"], "preferred_titles": ["Dev"]},
        headers=admin_headers,
    )
    profile_id = create_resp.json()["id"]

    # Update only skills
    resp = await client.put(
        f"/api/profiles/{profile_id}", json={"skills": ["s2", "s3"]}, headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Original"
    assert data["targets"] == ["t1"]
    assert data["skills"] == ["s2", "s3"]
