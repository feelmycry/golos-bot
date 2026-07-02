import pytest


@pytest.mark.asyncio
async def test_get_me_returns_profile(client):
    r = await client.get("/api/me")
    assert r.status_code == 200
    data = r.json()
    assert "user_id" in data
    assert "level" in data
    assert "coins" in data
    assert "xp_in_level" in data
    assert "xp_for_level" in data


@pytest.mark.asyncio
async def test_get_achievements(client):
    r = await client.get("/api/me/achievements")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
    assert "earned" in data[0]
