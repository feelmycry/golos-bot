# Telegram Mini App — Game Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести игровую механику бота (квесты, биржа, достижения, гильдии, лидерборд) в Telegram Mini App на React + FastAPI.

**Architecture:** FastAPI-сервер (`api/`) запускается рядом с ботом (`python -m api.server`), обращается к тому же `training.db` через уже готовые функции `services/db.py`. React-фронтенд (`miniapp/`) деплоится как статика на Cloudflare Pages; API открывается наружу через Cloudflare Tunnel. Аутентификация — валидация `initData` от Telegram через HMAC-SHA256.

**Tech Stack:** Python 3.11 · FastAPI + uvicorn · aiosqlite (уже в проекте) · React 18 + Vite · @twa-dev/sdk · Cloudflare Tunnel + Pages · pytest + httpx (тесты API)

## Global Constraints

- Python: работаем в директории `C:\Users\thisi\golos\`, запуск через `python -m api.server`
- SQLite DB: `training.db` (путь из `config.DB_PATH`)
- Бот и API используют одну БД, но запускаются как отдельные процессы — никаких shared in-memory state
- Все деньги/очки называются «ИР» (инвестиционные рубли) в UI; в коде переменная `coins`
- Telegram initData валидируется всегда, кроме режима `DEV_USER_ID` (env var для локальной разработки)
- API-порт: 8000; Vite dev-сервер: 5173
- Node.js ≥ 18 необходим для miniapp/
- Все команды PowerShell запускаются из `C:\Users\thisi\golos\`

---

## File Map

```
C:\Users\thisi\golos\
├── api\
│   ├── __init__.py             # пусто
│   ├── server.py               # FastAPI app + uvicorn entry
│   ├── auth.py                 # validate_init_data() + get_current_user()
│   ├── game_data.py            # реэкспорт LOCATIONS, ACHIEVEMENTS и helpers из handlers/game.py
│   └── routers\
│       ├── __init__.py
│       ├── profile.py          # GET /api/me, GET /api/me/achievements
│       ├── map.py              # GET /api/map, POST answer, POST collect
│       ├── exchange.py         # GET /api/stocks, POST buy/sell
│       ├── leaderboard.py      # GET /api/leaderboard (all/weekly/guilds)
│       └── daily.py            # GET /api/daily, POST claim
├── tests\
│   ├── conftest.py             # pytest fixtures: AsyncClient + test DB
│   ├── test_profile.py
│   ├── test_map.py
│   ├── test_exchange.py
│   └── test_leaderboard.py
├── miniapp\
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── src\
│       ├── main.jsx
│       ├── App.jsx             # состояние активного таба
│       ├── api.js              # HTTP-клиент с X-Telegram-Init-Data
│       ├── index.css           # CSS-переменные Telegram + базовые стили
│       ├── components\
│       │   ├── NavBar.jsx
│       │   ├── XPBar.jsx
│       │   └── QuestCard.jsx
│       └── pages\
│           ├── Dashboard.jsx
│           ├── Map.jsx
│           ├── Exchange.jsx
│           ├── Leaderboard.jsx
│           └── Profile.jsx
└── cloudflared-start.bat       # запуск туннеля
```

---

## Task 1: FastAPI scaffold + аутентификация

**Files:**
- Create: `api/__init__.py`
- Create: `api/auth.py`
- Create: `api/server.py`

**Interfaces:**
- Produces: `validate_init_data(init_data: str, bot_token: str) -> dict` (возвращает user dict или raises ValueError)
- Produces: `get_current_user(request: Request) -> int` (FastAPI dependency, возвращает telegram_id)
- Produces: FastAPI `app` запущен на порту 8000

- [ ] **Step 1: Установить зависимости**

```powershell
pip install fastapi uvicorn[standard] httpx pytest pytest-asyncio
```

Ожидаемый вывод: `Successfully installed fastapi-... uvicorn-...`

- [ ] **Step 2: Создать `api/__init__.py`**

Пустой файл.

- [ ] **Step 3: Создать `api/auth.py`**

```python
import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Validates Telegram WebApp initData. Returns user dict or raises ValueError."""
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_received = params.pop("hash", "")
    if not hash_received:
        raise ValueError("Missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(hash_computed, hash_received):
        raise ValueError("Invalid hash")

    return json.loads(params.get("user", "{}"))
```

- [ ] **Step 4: Создать `api/server.py`**

```python
import os
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import TELEGRAM_TOKEN
from api.auth import validate_init_data

DEV_USER_ID = int(os.getenv("DEV_USER_ID", "0"))

app = FastAPI(title="Golos Game API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_current_user(request: Request) -> int:
    if DEV_USER_ID:
        return DEV_USER_ID
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data")
    try:
        user_data = validate_init_data(init_data, TELEGRAM_TOKEN)
        return int(user_data["id"])
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid init data")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 5: Проверить запуск**

```powershell
$env:DEV_USER_ID = "12345"; python -m api.server
```

В другом терминале:
```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

Ожидаемый ответ: `{"status": "ok"}`

- [ ] **Step 6: Создать `tests/conftest.py`**

```python
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["DEV_USER_ID"] = "99999"  # bypass auth in tests

from api.server import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [ ] **Step 7: Написать smoke-тест**

Создать `tests/test_health.py`:
```python
import pytest

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 8: Запустить тест**

```powershell
pytest tests/test_health.py -v
```

Ожидаемый вывод: `PASSED`

- [ ] **Step 9: Commit**

```powershell
git add api/ tests/
git commit -m "feat: FastAPI scaffold with Telegram initData auth"
```

---

## Task 2: Game data helper

**Files:**
- Create: `api/game_data.py`

**Interfaces:**
- Produces: `LOCATIONS: dict[str, dict]` — все локации с квестами
- Produces: `WORLD_LOCATIONS: dict[str, dict]` — мировые локации
- Produces: `STOCK_CONFIG: dict[str, dict]` — конфиг акций
- Produces: `ACHIEVEMENTS: dict[str, dict]` — все достижения
- Produces: `DAILY_TASKS: dict[str, dict]` — ежедневные задания
- Produces: `parse_level(total_xp: int) -> tuple[int, int, int]` — (level, xp_in, xp_needed)
- Produces: `get_stock_info(loc_id: str) -> tuple[int, float]` — (price, change_pct)
- Produces: `STATUS_TITLES: dict[int, str]` — уровень → статус

- [ ] **Step 1: Создать `api/game_data.py`**

```python
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
```

- [ ] **Step 2: Проверить импорт в Python shell**

```powershell
python -c "from api.game_data import LOCATIONS, get_stock_info; print(list(LOCATIONS.keys())[:3]); print(get_stock_info('sber'))"
```

Ожидаемый вывод: `['sber', 'lukoil', 'gazprom']` и кортеж `(int, float)`

- [ ] **Step 3: Commit**

```powershell
git add api/game_data.py
git commit -m "feat: game_data helper — re-exports game constants for API"
```

---

## Task 3: Profile endpoints

**Files:**
- Create: `api/routers/__init__.py`
- Create: `api/routers/profile.py`
- Modify: `api/server.py` — добавить include_router

**Interfaces:**
- Consumes: `get_current_user` из `api/server.py`; `game_get_or_create_player`, `game_get_achievements`, `game_get_player_rank`, `game_get_weekly_rank`, `game_get_my_weekly_xp`, `game_get_my_guild` из `services/db.py`; `parse_level`, `streak_multiplier`, `get_status` из `api/game_data.py`
- Produces: `GET /api/me` → ProfileResponse; `GET /api/me/achievements` → list[AchievementResponse]

**Форматы ответов:**

`GET /api/me`:
```json
{
  "user_id": 123, "first_name": "Алексей",
  "level": 12, "xp": 12340, "xp_in_level": 420, "xp_for_level": 550,
  "coins": 2340, "streak_days": 14, "streak_mult": 1.1,
  "rank": 2, "weekly_rank": 3, "status": "💎 Аналитик рынка",
  "guild": {"id": 1, "name": "Альфа-Прайм", "emoji": "🛡"}
}
```

`GET /api/me/achievements`:
```json
[
  {"id": "first_quest", "name": "Первый шаг", "emoji": "🌱", "desc": "...", "earned": true},
  {"id": "quests_10", "name": "Разогрев", "emoji": "🔥", "desc": "...", "earned": false}
]
```

- [ ] **Step 1: Создать `api/routers/__init__.py`**

Пустой файл.

- [ ] **Step 2: Написать failing тест для /api/me**

Создать `tests/test_profile.py`:
```python
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
```

- [ ] **Step 3: Запустить тест — убедиться что FAIL**

```powershell
pytest tests/test_profile.py -v
```

Ожидаемый вывод: `FAILED` (404 — роутер ещё не подключён)

- [ ] **Step 4: Создать `api/routers/profile.py`**

```python
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Request

from api.server import get_current_user
from api.game_data import ACHIEVEMENTS, parse_level, xp_for_level, streak_multiplier, get_status
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
```

- [ ] **Step 5: Подключить роутер в `api/server.py`**

Добавить после блока `app.add_middleware(...)`:
```python
from api.routers import profile as profile_router
app.include_router(profile_router.router)
```

- [ ] **Step 6: Запустить тест — убедиться что PASS**

```powershell
$env:DEV_USER_ID = "99999"; pytest tests/test_profile.py -v
```

Ожидаемый вывод: `2 passed`

- [ ] **Step 7: Commit**

```powershell
git add api/routers/ tests/test_profile.py
git commit -m "feat: profile endpoints GET /api/me and /api/me/achievements"
```

---

## Task 4: Map + Quest endpoints

**Files:**
- Create: `api/routers/map.py`
- Modify: `api/server.py` — подключить роутер

**Interfaces:**
- Consumes: `LOCATIONS`, `WORLD_LOCATIONS`, `FUTURE_LOCATIONS`, `DAILY_TASKS`, `parse_level`, `streak_multiplier` из `api/game_data.py`; `game_get_or_create_player`, `game_get_location_progress`, `game_get_completed_quests`, `game_save_quest_result`, `game_update_daily_task`, `game_update_streak`, `game_get_achievements`, `game_grant_achievement`, `game_add_weekly_xp`, `game_update_player` из `services/db.py`
- Produces: `GET /api/map` → список локаций; `GET /api/map/{loc_id}` → локация + список квестов; `POST /api/map/{loc_id}/quests/{quest_id}/answer` → результат ответа; `POST /api/map/{loc_id}/collect` → сбор пассивного дохода

**Формат GET /api/map (элемент массива):**
```json
{
  "id": "sber", "name": "СБЕР-СИТИ", "emoji": "🏦", "sector": "Финансы",
  "min_level": 1, "unlocked": true,
  "quests_total": 4, "quests_done": 3,
  "reputation": 850, "rep_rank": "Доверенный", "shares": 2,
  "income_per_hour": 8, "can_collect": true, "collect_amount": 24
}
```

**Формат POST /api/map/{loc_id}/quests/{quest_id}/answer response:**
```json
{
  "correct": true, "xp_earned": 132, "coins_earned": 80, "rep_earned": 150,
  "explanation": "...", "new_achievements": []
}
```

- [ ] **Step 1: Написать failing тесты**

Создать `tests/test_map.py`:
```python
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
```

- [ ] **Step 2: Запустить — убедиться что FAIL**

```powershell
pytest tests/test_map.py -v
```

- [ ] **Step 3: Создать `api/routers/map.py`**

```python
import math
from datetime import date, timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.server import get_current_user
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
    game_get_daily_progress,
)

router = APIRouter()


def _week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def _rep_rank(loc: dict, reputation: int) -> str:
    thresholds = loc.get("rep_thresholds", [0])
    ranks = loc.get("rep_rank", ["Новичок"])
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
    dt = datetime.fromisoformat(last)
    hours = max(0, (datetime.now() - dt).total_seconds() / 3600)
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

    player = await game_get_or_create_player(user_id)
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
        rep_earned = quest["rep"] // 3
        await game_save_quest_result(user_id, quest_id, loc_id, 0, 0, rep_earned)
        for tid, task in DAILY_TASKS.items():
            if task["type"] == "correct_answers" and not is_correct:
                pass  # only correct answers count

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
        return {"collected": 0, "message": "Нечего собирать"}

    await game_collect_income(user_id, loc_id, amount)
    return {"collected": amount}
```

- [ ] **Step 4: Подключить роутер в `api/server.py`**

Добавить в блок include_router:
```python
from api.routers import map as map_router
app.include_router(map_router.router)
```

- [ ] **Step 5: Запустить тесты**

```powershell
pytest tests/test_map.py -v
```

Ожидаемый вывод: `3 passed`

- [ ] **Step 6: Commit**

```powershell
git add api/routers/map.py tests/test_map.py
git commit -m "feat: map endpoints — locations, quest detail, answer, collect income"
```

---

## Task 5: Exchange endpoints

**Files:**
- Create: `api/routers/exchange.py`
- Modify: `api/server.py` — подключить роутер

**Interfaces:**
- Consumes: `STOCK_CONFIG`, `get_stock_info` из `api/game_data.py`; `game_get_location_progress`, `game_buy_shares`, `game_sell_shares`, `game_get_or_create_player`, `game_update_daily_task` из `services/db.py`
- Produces: `GET /api/stocks` → список акций с ценами и долями пользователя; `POST /api/stocks/{loc_id}/buy` → результат покупки; `POST /api/stocks/{loc_id}/sell` → результат продажи

**Формат GET /api/stocks (элемент):**
```json
{"id": "sber", "ticker": "SBER", "name": "Сбербанк", "price": 307, "change_pct": 2.3, "shares_owned": 2}
```

- [ ] **Step 1: Написать failing тесты**

Создать `tests/test_exchange.py`:
```python
import pytest

@pytest.mark.asyncio
async def test_get_stocks(client):
    r = await client.get("/api/stocks")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 9
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
```

- [ ] **Step 2: Запустить — убедиться что FAIL**

```powershell
pytest tests/test_exchange.py -v
```

- [ ] **Step 3: Создать `api/routers/exchange.py`**

```python
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.server import get_current_user
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
        "message": "" if success else "Недостаточно ИР",
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
        "message": "" if success else "Недостаточно акций",
    }
```

- [ ] **Step 4: Подключить в `api/server.py`**

```python
from api.routers import exchange as exchange_router
app.include_router(exchange_router.router)
```

- [ ] **Step 5: Запустить тесты**

```powershell
pytest tests/test_exchange.py -v
```

Ожидаемый вывод: `2 passed`

- [ ] **Step 6: Commit**

```powershell
git add api/routers/exchange.py tests/test_exchange.py
git commit -m "feat: exchange endpoints — stock list, buy, sell"
```

---

## Task 6: Leaderboard + Daily endpoints

**Files:**
- Create: `api/routers/leaderboard.py`
- Create: `api/routers/daily.py`
- Modify: `api/server.py`

**Interfaces:**
- Consumes: `game_get_leaderboard`, `game_get_weekly_leaderboard`, `game_get_guild_leaderboard`, `game_get_player_rank`, `game_get_weekly_rank`, `game_get_daily_progress`, `game_claim_daily_reward` из `services/db.py`; `DAILY_TASKS` из `api/game_data.py`
- Produces: `GET /api/leaderboard` → {alltime, weekly, guilds, my_rank, my_weekly_rank}; `GET /api/daily` → список заданий с прогрессом; `POST /api/daily/{task_id}/claim` → результат получения награды

- [ ] **Step 1: Написать failing тесты**

Создать `tests/test_leaderboard.py`:
```python
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
```

- [ ] **Step 2: Запустить — убедиться что FAIL**

```powershell
pytest tests/test_leaderboard.py -v
```

- [ ] **Step 3: Создать `api/routers/leaderboard.py`**

```python
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request

from api.server import get_current_user
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
```

- [ ] **Step 4: Создать `api/routers/daily.py`**

```python
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request

from api.server import get_current_user
from api.game_data import DAILY_TASKS
from services.db import game_get_daily_progress, game_claim_daily_reward


router = APIRouter()


def _today_task_ids() -> list[str]:
    """Returns the 3 tasks for today (deterministic by weekday)."""
    import hashlib
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
    return {"success": success, "message": "" if success else "Задание не выполнено или уже получено"}
```

- [ ] **Step 5: Подключить в `api/server.py`**

```python
from api.routers import leaderboard as lb_router, daily as daily_router
app.include_router(lb_router.router)
app.include_router(daily_router.router)
```

- [ ] **Step 6: Запустить все тесты**

```powershell
pytest tests/ -v
```

Ожидаемый вывод: все тесты `PASSED`

- [ ] **Step 7: Commit**

```powershell
git add api/routers/leaderboard.py api/routers/daily.py tests/test_leaderboard.py
git commit -m "feat: leaderboard and daily task endpoints"
```

---

## Task 7: React + Vite scaffold + NavBar

**Files:**
- Create: `miniapp/` (Vite project)
- Create: `miniapp/src/App.jsx`
- Create: `miniapp/src/api.js`
- Create: `miniapp/src/index.css`
- Create: `miniapp/src/components/NavBar.jsx`
- Create: `miniapp/src/components/XPBar.jsx`

**Interfaces:**
- Produces: `useApi(path, opts?)` hook → `{data, loading, error, refetch}`
- Produces: `NavBar` с 5 вкладками: Главная / Карта / Биржа / Рейтинг / Профиль
- Produces: `XPBar({xpIn, xpFor, level})` — прогресс XP

- [ ] **Step 1: Создать Vite-проект**

```powershell
npm create vite@latest miniapp -- --template react
cd miniapp
npm install
npm install @twa-dev/sdk
```

- [ ] **Step 2: Создать `miniapp/src/api.js`**

```js
const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getInitData() {
  try {
    return window.Telegram?.WebApp?.initData || "";
  } catch {
    return "";
  }
}

export async function apiFetch(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export function useApi(path, deps = []) {
  const [state, setState] = React.useState({ data: null, loading: true, error: null });

  const refetch = React.useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    apiFetch(path)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error) => setState({ data: null, loading: false, error }));
  }, [path]);

  React.useEffect(() => { refetch(); }, [refetch, ...deps]);

  return { ...state, refetch };
}
```

Добавить `import React from 'react';` в начало файла.

- [ ] **Step 3: Создать `miniapp/src/index.css`**

```css
:root {
  --bg: var(--tg-theme-bg-color, #ffffff);
  --text: var(--tg-theme-text-color, #000000);
  --hint: var(--tg-theme-hint-color, #999999);
  --link: var(--tg-theme-link-color, #2481cc);
  --btn: var(--tg-theme-button-color, #2481cc);
  --btn-text: var(--tg-theme-button-text-color, #ffffff);
  --secondary: var(--tg-theme-secondary-bg-color, #f0f0f0);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }

.page { padding: 12px 12px 72px; }
.card { background: var(--secondary); border-radius: 12px; padding: 14px; margin-bottom: 10px; }
.badge { display: inline-block; background: var(--btn); color: var(--btn-text); border-radius: 8px; padding: 2px 8px; font-size: 12px; }
.btn { display: block; width: 100%; padding: 12px; background: var(--btn); color: var(--btn-text); border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; }
.btn:disabled { opacity: 0.5; }
.btn-outline { background: transparent; border: 1.5px solid var(--btn); color: var(--btn); }
```

- [ ] **Step 4: Создать `miniapp/src/components/NavBar.jsx`**

```jsx
const TABS = [
  { id: "dashboard", emoji: "🏠", label: "Главная" },
  { id: "map",       emoji: "🗺",  label: "Карта" },
  { id: "exchange",  emoji: "📈",  label: "Биржа" },
  { id: "leaders",   emoji: "🏆",  label: "Рейтинг" },
  { id: "profile",   emoji: "👤",  label: "Профиль" },
];

export default function NavBar({ active, onSelect }) {
  return (
    <nav style={{
      position: "fixed", bottom: 0, left: 0, right: 0,
      display: "flex", background: "var(--secondary)",
      borderTop: "1px solid rgba(0,0,0,0.08)", paddingBottom: "env(safe-area-inset-bottom)"
    }}>
      {TABS.map((t) => (
        <button key={t.id} onClick={() => onSelect(t.id)}
          style={{
            flex: 1, padding: "8px 0", border: "none", background: "none", cursor: "pointer",
            color: active === t.id ? "var(--btn)" : "var(--hint)", fontSize: 11,
            display: "flex", flexDirection: "column", alignItems: "center", gap: 2
          }}>
          <span style={{ fontSize: 22 }}>{t.emoji}</span>
          {t.label}
        </button>
      ))}
    </nav>
  );
}
```

- [ ] **Step 5: Создать `miniapp/src/components/XPBar.jsx`**

```jsx
export default function XPBar({ xpIn, xpFor, level }) {
  const pct = xpFor > 0 ? Math.min(100, Math.round((xpIn / xpFor) * 100)) : 0;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--hint)", marginBottom: 4 }}>
        <span>Ур. {level}</span>
        <span>{xpIn} / {xpFor} XP</span>
      </div>
      <div style={{ background: "rgba(0,0,0,0.1)", borderRadius: 8, height: 8, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, background: "var(--btn)", height: "100%", borderRadius: 8, transition: "width 0.5s" }} />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Создать `miniapp/src/App.jsx`**

```jsx
import { useState } from "react";
import NavBar from "./components/NavBar";
import Dashboard from "./pages/Dashboard";
import Map from "./pages/Map";
import Exchange from "./pages/Exchange";
import Leaderboard from "./pages/Leaderboard";
import Profile from "./pages/Profile";

const PAGES = { dashboard: Dashboard, map: Map, exchange: Exchange, leaders: Leaderboard, profile: Profile };

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const Page = PAGES[tab];
  return (
    <>
      <Page />
      <NavBar active={tab} onSelect={setTab} />
    </>
  );
}
```

- [ ] **Step 7: Создать `miniapp/src/main.jsx`**

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

try { window.Telegram?.WebApp?.ready(); } catch {}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
```

- [ ] **Step 8: Создать заглушки страниц (чтобы App компилировался)**

Создать `miniapp/src/pages/Dashboard.jsx`, `Map.jsx`, `Exchange.jsx`, `Leaderboard.jsx`, `Profile.jsx` — каждый файл:
```jsx
export default function Dashboard() { return <div className="page"><h2>Загрузка...</h2></div>; }
```
(заменить `Dashboard` на соответствующее имя)

- [ ] **Step 9: Создать `miniapp/.env.local`**

```
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 10: Запустить dev-сервер**

```powershell
cd miniapp; npm run dev
```

Открыть `http://localhost:5173` в браузере. Должна отображаться нижняя навигация с 5 кнопками.

- [ ] **Step 11: Commit**

```powershell
cd ..; git add miniapp/
git commit -m "feat: React Mini App scaffold — NavBar, XPBar, routing shell"
```

---

## Task 8: Dashboard page

**Files:**
- Modify: `miniapp/src/pages/Dashboard.jsx`
- Create: `miniapp/src/components/DailyTask.jsx`

**Interfaces:**
- Consumes: `GET /api/me`, `GET /api/daily`

- [ ] **Step 1: Создать `miniapp/src/components/DailyTask.jsx`**

```jsx
import { apiFetch } from "../api";
import { useState } from "react";

export default function DailyTask({ task, onClaim }) {
  const [busy, setBusy] = useState(false);
  const pct = Math.min(100, Math.round((task.progress / task.target) * 100));

  async function handleClaim() {
    setBusy(true);
    try {
      await apiFetch(`/api/daily/${task.id}/claim`, { method: "POST" });
      onClaim();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 14 }}>
        <span>{task.desc}</span>
        <span style={{ color: "var(--hint)" }}>{task.progress}/{task.target}</span>
      </div>
      <div style={{ background: "rgba(0,0,0,0.1)", borderRadius: 6, height: 6, marginBottom: 6 }}>
        <div style={{ width: `${pct}%`, background: task.completed ? "#4cd964" : "var(--btn)", height: "100%", borderRadius: 6 }} />
      </div>
      {task.completed && !task.claimed && (
        <button className="btn" disabled={busy} onClick={handleClaim}>
          Получить +{task.coins} ИР, +{task.xp} XP
        </button>
      )}
      {task.claimed && <div style={{ color: "#4cd964", fontSize: 13 }}>✅ Получено</div>}
    </div>
  );
}
```

- [ ] **Step 2: Реализовать `miniapp/src/pages/Dashboard.jsx`**

```jsx
import { useApi } from "../api";
import XPBar from "../components/XPBar";
import DailyTask from "../components/DailyTask";

export default function Dashboard() {
  const { data: me, loading: meLoading, refetch: refetchMe } = useApi("/api/me");
  const { data: daily, loading: dailyLoading, refetch: refetchDaily } = useApi("/api/daily");

  if (meLoading || dailyLoading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  const streak = me?.streak_days || 0;

  return (
    <div className="page">
      {/* Header */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17 }}>{me?.first_name || "Игрок"}</div>
            <div style={{ color: "var(--hint)", fontSize: 13 }}>{me?.status}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>💰 {me?.coins?.toLocaleString()} ИР</div>
            {streak > 0 && <div style={{ fontSize: 12, color: "#ff9500" }}>🔥 {streak} дн. +{Math.round((me.streak_mult - 1) * 100)}% XP</div>}
          </div>
        </div>
        <XPBar xpIn={me?.xp_in_level || 0} xpFor={me?.xp_for_level || 1} level={me?.level || 1} />
      </div>

      {/* Guild */}
      {me?.guild && (
        <div className="card" style={{ marginBottom: 12 }}>
          <span>{me.guild.emoji} <b>{me.guild.name}</b></span>
          <span style={{ float: "right", color: "var(--hint)", fontSize: 13 }}>Рейтинг #{me.rank}</span>
        </div>
      )}

      {/* Daily tasks */}
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 10 }}>📋 Задания дня</div>
        {daily?.tasks?.map((t) => (
          <DailyTask key={t.id} task={t} onClaim={() => { refetchDaily(); refetchMe(); }} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Проверить в браузере**

Запустить API: `$env:DEV_USER_ID = "99999"; python -m api.server`
Запустить frontend: `cd miniapp; npm run dev`

Открыть `http://localhost:5173`. Проверить что:
- Отображается профиль с XP баром
- Показываются задания дня
- Кнопка "Получить" появляется если задание выполнено

- [ ] **Step 4: Commit**

```powershell
cd ..; git add miniapp/src/pages/Dashboard.jsx miniapp/src/components/DailyTask.jsx
git commit -m "feat: Dashboard page — profile, XP bar, streak, daily tasks"
```

---

## Task 9: Map page с квестами

**Files:**
- Modify: `miniapp/src/pages/Map.jsx`
- Create: `miniapp/src/components/QuestCard.jsx`

**Interfaces:**
- Consumes: `GET /api/map`, `GET /api/map/{loc_id}`, `POST /api/map/{loc_id}/quests/{quest_id}/answer`, `POST /api/map/{loc_id}/collect`

- [ ] **Step 1: Создать `miniapp/src/components/QuestCard.jsx`**

```jsx
import { useState } from "react";
import { apiFetch } from "../api";

export default function QuestCard({ quest, locId, onDone }) {
  const [selected, setSelected] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(idx) {
    if (result || busy) return;
    setSelected(idx);
    setBusy(true);
    try {
      const data = await apiFetch(`/api/map/${locId}/quests/${quest.id}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer_idx: idx }),
      });
      setResult(data);
    } finally {
      setBusy(false);
    }
  }

  const NUMS = ["①", "②", "③", "④"];

  return (
    <div className="card">
      <div style={{ fontSize: 13, color: "var(--hint)", marginBottom: 6 }}>{quest.story}</div>
      <div style={{ fontWeight: 600, marginBottom: 10 }}>{quest.question}</div>
      {quest.options.map((opt, i) => {
        let bg = "var(--secondary)";
        if (result) {
          if (result.correct && i === selected) bg = "#4cd96422";
          else if (!result.correct && i === selected) bg = "#ff3b3022";
        }
        return (
          <button key={i} onClick={() => submit(i)} disabled={!!result || busy}
            style={{ display: "block", width: "100%", textAlign: "left", padding: "10px 12px",
              marginBottom: 6, background: bg, border: "1.5px solid rgba(0,0,0,0.08)",
              borderRadius: 8, cursor: result ? "default" : "pointer", fontSize: 14 }}>
            {NUMS[i]} {opt}
          </button>
        );
      })}
      {result && (
        <div style={{ marginTop: 10 }}>
          <div style={{ color: result.correct ? "#4cd964" : "#ff3b30", fontWeight: 600, marginBottom: 4 }}>
            {result.correct ? `✅ +${result.xp_earned} XP, +${result.coins_earned} ИР` : "❌ Неверно"}
          </div>
          <div style={{ fontSize: 13, color: "var(--hint)" }}>{result.explanation}</div>
          {result.new_achievements?.map((a) => (
            <div key={a.id} style={{ marginTop: 6, color: "#ff9500" }}>🏅 Достижение: {a.emoji} {a.name}</div>
          ))}
          <button className="btn" style={{ marginTop: 10 }} onClick={onDone}>← К локации</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Реализовать `miniapp/src/pages/Map.jsx`**

```jsx
import { useState } from "react";
import { useApi, apiFetch } from "../api";
import QuestCard from "../components/QuestCard";

export default function Map() {
  const { data: locations, loading, refetch } = useApi("/api/map");
  const [selectedLoc, setSelectedLoc] = useState(null);
  const [locDetail, setLocDetail] = useState(null);
  const [selectedQuest, setSelectedQuest] = useState(null);
  const [collecting, setCollecting] = useState(false);

  async function openLocation(loc) {
    if (!loc.unlocked || !loc.id) return;
    setSelectedLoc(loc);
    setLocDetail(null);
    const detail = await apiFetch(`/api/map/${loc.id}`);
    setLocDetail(detail);
  }

  async function collect(locId) {
    setCollecting(true);
    try {
      await apiFetch(`/api/map/${locId}/collect`, { method: "POST" });
      refetch();
    } finally {
      setCollecting(false);
    }
  }

  if (loading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  // Quest view
  if (selectedQuest && selectedLoc) {
    return (
      <div className="page">
        <button onClick={() => setSelectedQuest(null)} style={{ background: "none", border: "none", color: "var(--btn)", fontSize: 16, cursor: "pointer", marginBottom: 10 }}>← {selectedLoc.name}</button>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>{selectedQuest.title}</div>
        <QuestCard quest={selectedQuest} locId={selectedLoc.id} onDone={() => { setSelectedQuest(null); openLocation(selectedLoc); }} />
      </div>
    );
  }

  // Location detail view
  if (selectedLoc && locDetail) {
    return (
      <div className="page">
        <button onClick={() => setSelectedLoc(null)} style={{ background: "none", border: "none", color: "var(--btn)", fontSize: 16, cursor: "pointer", marginBottom: 10 }}>← Карта</button>
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{selectedLoc.emoji} {locDetail.name}</div>
          <div style={{ color: "var(--hint)", fontSize: 13, margin: "6px 0" }}>{locDetail.sector}</div>
          <div style={{ fontSize: 13 }}>{locDetail.description?.replace(/<[^>]+>/g, "")}</div>
          {selectedLoc.can_collect && (
            <button className="btn" style={{ marginTop: 10 }} disabled={collecting}
              onClick={() => collect(selectedLoc.id)}>
              Собрать {selectedLoc.collect_amount} ИР пассивного дохода
            </button>
          )}
        </div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Квесты ({selectedLoc.quests_done}/{selectedLoc.quests_total})</div>
        {locDetail.quests?.map((q) => (
          <div key={q.id} className="card" onClick={() => !q.completed && setSelectedQuest(q)}
            style={{ cursor: q.completed ? "default" : "pointer", opacity: q.completed ? 0.6 : 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{q.title}</div>
              <div style={{ fontSize: 12, color: "var(--hint)" }}>+{q.xp} XP · +{q.coins} ИР</div>
            </div>
            {q.completed ? <span style={{ color: "#4cd964" }}>✅</span> : <span style={{ color: "var(--btn)" }}>▶</span>}
          </div>
        ))}
      </div>
    );
  }

  // Map overview
  return (
    <div className="page">
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12 }}>🗺 Карта локаций</div>
      {locations?.map((loc, i) => (
        <div key={loc.id || i} className="card" onClick={() => openLocation(loc)}
          style={{ cursor: loc.unlocked && loc.id ? "pointer" : "default", opacity: loc.unlocked ? 1 : 0.5 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{loc.emoji} {loc.name}</div>
              <div style={{ fontSize: 12, color: "var(--hint)" }}>{loc.sector} {!loc.unlocked ? `· Ур. ${loc.min_level}` : ""}</div>
            </div>
            <div style={{ textAlign: "right", fontSize: 12 }}>
              {loc.unlocked && loc.id
                ? <><span className="badge">{loc.quests_done}/{loc.quests_total}</span>{loc.can_collect && <div style={{ color: "#ff9500", marginTop: 2 }}>💰 {loc.collect_amount}</div>}</>
                : <span>🔒</span>
              }
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Проверить в браузере**

Открыть `http://localhost:5173`, перейти на вкладку Карта:
- Отображаются локации (разблокированные и заблокированные)
- Клик по локации открывает список квестов
- Клик по квесту показывает вопрос с вариантами ответа
- После ответа отображается объяснение и количество XP

- [ ] **Step 4: Commit**

```powershell
git add miniapp/src/pages/Map.jsx miniapp/src/components/QuestCard.jsx
git commit -m "feat: Map page — location list, quest detail, answer flow"
```

---

## Task 10: Exchange page

**Files:**
- Modify: `miniapp/src/pages/Exchange.jsx`

**Interfaces:**
- Consumes: `GET /api/stocks`, `GET /api/me`, `POST /api/stocks/{loc_id}/buy`, `POST /api/stocks/{loc_id}/sell`

- [ ] **Step 1: Реализовать `miniapp/src/pages/Exchange.jsx`**

```jsx
import { useState } from "react";
import { useApi, apiFetch } from "../api";

export default function Exchange() {
  const { data: stocks, loading, refetch } = useApi("/api/stocks");
  const { data: me, refetch: refetchMe } = useApi("/api/me");
  const [selected, setSelected] = useState(null);
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function trade(action) {
    if (!selected || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await apiFetch(`/api/stocks/${selected.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ qty: Number(qty) }),
      });
      setMsg(res.success ? `${action === "buy" ? "Куплено" : "Продано"} ${qty} акций` : res.message);
      refetch();
      refetchMe();
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  if (selected) {
    const stock = stocks?.find((s) => s.id === selected.id) || selected;
    return (
      <div className="page">
        <button onClick={() => { setSelected(null); setMsg(""); }} style={{ background: "none", border: "none", color: "var(--btn)", fontSize: 16, cursor: "pointer", marginBottom: 10 }}>← Биржа</button>
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: 18 }}>{stock.name}</div>
          <div style={{ color: "var(--hint)", fontSize: 13 }}>{stock.ticker}</div>
          <div style={{ fontSize: 28, fontWeight: 700, margin: "10px 0" }}>{stock.price} ИР</div>
          <div style={{ color: stock.change_pct >= 0 ? "#4cd964" : "#ff3b30", fontSize: 15 }}>
            {stock.change_pct >= 0 ? "▲" : "▼"} {Math.abs(stock.change_pct).toFixed(2)}%
          </div>
          <div style={{ marginTop: 10, color: "var(--hint)", fontSize: 13 }}>Ваши акции: {stock.shares_owned}</div>
        </div>
        <div className="card">
          <div style={{ marginBottom: 10, fontWeight: 600 }}>Количество</div>
          <input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)}
            style={{ width: "100%", padding: "10px", border: "1px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 16, background: "var(--bg)", color: "var(--text)", marginBottom: 10 }} />
          <div style={{ fontSize: 13, color: "var(--hint)", marginBottom: 10 }}>
            Сумма: {stock.price * Number(qty)} ИР · Баланс: {me?.coins?.toLocaleString()} ИР
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" disabled={busy} onClick={() => trade("buy")}>Купить</button>
            <button className="btn btn-outline" disabled={busy || stock.shares_owned === 0} onClick={() => trade("sell")}>Продать</button>
          </div>
          {msg && <div style={{ marginTop: 8, textAlign: "center", color: "var(--hint)", fontSize: 13 }}>{msg}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 18 }}>📈 Биржа</div>
        <div style={{ color: "var(--hint)", fontSize: 13 }}>💰 {me?.coins?.toLocaleString()} ИР</div>
      </div>
      {stocks?.map((s) => (
        <div key={s.id} className="card" onClick={() => { setSelected(s); setQty(1); setMsg(""); }}
          style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 600 }}>{s.name}</div>
            <div style={{ fontSize: 12, color: "var(--hint)" }}>{s.ticker}{s.shares_owned > 0 ? ` · Ваши: ${s.shares_owned}` : ""}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 700 }}>{s.price} ИР</div>
            <div style={{ fontSize: 12, color: s.change_pct >= 0 ? "#4cd964" : "#ff3b30" }}>
              {s.change_pct >= 0 ? "▲" : "▼"} {Math.abs(s.change_pct).toFixed(2)}%
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Проверить в браузере**

Вкладка Биржа:
- Список акций с ценой и процентом изменения (зелёный/красный)
- Клик открывает детальный вид с кнопками Купить/Продать
- После покупки баланс обновляется

- [ ] **Step 3: Commit**

```powershell
git add miniapp/src/pages/Exchange.jsx
git commit -m "feat: Exchange page — stock list, buy/sell flow"
```

---

## Task 11: Leaderboard и Profile pages

**Files:**
- Modify: `miniapp/src/pages/Leaderboard.jsx`
- Modify: `miniapp/src/pages/Profile.jsx`

**Interfaces:**
- Consumes: `GET /api/leaderboard`, `GET /api/me`, `GET /api/me/achievements`

- [ ] **Step 1: Реализовать `miniapp/src/pages/Leaderboard.jsx`**

```jsx
import { useState } from "react";
import { useApi } from "../api";

const MEDALS = ["🥇", "🥈", "🥉"];

export default function Leaderboard() {
  const { data, loading } = useApi("/api/leaderboard");
  const [tab, setTab] = useState("alltime");

  if (loading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  const TABS = [
    { id: "alltime", label: "Всё время" },
    { id: "weekly",  label: "Неделя" },
    { id: "guilds",  label: "Гильдии" },
  ];

  const list = data?.[tab] || [];
  const myRank = tab === "weekly" ? data?.my_weekly_rank : data?.my_rank;

  return (
    <div className="page">
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 12 }}>🏆 Рейтинг</div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ flex: 1, padding: "8px 0", borderRadius: 8, border: "none", cursor: "pointer",
              background: tab === t.id ? "var(--btn)" : "var(--secondary)", color: tab === t.id ? "var(--btn-text)" : "var(--text)", fontWeight: 600, fontSize: 13 }}>
            {t.label}
          </button>
        ))}
      </div>
      {myRank && myRank > 3 && (
        <div className="card" style={{ marginBottom: 8, borderLeft: "3px solid var(--btn)" }}>
          Ваша позиция: #{myRank}
        </div>
      )}
      {list.map((entry, i) => (
        <div key={i} className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: i < 3 ? 22 : 16, minWidth: 28 }}>{i < 3 ? MEDALS[i] : `${i + 1}.`}</span>
            <div>
              <div style={{ fontWeight: 600 }}>{tab === "guilds" ? (entry.emoji + " " + entry.name) : (entry.first_name || `ID ${entry.user_id}`)}</div>
              {tab !== "guilds" && <div style={{ fontSize: 12, color: "var(--hint)" }}>{entry.username ? `@${entry.username}` : ""}</div>}
            </div>
          </div>
          <div style={{ fontWeight: 700 }}>
            {tab === "guilds" ? entry.total_xp : tab === "weekly" ? entry.xp_gained : entry.xp} XP
          </div>
        </div>
      ))}
      {list.length === 0 && <div style={{ textAlign: "center", color: "var(--hint)", paddingTop: 30 }}>Пока никого нет</div>}
    </div>
  );
}
```

- [ ] **Step 2: Реализовать `miniapp/src/pages/Profile.jsx`**

```jsx
import { useApi } from "../api";

export default function Profile() {
  const { data: me, loading: meLoading } = useApi("/api/me");
  const { data: achievements, loading: achLoading } = useApi("/api/me/achievements");

  if (meLoading || achLoading) return <div className="page" style={{ textAlign: "center", paddingTop: 40 }}>⏳</div>;

  const earned = achievements?.filter((a) => a.earned) || [];
  const locked = achievements?.filter((a) => !a.earned) || [];

  return (
    <div className="page">
      <div className="card" style={{ textAlign: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 40, marginBottom: 6 }}>👤</div>
        <div style={{ fontWeight: 700, fontSize: 20 }}>{me?.first_name}</div>
        <div style={{ color: "var(--hint)", marginBottom: 8 }}>{me?.status}</div>
        <div style={{ display: "flex", justifyContent: "space-around", fontSize: 14 }}>
          <div><b>{me?.xp?.toLocaleString()}</b><div style={{ color: "var(--hint)" }}>XP</div></div>
          <div><b>{me?.coins?.toLocaleString()}</b><div style={{ color: "var(--hint)" }}>ИР</div></div>
          <div><b>{me?.streak_days}</b><div style={{ color: "var(--hint)" }}>дн. серия</div></div>
          <div><b>#{me?.rank}</b><div style={{ color: "var(--hint)" }}>место</div></div>
        </div>
      </div>
      {me?.guild && (
        <div className="card" style={{ marginBottom: 12 }}>
          <span>{me.guild.emoji} <b>{me.guild.name}</b></span>
        </div>
      )}
      <div style={{ fontWeight: 600, marginBottom: 8 }}>🏅 Достижения ({earned.length}/{achievements?.length})</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
        {earned.map((a) => (
          <div key={a.id} className="card" style={{ textAlign: "center", padding: "10px 8px" }}>
            <div style={{ fontSize: 28 }}>{a.emoji}</div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{a.name}</div>
            <div style={{ fontSize: 11, color: "var(--hint)" }}>{a.desc}</div>
          </div>
        ))}
        {locked.map((a) => (
          <div key={a.id} className="card" style={{ textAlign: "center", padding: "10px 8px", opacity: 0.4 }}>
            <div style={{ fontSize: 28 }}>🔒</div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>{a.name}</div>
            <div style={{ fontSize: 11, color: "var(--hint)" }}>{a.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Проверить в браузере**

Вкладка Рейтинг: 3 таба (все/неделя/гильдии), медали для топ-3.
Вкладка Профиль: статистика, достижения сеткой 2×N.

- [ ] **Step 4: Commit**

```powershell
git add miniapp/src/pages/Leaderboard.jsx miniapp/src/pages/Profile.jsx
git commit -m "feat: Leaderboard and Profile pages"
```

---

## Task 12: Сборка и Cloudflare деплой

**Files:**
- Create: `cloudflared-start.bat`
- Modify: `miniapp/.env.production`

**Interfaces:**
- Produces: публичный HTTPS URL для API (cloudflared tunnel)
- Produces: Mini App URL на Cloudflare Pages
- Produces: бот отображает кнопку `🎮 Играть` → открывает Mini App

- [ ] **Step 1: Установить cloudflared**

Скачать `cloudflared-windows-amd64.exe` с https://github.com/cloudflare/cloudflared/releases/latest
Переименовать в `cloudflared.exe`, положить в `C:\Users\thisi\golos\`

- [ ] **Step 2: Авторизация Cloudflare**

```powershell
.\cloudflared.exe tunnel login
```

Откроется браузер — войти в Cloudflare аккаунт.

- [ ] **Step 3: Создать туннель**

```powershell
.\cloudflared.exe tunnel create golos-api
```

Запомнить UUID туннеля из вывода.

- [ ] **Step 4: Создать конфиг туннеля**

Создать файл `C:\Users\thisi\.cloudflared\config.yml`:
```yaml
tunnel: <UUID_ТУННЕЛЯ>
credentials-file: C:\Users\thisi\.cloudflared\<UUID_ТУННЕЛЯ>.json

ingress:
  - hostname: api.golos.pages.dev
    service: http://localhost:8000
  - service: http_status:404
```

**Примечание:** `api.golos.pages.dev` — это имя для будущего маршрута. После деплоя Pages нужно будет добавить CNAME в Cloudflare DNS.

- [ ] **Step 5: Для быстрого старта использовать quick tunnel (не требует домена)**

```powershell
.\cloudflared.exe tunnel --url http://localhost:8000
```

В выводе появится URL вида `https://xxxx-xxxx.trycloudflare.com`. Скопировать его.

- [ ] **Step 6: Создать `cloudflared-start.bat`**

```batch
@echo off
start "" "C:\Users\thisi\golos\cloudflared.exe" tunnel --url http://localhost:8000
echo Cloudflare tunnel started. Check console for URL.
pause
```

- [ ] **Step 7: Обновить `miniapp/.env.production`**

```
VITE_API_URL=https://xxxx-xxxx.trycloudflare.com
```

(Заменить на реальный URL из шага 5)

- [ ] **Step 8: Собрать React-приложение**

```powershell
cd miniapp; npm run build; cd ..
```

Собранный файлы окажутся в `miniapp/dist/`

- [ ] **Step 9: Установить Wrangler и задеплоить на Cloudflare Pages**

```powershell
npm install -g wrangler
cd miniapp; npx wrangler pages deploy dist --project-name golos-miniapp; cd ..
```

При первом запуске — авторизация в Cloudflare через браузер. После деплоя в выводе будет URL: `https://golos-miniapp.pages.dev`

- [ ] **Step 10: Добавить кнопку в боте**

Открыть BotFather в Telegram → `/newapp` → выбрать бота → ввести URL Mini App: `https://golos-miniapp.pages.dev`

Либо добавить Web App кнопку в главном меню бота. В `handlers/start.py` найти клавиатуру главного меню и добавить:

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# В функции главного меню добавить кнопку:
InlineKeyboardButton(
    text="🎮 Играть",
    web_app=WebAppInfo(url="https://golos-miniapp.pages.dev")
)
```

- [ ] **Step 11: Проверить сквозной сценарий**

1. Запустить бота: `python bot.py`
2. Запустить API: `python -m api.server`
3. Запустить туннель: `cloudflared-start.bat`
4. Открыть бота в Telegram → нажать «🎮 Играть»
5. Убедиться что Mini App открывается, профиль загружается, квест проходится

- [ ] **Step 12: Финальный commit**

```powershell
git add miniapp/.env.production cloudflared-start.bat miniapp/dist/ handlers/start.py
git commit -m "feat: Cloudflare deployment — tunnel, Pages, bot WebApp button"
```

---

## Self-Review

### Spec coverage

| Требование | Задача |
|---|---|
| Полная игра в Mini App | Task 7–11 |
| FastAPI + бот на одном DB | Task 1 (shared SQLite) |
| React + Vite | Task 7 |
| Cloudflare Tunnel + Pages | Task 12 |
| Аутентификация initData | Task 1 (auth.py) |
| Профиль, XP, стрик | Task 3, 8 |
| Карта локаций + квесты | Task 4, 9 |
| Биржа акций | Task 5, 10 |
| Лидерборд (3 таба) | Task 6, 11 |
| Ежедневные задания | Task 6, 8 |
| Достижения | Task 3, 11 |
| Пассивный доход (collect) | Task 4, 9 |
| DEV_USER_ID для локальной разработки | Task 1 |
| Тесты API | Tasks 1, 3, 4, 5, 6 |

### Gaps
- Гильдии (создание/вступление) — не реализованы в API. Только просмотр в лидерборде. Это сознательный MVP-скоп: создание гильдий можно добавить позже отдельным PR.
- Дуэли и кооп — оставлены в чат-боте, не перенесены в Mini App. Это отдельная задача Phase 2.
- Наставничество — только отображение в профиле.

### Type consistency
- `parse_level(total_xp)` → `(level, xp_in, xp_needed)` используется везде одинаково
- `get_stock_info(loc_id)` → `(price, change_pct)` — Task 2 называет `get_stock_info`, Task 5 тоже
- `get_current_user` — FastAPI dependency, импортируется из `api.server` во всех роутерах одинаково
- `_week_start()` дублируется в profile.py, map.py, leaderboard.py — это нормально (3 строки, не абстрагируем)
