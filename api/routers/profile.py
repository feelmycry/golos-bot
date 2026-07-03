from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request

from api.deps import get_current_user
from api.game_data import ACHIEVEMENTS, parse_level, streak_multiplier, get_status
from services.db import (
    game_get_or_create_player,
    game_get_achievements,
    game_get_player_rank,
    game_get_weekly_rank,
    game_get_my_guild,
)

router = APIRouter()


def _week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


@router.get("/api/me")
async def get_me(request: Request, user_id: int = Depends(get_current_user)):
    player = await game_get_or_create_player(user_id)
    level, xp_in, xp_needed = parse_level(player["xp"])
    streak = player.get("streak_days", 0) or 0
    rank = await game_get_player_rank(user_id)
    weekly_rank = await game_get_weekly_rank(user_id, _week_start())
    guild = await game_get_my_guild(user_id)

    return {
        "user_id": user_id,
        "first_name": player.get("first_name", ""),
        "level": level,
        "xp": player["xp"],
        "xp_in_level": xp_in,
        "xp_for_level": xp_needed,
        "coins": player["coins"],
        "streak_days": streak,
        "streak_mult": round(streak_multiplier(streak), 2),
        "rank": rank,
        "weekly_rank": weekly_rank,
        "status": get_status(level),
        "guild": {"id": guild["id"], "name": guild["name"], "emoji": guild["emoji"]} if guild else None,
    }


@router.get("/api/me/achievements")
async def get_achievements(request: Request, user_id: int = Depends(get_current_user)):
    earned = await game_get_achievements(user_id)
    return [
        {
            "id": ach_id,
            "name": ach["name"],
            "emoji": ach["emoji"],
            "desc": ach["desc"],
            "earned": ach_id in earned,
        }
        for ach_id, ach in ACHIEVEMENTS.items()
    ]
