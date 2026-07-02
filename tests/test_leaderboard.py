import pytest


@pytest.mark.asyncio
async def test_get_leaderboard(client):
    r = await client.get("/api/leaderboard")
    assert r.status_code == 200
    data = r.json()
    assert "alltime" in data
    assert "weekly" in data
    assert "guilds" in data
    assert "my_rank" in data


@pytest.mark.asyncio
async def test_get_daily(client):
    r = await client.get("/api/daily")
    assert r.status_code == 200
    data = r.json()
    assert "tasks" in data
    assert isinstance(data["tasks"], list)
    t = data["tasks"][0]
    assert "id" in t
    assert "progress" in t
    assert "target" in t
    assert "claimed" in t
