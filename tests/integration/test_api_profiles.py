import pytest


@pytest.mark.asyncio
async def test_create_profile(client):
    resp = await client.post(
        "/api/profiles",
        json={"name": "Architect", "targets": ["cloud", "infra"], "skills": ["aws"]},
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
async def test_create_profile_minimal(client):
    resp = await client.post("/api/profiles", json={"name": "Developer"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Developer"
    assert data["targets"] is None


@pytest.mark.asyncio
async def test_create_profile_missing_name(client):
    resp = await client.post("/api/profiles", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_profile_empty_name(client):
    resp = await client.post("/api/profiles", json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_profile_name_too_long(client):
    resp = await client.post("/api/profiles", json={"name": "x" * 201})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_profiles(client):
    await client.post("/api/profiles", json={"name": "Alpha"})
    await client.post("/api/profiles", json={"name": "Beta"})
    resp = await client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha"
    assert data[1]["name"] == "Beta"


@pytest.mark.asyncio
async def test_get_profile(client):
    create_resp = await client.post(
        "/api/profiles", json={"name": "Architect", "skills": ["python"]}
    )
    profile_id = create_resp.json()["id"]
    resp = await client.get(f"/api/profiles/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Architect"
    assert resp.json()["skills"] == ["python"]


@pytest.mark.asyncio
async def test_get_profile_not_found(client):
    resp = await client.get("/api/profiles/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_profile(client):
    create_resp = await client.post(
        "/api/profiles", json={"name": "Old Name", "targets": ["a"]}
    )
    profile_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/profiles/{profile_id}",
        json={"name": "New Name", "skills": ["go"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["skills"] == ["go"]
    # targets should remain unchanged
    assert data["targets"] == ["a"]


@pytest.mark.asyncio
async def test_update_profile_not_found(client):
    resp = await client.put(
        "/api/profiles/nonexistent-id", json={"name": "Whatever"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile(client):
    create_resp = await client.post("/api/profiles", json={"name": "ToDelete"})
    profile_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/profiles/{profile_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/profiles/{profile_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile_not_found(client):
    resp = await client.delete("/api/profiles/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_profile_partial(client):
    """Only the fields provided in the update body are changed."""
    create_resp = await client.post(
        "/api/profiles",
        json={"name": "Original", "targets": ["t1"], "skills": ["s1"]},
    )
    profile_id = create_resp.json()["id"]

    # Update only skills
    resp = await client.put(
        f"/api/profiles/{profile_id}", json={"skills": ["s2", "s3"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Original"
    assert data["targets"] == ["t1"]
    assert data["skills"] == ["s2", "s3"]
