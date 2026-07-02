"""Re-exports game constants and helpers from handlers/game.py."""
from handlers.game import (
    LOCATIONS,
    WORLD_LOCATIONS,
    STOCK_CONFIG,
    ACHIEVEMENTS,
    DAILY_TASKS,
    FUTURE_LOCATIONS,
    parse_level,
    xp_for_level,
    streak_multiplier,
    _stock_price,
    _stock_info as get_stock_info,
)

STATUS_TITLES = {
    1:  "🌱 Стажёр",
    5:  "📊 Аналитик",
    10: "🏆 Младший аналитик",
    15: "💎 Аналитик рынка",
    20: "🦅 Легенда Мосбиржи",
}


def get_status(level: int) -> str:
    title = "🌱 Стажёр"
    for lvl, name in STATUS_TITLES.items():
        if level >= lvl:
            title = name
    return title


def all_locations() -> dict[str, dict]:
    return {**LOCATIONS, **WORLD_LOCATIONS}
