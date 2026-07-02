import pytest


@pytest.mark.asyncio
async def test_get_map(client):
    r = await client.get("/api/map")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    loc = data[0]
    assert "id" in loc
    assert "quests_total" in loc
    assert "unlocked" in loc


@pytest.mark.asyncio
async def test_get_location_detail(client):
    r = await client.get("/api/map/sber")
    assert r.status_code == 200
    data = r.json()
    assert "quests" in data
    assert len(data["quests"]) > 0
    q = data["quests"][0]
    assert "id" in q
    assert "question" in q
    assert "options" in q
    assert "correct" not in q  # не отдаём правильный ответ заранее


@pytest.mark.asyncio
async def test_answer_quest(client):
    r = await client.post("/api/map/sber/quests/sber_q1/answer", json={"answer_idx": 2})
    assert r.status_code == 200
    data = r.json()
    assert "correct" in data
    assert "xp_earned" in data
    assert "explanation" in data
