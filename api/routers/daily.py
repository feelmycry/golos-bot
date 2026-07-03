import hashlib
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request

from api.deps import get_current_user
from api.game_data import DAILY_TASKS
from services.db import game_get_daily_progress, game_claim_daily_reward

router = APIRouter()


def _today_task_ids() -> list[str]:
    """Returns the 3 tasks for today (deterministic by date using md5)."""
    day = date.today().isoformat()
    task_ids = list(DAILY_TASKS.keys())
    h = int(hashlib.md5(day.encode()).hexdigest(), 16)
    # Pick 3 tasks deterministically
    indices = [(h >> (i * 8)) % len(task_ids) for i in range(5)]
    seen, chosen = set(), []
    for i in indices:
        if task_ids[i] not in seen:
            seen.add(task_ids[i])
            chosen.append(task_ids[i])
        if len(chosen) == 3:
            break
    while len(chosen) < 3:
        for tid in task_ids:
            if tid not in seen:
                chosen.append(tid)
                seen.add(tid)
                break
    return chosen


@router.get("/api/daily")
async def get_daily(request: Request, user_id: int = Depends(get_current_user)):
    today = date.today().isoformat()
    progress = await game_get_daily_progress(user_id, today)
    task_ids = _today_task_ids()
    tasks = []
    for tid in task_ids:
        cfg = DAILY_TASKS[tid]
        p = progress.get(tid, {"progress": 0, "completed": False, "claimed": False})
        tasks.append({
            "id": tid,
            "desc": cfg["desc"],
            "target": cfg["target"],
            "progress": p.get("progress", 0),
            "completed": bool(p.get("completed", 0)),
            "claimed": bool(p.get("claimed", 0)),
            "coins": cfg["coins"],
            "xp": cfg["xp"],
        })
    return {"tasks": tasks, "date": today}


@router.post("/api/daily/{task_id}/claim")
async def claim_daily(task_id: str, request: Request, user_id: int = Depends(get_current_user)):
    cfg = DAILY_TASKS.get(task_id)
    if not cfg:
        raise HTTPException(404, "Task not found")
    today = date.today().isoformat()
    success = await game_claim_daily_reward(user_id, today, task_id, cfg["xp"], cfg["coins"])
    return {"success": success, "message": "" if success else "Р—Р°РґР°РЅРёРµ РЅРµ РІС‹РїРѕР»РЅРµРЅРѕ РёР»Рё СѓР¶Рµ РїРѕР»СѓС‡РµРЅРѕ"}
