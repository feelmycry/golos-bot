from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import get_current_user
from api.game_data import STOCK_CONFIG, get_stock_info, DAILY_TASKS
from services.db import (
    game_get_location_progress,
    game_get_or_create_player,
    game_buy_shares,
    game_sell_shares,
    game_update_daily_task,
)

router = APIRouter()


@router.get("/api/stocks")
async def list_stocks(request: Request, user_id: int = Depends(get_current_user)):
    loc_progress = await game_get_location_progress(user_id)
    result = []
    for loc_id, cfg in STOCK_CONFIG.items():
        price, change = get_stock_info(loc_id)
        p = loc_progress.get(loc_id, {})
        result.append({
            "id": loc_id,
            "ticker": cfg["ticker"],
            "name": cfg["name"],
            "price": price,
            "change_pct": round(change, 2),
            "shares_owned": p.get("shares", 0),
        })
    return result


class TradeRequest(BaseModel):
    qty: int


@router.post("/api/stocks/{loc_id}/buy")
async def buy_stock(loc_id: str, body: TradeRequest, request: Request, user_id: int = Depends(get_current_user)):
    cfg = STOCK_CONFIG.get(loc_id)
    if not cfg:
        raise HTTPException(404, "Stock not found")
    if body.qty < 1:
        raise HTTPException(400, "qty must be >= 1")

    price, _ = get_stock_info(loc_id)
    cost = price * body.qty
    success = await game_buy_shares(user_id, loc_id, body.qty, cost)

    if success:
        today = date.today().isoformat()
        for tid, task in DAILY_TASKS.items():
            if task["type"] == "buy_stock":
                await game_update_daily_task(user_id, today, tid, 1, task["target"])
            if task["type"] == "visit_exchange":
                await game_update_daily_task(user_id, today, tid, 1, task["target"])

    player = await game_get_or_create_player(user_id)
    loc_progress = await game_get_location_progress(user_id)
    return {
        "success": success,
        "new_coins": player["coins"],
        "shares": loc_progress.get(loc_id, {}).get("shares", 0),
        "message": "" if success else "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РР ",
    }


@router.post("/api/stocks/{loc_id}/sell")
async def sell_stock(loc_id: str, body: TradeRequest, request: Request, user_id: int = Depends(get_current_user)):
    cfg = STOCK_CONFIG.get(loc_id)
    if not cfg:
        raise HTTPException(404, "Stock not found")
    if body.qty < 1:
        raise HTTPException(400, "qty must be >= 1")

    price, _ = get_stock_info(loc_id)
    gain = price * body.qty
    success = await game_sell_shares(user_id, loc_id, body.qty, gain)

    player = await game_get_or_create_player(user_id)
    loc_progress = await game_get_location_progress(user_id)
    return {
        "success": success,
        "new_coins": player["coins"],
        "shares": loc_progress.get(loc_id, {}).get("shares", 0),
        "message": "" if success else "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р°РєС†РёР№",
    }
