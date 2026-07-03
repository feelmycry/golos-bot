from datetime import date, timedelta, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import get_current_user
from api.game_data import (
    LOCATIONS, WORLD_LOCATIONS, FUTURE_LOCATIONS, DAILY_TASKS,
    ACHIEVEMENTS, parse_level, streak_multiplier,
)
from services.db import (
    game_get_or_create_player,
    game_get_location_progress,
    game_get_completed_quests,
    game_save_quest_result,
    game_update_daily_task,
    game_update_streak,
    game_get_achievements,
    game_grant_achievement,
    game_add_weekly_xp,
    game_update_player,
    game_collect_income,
)

router = APIRouter()


def _week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def _rep_rank(loc: dict, reputation: int) -> str:
    thresholds = loc.get("rep_thresholds", [0])
    ranks = loc.get("rep_rank", ["РќРѕРІРёС‡РѕРє"])
    rank = ranks[0]
    for i, t in enumerate(thresholds):
        if reputation >= t and i < len(ranks):
            rank = ranks[i]
    return rank


def _collect_amount(loc: dict, loc_progress: dict, loc_id: str) -> int:
    p = loc_progress.get(loc_id, {})
    shares = p.get("shares", 0)
    if shares == 0:
        return 0
    last = p.get("last_collected")
    if not last:
        return loc["income_per_hour"] * shares
    dt = datetime.fromisoformat(last).replace(tzinfo=timezone.utc)
    hours = max(0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    return int(loc["income_per_hour"] * shares * hours)


@router.get("/api/map")
async def get_map(request: Request, user_id: int = Depends(get_current_user)):
    player = await game_get_or_create_player(user_id)
    level = parse_level(player["xp"])[0]
    loc_progress = await game_get_location_progress(user_id)
    completed = await game_get_completed_quests(user_id)

    result = []
    all_locs = {**LOCATIONS, **WORLD_LOCATIONS}
    for loc_id, loc in all_locs.items():
        p = loc_progress.get(loc_id, {"reputation": 0, "shares": 0})
        quests = loc.get("quests", [])
        done = sum(1 for q in quests if q["id"] in completed)
        amount = _collect_amount(loc, loc_progress, loc_id)
        result.append({
            "id": loc_id,
            "name": loc["name"],
            "emoji": loc["emoji"],
            "sector": loc["sector"],
            "min_level": loc.get("min_level", 1),
            "unlocked": level >= loc.get("min_level", 1),
            "quests_total": len(quests),
            "quests_done": done,
            "reputation": p.get("reputation", 0),
            "rep_rank": _rep_rank(loc, p.get("reputation", 0)),
            "shares": p.get("shares", 0),
            "income_per_hour": loc.get("income_per_hour", 0),
            "can_collect": amount > 0,
            "collect_amount": amount,
        })

    for fl in FUTURE_LOCATIONS:
        result.append({
            "id": None,
            "name": fl["name"],
            "emoji": fl["emoji"],
            "sector": fl["sector"],
            "min_level": fl["min_level"],
            "unlocked": False,
            "quests_total": 0, "quests_done": 0,
            "reputation": 0, "rep_rank": "",
            "shares": 0, "income_per_hour": 0,
            "can_collect": False, "collect_amount": 0,
        })

    return result


@router.get("/api/map/{loc_id}")
async def get_location(loc_id: str, request: Request, user_id: int = Depends(get_current_user)):
    all_locs = {**LOCATIONS, **WORLD_LOCATIONS}
    loc = all_locs.get(loc_id)
    if not loc:
        raise HTTPException(404, "Location not found")

    completed = await game_get_completed_quests(user_id)
    quests_out = []
    for q in loc.get("quests", []):
        quests_out.append({
            "id": q["id"],
            "title": q["title"],
            "story": q["story"],
            "question": q["question"],
            "options": q["options"],
            "xp": q["xp"],
            "coins": q["coins"],
            "completed": q["id"] in completed,
            # "correct" intentionally omitted
        })

    return {**{k: loc[k] for k in ("name", "emoji", "sector", "description", "income_per_hour")}, "quests": quests_out}


class AnswerRequest(BaseModel):
    answer_idx: int


@router.post("/api/map/{loc_id}/quests/{quest_id}/answer")
async def answer_quest(
    loc_id: str, quest_id: str, body: AnswerRequest,
    request: Request, user_id: int = Depends(get_current_user)
):
    all_locs = {**LOCATIONS, **WORLD_LOCATIONS}
    loc = all_locs.get(loc_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    quest = next((q for q in loc.get("quests", []) if q["id"] == quest_id), None)
    if not quest:
        raise HTTPException(404, "Quest not found")

    completed = await game_get_completed_quests(user_id)
    if quest_id in completed:
        return {"correct": None, "xp_earned": 0, "coins_earned": 0, "rep_earned": 0,
                "explanation": quest["explanation"], "new_achievements": [], "already_done": True}

    is_correct = body.answer_idx == quest["correct"]
    today_str = date.today().isoformat()
    week = _week_start()

    xp_earned = 0
    coins_earned = 0
    rep_earned = 0

    if is_correct:
        streak = await game_update_streak(user_id)
        mult = streak_multiplier(streak)
        xp_earned = int(quest["xp"] * mult)
        coins_earned = quest["coins"]
        rep_earned = quest["rep"]
        await game_save_quest_result(user_id, quest_id, loc_id, xp_earned, coins_earned, rep_earned)
        await game_add_weekly_xp(user_id, week, xp_earned)
        for tid, task in DAILY_TASKS.items():
            if task["type"] == "complete_quests":
                await game_update_daily_task(user_id, today_str, tid, 1, task["target"])
            if task["type"] == "correct_answers":
                await game_update_daily_task(user_id, today_str, tid, 1, task["target"])
    else:
        rep_earned = 0  # wrong answers don't earn rep in Mini App (no permanent side effects)

    # Check achievements
    updated_player = await game_get_or_create_player(user_id)
    loc_progress = await game_get_location_progress(user_id)
    completed_now = await game_get_completed_quests(user_id)
    earned = await game_get_achievements(user_id)
    level = parse_level(updated_player["xp"])[0]
    streak = updated_player.get("streak_days", 0) or 0
    coins = updated_player.get("coins", 0)
    total_shares = sum(p.get("shares", 0) for p in loc_progress.values())
    companies = sum(1 for p in loc_progress.values() if p.get("shares", 0) > 0)
    quests_done = len(completed_now)

    checks = {
        "first_quest": quests_done >= 1,
        "quests_10": quests_done >= 10,
        "quests_30": quests_done >= 30,
        "quests_60": quests_done >= 60,
        "quests_all": quests_done >= 90,
        "streak_7": streak >= 7,
        "streak_30": streak >= 30,
        "first_stock": total_shares >= 1,
        "diversify": companies >= 3,
        "rich": coins >= 10000,
        "level_5": level >= 5,
        "level_10": level >= 10,
    }
    new_achievements = []
    for ach_id, condition in checks.items():
        if condition and ach_id not in earned:
            is_new = await game_grant_achievement(user_id, ach_id)
            if is_new:
                ach = ACHIEVEMENTS[ach_id]
                await game_update_player(user_id, xp=ach["xp"], coins=ach["coins"])
                new_achievements.append({"id": ach_id, "name": ach["name"], "emoji": ach["emoji"]})

    return {
        "correct": is_correct,
        "xp_earned": xp_earned,
        "coins_earned": coins_earned,
        "rep_earned": rep_earned,
        "explanation": quest["explanation"],
        "new_achievements": new_achievements,
        "already_done": False,
    }


@router.post("/api/map/{loc_id}/collect")
async def collect_income(loc_id: str, request: Request, user_id: int = Depends(get_current_user)):
    all_locs = {**LOCATIONS, **WORLD_LOCATIONS}
    if loc_id not in all_locs:
        raise HTTPException(404, "Location not found")

    loc_progress = await game_get_location_progress(user_id)
    amount = _collect_amount(all_locs[loc_id], loc_progress, loc_id)
    if amount <= 0:
        return {"collected": 0, "message": "РќРµС‡РµРіРѕ СЃРѕР±РёСЂР°С‚СЊ"}

    await game_collect_income(user_id, loc_id, amount)
    return {"collected": amount, "message": ""}
