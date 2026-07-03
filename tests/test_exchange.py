import pytest


@pytest.mark.asyncio
async def test_get_stocks(client):
    r = await client.get("/api/stocks")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    s = data[0]
    assert "id" in s
    assert "price" in s
    assert "change_pct" in s
    assert "shares_owned" in s


@pytest.mark.asyncio
async def test_buy_without_enough_coins(client):
    # User 99999 starts with 0 coins → buy should fail
    r = await client.post("/api/stocks/sber/buy", json={"qty": 1000})
    assert r.status_code == 200
    assert r.json()["success"] is False
