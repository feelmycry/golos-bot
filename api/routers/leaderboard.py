from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request

from api.deps import get_current_user
from services.db import (
    game_get_leaderboard,
    game_get_weekly_leaderboard,
    game_get_guild_leaderboard,
    game_get_player_rank,
    game_get_weekly_rank,
)

router = APIRouter()


def _week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


@router.get("/api/leaderboard")
async def get_leaderboard(request: Request, user_id: int = Depends(get_current_user)):
    week = _week_start()
    alltime = await game_get_leaderboard(15)
    weekly = await game_get_weekly_leaderboard(week, 15)
    guilds = await game_get_guild_leaderboard()
    my_rank = await game_get_player_rank(user_id)
    my_weekly = await game_get_weekly_rank(user_id, week)
    return {
        "alltime": alltime,
        "weekly": weekly,
        "guilds": guilds,
        "my_rank": my_rank,
        "my_weekly_rank": my_weekly,
    }
