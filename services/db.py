import asyncio
import json
import re
import aiosqlite
from datetime import datetime, date
from config import DB_PATH

# Per-resource locks to prevent race conditions in concurrent answer handling
_duel_locks: dict[int, asyncio.Lock] = {}
_coop_locks: dict[int, asyncio.Lock] = {}


def _get_lock(lock_dict: dict, key: int) -> asyncio.Lock:
    if key not in lock_dict:
        lock_dict[key] = asyncio.Lock()
    return lock_dict[key]


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                is_blocked  INTEGER DEFAULT 0
            )
        """)
        # Migrate existing DB: add is_blocked if column missing
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        except Exception:
            pass  # Column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                started_at     TEXT    DEFAULT CURRENT_TIMESTAMP,
                completed_at   TEXT,
                scenario       TEXT,
                mode           TEXT,
                stage          TEXT,
                product        TEXT,
                cohort         TEXT,
                client_profile TEXT,
                messages       TEXT    DEFAULT '[]',
                final_feedback TEXT,
                is_complete    INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS learning_progress (
                user_id      INTEGER NOT NULL,
                lesson_id    TEXT    NOT NULL,
                completed    INTEGER DEFAULT 0,
                quiz_passed  INTEGER DEFAULT 0,
                quiz_score   INTEGER DEFAULT 0,
                completed_at TEXT,
                PRIMARY KEY (user_id, lesson_id)
            )
        """)
        # ── Game tables ───────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_players (
                user_id     INTEGER PRIMARY KEY,
                level       INTEGER DEFAULT 1,
                xp          INTEGER DEFAULT 0,
                coins       INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                last_active TEXT,
                onboarded   INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_location_progress (
                user_id       INTEGER NOT NULL,
                location_id   TEXT    NOT NULL,
                reputation    INTEGER DEFAULT 0,
                shares        INTEGER DEFAULT 0,
                last_collected TEXT,
                PRIMARY KEY (user_id, location_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_quest_log (
                user_id      INTEGER NOT NULL,
                quest_id     TEXT    NOT NULL,
                location_id  TEXT    NOT NULL,
                completed_at TEXT,
                PRIMARY KEY (user_id, quest_id)
            )
        """)
        try:
            await db.execute("ALTER TABLE sessions ADD COLUMN score REAL")
        except Exception:
            pass
        for col in (
            "hint_charges INTEGER DEFAULT 0",
            "xp_boost_charges INTEGER DEFAULT 0",
            "onboarded INTEGER DEFAULT 0",
            "streak_reminded_date TEXT",
        ):
            try:
                await db.execute(f"ALTER TABLE game_players ADD COLUMN {col}")
            except Exception:
                pass
        # Mark existing active players as already onboarded so they skip the intro
        await db.execute(
            "UPDATE game_players SET onboarded = 1 "
            "WHERE onboarded = 0 AND (xp > 0 OR coins > 0 OR last_active IS NOT NULL)"
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_daily_progress (
                user_id   INTEGER NOT NULL,
                date      TEXT    NOT NULL,
                task_id   TEXT    NOT NULL,
                progress  INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                claimed   INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date, task_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_achievements (
                user_id        INTEGER NOT NULL,
                achievement_id TEXT    NOT NULL,
                earned_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_weekly_xp (
                user_id    INTEGER NOT NULL,
                week_start TEXT    NOT NULL,
                xp_gained  INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, week_start)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_scenario_log (
                user_id     INTEGER NOT NULL,
                scenario_id TEXT    NOT NULL,
                played_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, scenario_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_guilds (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                emoji      TEXT    DEFAULT '🏰',
                created_by INTEGER NOT NULL,
                created_at TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_guild_members (
                user_id   INTEGER PRIMARY KEY,
                guild_id  INTEGER NOT NULL,
                joined_at TEXT    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)  REFERENCES game_players(user_id),
                FOREIGN KEY (guild_id) REFERENCES game_guilds(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_duels (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id    INTEGER NOT NULL,
                opponent_id      INTEGER,
                questions_json   TEXT    NOT NULL,
                challenger_score INTEGER DEFAULT -1,
                opponent_score   INTEGER DEFAULT -1,
                status           TEXT    DEFAULT 'pending',
                created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_mentors (
                mentor_id  INTEGER NOT NULL,
                mentee_id  INTEGER PRIMARY KEY,
                created_at TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    INTEGER PRIMARY KEY,
                plan       TEXT    NOT NULL,
                paid_until TEXT    NOT NULL,
                payment_id TEXT,
                created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS product_access (
                user_id    INTEGER NOT NULL,
                product    TEXT    NOT NULL,
                plan       TEXT    NOT NULL,
                paid_until TEXT    NOT NULL,
                payment_id TEXT,
                created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, product)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_coop_sessions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                initiator_id       INTEGER NOT NULL,
                partner_id         INTEGER,
                quest_id           TEXT    NOT NULL,
                location_id        TEXT    NOT NULL,
                quest_json         TEXT    NOT NULL,
                initiator_correct  INTEGER DEFAULT -1,
                partner_correct    INTEGER DEFAULT -1,
                status             TEXT    DEFAULT 'pending',
                created_at         TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id              INTEGER NOT NULL,
                referred_id              INTEGER NOT NULL UNIQUE,
                discount_used            INTEGER DEFAULT 0,
                discount_product         TEXT,
                referrer_discount_used   INTEGER DEFAULT 0,
                referrer_discount_product TEXT,
                created_at               TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for col in (
            "referrer_discount_used INTEGER DEFAULT 0",
            "referrer_discount_product TEXT",
        ):
            try:
                await db.execute(f"ALTER TABLE referrals ADD COLUMN {col}")
            except Exception:
                pass
        await db.commit()


async def upsert_user(telegram_id: int, username: str | None, first_name: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        await db.commit()


async def create_session(
    user_id: int,
    scenario: str,
    mode: str,
    stage: str,
    product: str | None,
    cohort: str,
    client_profile: dict,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO sessions (user_id, scenario, mode, stage, product, cohort, client_profile)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, scenario, mode, stage, product, cohort, json.dumps(client_profile, ensure_ascii=False)),
        )
        await db.commit()
        return cursor.lastrowid


async def update_messages(session_id: int, messages: list) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET messages = ? WHERE id = ?",
            (json.dumps(messages, ensure_ascii=False), session_id),
        )
        await db.commit()


async def complete_session(session_id: int, final_feedback: str) -> None:
    m = re.search(r'Оценка[:\s]+(\d+(?:[.,]\d+)?)\s*/\s*10', final_feedback)
    score = float(m.group(1).replace(',', '.')) if m else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET is_complete = 1, completed_at = ?, final_feedback = ?, score = ? WHERE id = ?",
            (datetime.now().isoformat(), final_feedback, score, session_id),
        )
        await db.commit()


async def get_user_by_username(username: str) -> dict | None:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT telegram_id, username, first_name FROM users WHERE LOWER(username) = LOWER(?)",
            (username,)
        )).fetchone()
        if not row:
            return None
        return {"telegram_id": row["telegram_id"], "username": row["username"], "first_name": row["first_name"]}


async def get_admin_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Total users
        cur = await db.execute("SELECT COUNT(*) AS cnt FROM users")
        total_users = (await cur.fetchone())["cnt"]

        # Users list with session counts and avg score
        cur = await db.execute("""
            SELECT u.first_name, u.username, u.telegram_id, u.created_at,
                   u.is_blocked,
                   COUNT(s.id) AS sessions_total,
                   SUM(s.is_complete) AS sessions_done,
                   ROUND(AVG(CASE WHEN s.is_complete=1 AND s.score IS NOT NULL THEN s.score END), 1) AS avg_score
            FROM users u
            LEFT JOIN sessions s ON s.user_id = u.telegram_id
            GROUP BY u.telegram_id
            ORDER BY sessions_total DESC
        """)
        users = [dict(r) for r in await cur.fetchall()]

        # Session totals
        cur = await db.execute(
            "SELECT COUNT(*) total, SUM(is_complete) done FROM sessions"
        )
        sess_totals = dict(await cur.fetchone())

        # Avg duration of completed sessions (in minutes)
        cur = await db.execute("""
            SELECT AVG((julianday(completed_at) - julianday(started_at)) * 1440) AS avg_min
            FROM sessions WHERE is_complete = 1 AND completed_at IS NOT NULL
        """)
        avg_dur = (await cur.fetchone())["avg_min"]

        # Stage stats: sessions count, completion, avg messages
        cur = await db.execute("""
            SELECT stage,
                   COUNT(*) cnt,
                   SUM(is_complete) done,
                   AVG(json_array_length(messages)) avg_msgs,
                   AVG(CASE WHEN completed_at IS NOT NULL
                       THEN (julianday(completed_at) - julianday(started_at)) * 1440
                       ELSE NULL END) avg_min
            FROM sessions
            GROUP BY stage
            ORDER BY cnt DESC
        """)
        by_stage = [dict(r) for r in await cur.fetchall()]

        # Product stats with avg score
        cur = await db.execute("""
            SELECT product, COUNT(*) cnt, SUM(is_complete) done,
                   ROUND(AVG(json_array_length(messages)), 1) avg_msgs,
                   ROUND(AVG(CASE WHEN is_complete=1 AND score IS NOT NULL THEN score END), 1) avg_score
            FROM sessions WHERE product IS NOT NULL
            GROUP BY product ORDER BY avg_score ASC
        """)
        by_product = [dict(r) for r in await cur.fetchall()]

        # Cohort stats
        cur = await db.execute("""
            SELECT cohort, COUNT(*) cnt, SUM(is_complete) done
            FROM sessions WHERE cohort IS NOT NULL
            GROUP BY cohort ORDER BY cnt DESC
        """)
        by_cohort = [dict(r) for r in await cur.fetchall()]

        # Last 50 sessions
        cur = await db.execute("""
            SELECT u.first_name, s.stage, s.product, s.cohort,
                   s.started_at, s.completed_at, s.is_complete,
                   json_array_length(s.messages) AS msg_count
            FROM sessions s JOIN users u ON s.user_id = u.telegram_id
            ORDER BY s.started_at DESC LIMIT 50
        """)
        recent = [dict(r) for r in await cur.fetchall()]

    return {
        "total_users": total_users,
        "users": users,
        "sess_total": sess_totals.get("total") or 0,
        "sess_done": sess_totals.get("done") or 0,
        "avg_duration_min": round(avg_dur, 1) if avg_dur else None,
        "by_stage": by_stage,
        "by_product": by_product,
        "by_cohort": by_cohort,
        "recent": recent,
    }


async def get_all_sessions_export() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT u.telegram_id, u.first_name, u.username, u.created_at AS registered_at,
                   s.id AS session_id, s.started_at, s.completed_at, s.is_complete,
                   s.stage, s.product, s.cohort, s.mode, s.scenario,
                   json_array_length(s.messages) AS msg_count,
                   CASE WHEN s.completed_at IS NOT NULL
                        THEN ROUND((julianday(s.completed_at) - julianday(s.started_at)) * 1440, 1)
                        ELSE NULL END AS duration_min
            FROM sessions s
            JOIN users u ON s.user_id = u.telegram_id
            ORDER BY s.started_at DESC
        """)
        return [dict(r) for r in await cur.fetchall()]


async def get_user_sessions(telegram_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT u.first_name, u.username, u.created_at,
                   s.id, s.stage, s.product, s.cohort,
                   s.started_at, s.completed_at, s.is_complete,
                   json_array_length(s.messages) AS msg_count,
                   CASE WHEN s.completed_at IS NOT NULL
                        THEN (julianday(s.completed_at) - julianday(s.started_at)) * 1440
                        ELSE NULL END AS duration_min
            FROM sessions s
            JOIN users u ON s.user_id = u.telegram_id
            WHERE u.telegram_id = ?
            ORDER BY s.started_at DESC
        """, (telegram_id,))
        return [dict(r) for r in await cur.fetchall()]


async def is_user_blocked(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT is_blocked FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0])


async def set_user_blocked(telegram_id: int, blocked: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_blocked = ? WHERE telegram_id = ?",
            (1 if blocked else 0, telegram_id),
        )
        await db.commit()


async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            """SELECT COUNT(*) AS total, SUM(is_complete) AS completed,
                      ROUND(AVG(CASE WHEN is_complete=1 AND score IS NOT NULL THEN score END), 1) AS avg_score
               FROM sessions WHERE user_id = ?""",
            (user_id,),
        )
        totals = dict(await cur.fetchone())

        cur = await db.execute(
            """SELECT product, COUNT(*) AS total, SUM(is_complete) AS completed,
                      ROUND(AVG(CASE WHEN is_complete=1 AND score IS NOT NULL THEN score END), 1) AS avg_score
               FROM sessions WHERE user_id = ? AND product IS NOT NULL
               GROUP BY product ORDER BY total DESC""",
            (user_id,),
        )
        by_product = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            """SELECT stage, COUNT(*) AS total, SUM(is_complete) AS completed
               FROM sessions WHERE user_id = ?
               GROUP BY stage ORDER BY total DESC""",
            (user_id,),
        )
        by_stage = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            """SELECT id, stage, product, mode, score, completed_at,
                      SUBSTR(final_feedback, 1, 120) AS feedback_preview
               FROM sessions WHERE user_id = ? AND is_complete = 1
               ORDER BY completed_at DESC LIMIT 10""",
            (user_id,),
        )
        recent_sessions = [dict(r) for r in await cur.fetchall()]

    return {
        "total": totals.get("total") or 0,
        "completed": totals.get("completed") or 0,
        "avg_score": totals.get("avg_score"),
        "by_product": by_product,
        "by_stage": by_stage,
        "recent_sessions": recent_sessions,
    }


async def get_user_session_detail(session_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, stage, product, mode, score, completed_at, final_feedback
               FROM sessions WHERE id = ? AND user_id = ? AND is_complete = 1""",
            (session_id, user_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ── Learning progress ─────────────────────────────────────────────────────────

async def get_learning_progress(user_id: int) -> dict[str, dict]:
    """Returns {lesson_id: {completed, quiz_passed, quiz_score}} for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT lesson_id, completed, quiz_passed, quiz_score FROM learning_progress WHERE user_id = ?",
            (user_id,),
        )
        return {r["lesson_id"]: dict(r) for r in await cur.fetchall()}


async def mark_lesson_read(user_id: int, lesson_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO learning_progress (user_id, lesson_id, completed, completed_at)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, lesson_id) DO UPDATE SET completed=1, completed_at=excluded.completed_at""",
            (user_id, lesson_id, datetime.now().isoformat()),
        )
        await db.commit()


async def save_quiz_result(user_id: int, lesson_id: str, score: int, total: int) -> None:
    passed = 1 if score >= (total + 1) // 2 else 0  # >=50% to pass
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO learning_progress (user_id, lesson_id, completed, quiz_passed, quiz_score, completed_at)
               VALUES (?, ?, 1, ?, ?, ?)
               ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                 completed=1, quiz_passed=excluded.quiz_passed,
                 quiz_score=excluded.quiz_score, completed_at=excluded.completed_at""",
            (user_id, lesson_id, passed, score, datetime.now().isoformat()),
        )
        await db.commit()


# ── Game functions ────────────────────────────────────────────────────────────

async def game_get_or_create_player(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO game_players (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT user_id, xp, coins, streak_days, last_active, hint_charges, xp_boost_charges, onboarded FROM game_players WHERE user_id = ?",
            (user_id,),
        )
        return dict(await cur.fetchone())


async def game_set_onboarded(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE game_players SET onboarded = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def game_update_streak(user_id: int) -> int:
    """Update streak counter. Returns new streak value."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT streak_days, last_active FROM game_players WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return 0

        last_active = row["last_active"]
        streak = row["streak_days"]

        if last_active == today:
            return streak  # Already updated today

        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last_active == yesterday:
            streak += 1
        else:
            streak = 1

        await db.execute(
            "UPDATE game_players SET streak_days = ?, last_active = ? WHERE user_id = ?",
            (streak, today, user_id),
        )
        await db.commit()
        return streak


async def game_get_location_progress(user_id: int) -> dict[str, dict]:
    """Returns {location_id: {reputation, shares, last_collected}}."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT location_id, reputation, shares, last_collected FROM game_location_progress WHERE user_id = ?",
            (user_id,),
        )
        return {r["location_id"]: dict(r) for r in await cur.fetchall()}


async def game_get_completed_quests(user_id: int) -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT quest_id FROM game_quest_log WHERE user_id = ?",
            (user_id,),
        )
        return {r[0] for r in await cur.fetchall()}


async def game_save_quest_result(
    user_id: int,
    quest_id: str,
    location_id: str,
    xp: int,
    coins: int,
    rep: int,
) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        # Log the quest
        await db.execute(
            """INSERT OR REPLACE INTO game_quest_log (user_id, quest_id, location_id, completed_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, quest_id, location_id, now),
        )
        # Update player XP and coins
        if xp > 0 or coins > 0:
            await db.execute(
                "UPDATE game_players SET xp = xp + ?, coins = coins + ? WHERE user_id = ?",
                (xp, coins, user_id),
            )
        # Update location reputation and shares (1 share per quest completed with correct answer)
        if rep > 0:
            await db.execute(
                """INSERT INTO game_location_progress (user_id, location_id, reputation, shares, last_collected)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(user_id, location_id) DO UPDATE SET
                     reputation = reputation + ?,
                     shares = shares + 1""",
                (user_id, location_id, rep, now, rep),
            )
        await db.commit()


async def game_update_player(user_id: int, xp: int = 0, coins: int = 0) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE game_players SET xp = xp + ?, coins = coins + ? WHERE user_id = ?",
            (xp, coins, user_id),
        )
        await db.commit()


async def game_apply_legendary_penalty(user_id: int, xp_penalty: int, coins_penalty: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE game_players SET xp = MAX(0, xp - ?), coins = MAX(0, coins - ?) WHERE user_id = ?",
            (xp_penalty, coins_penalty, user_id),
        )
        await db.commit()


async def game_collect_income(user_id: int, location_id: str, amount: int) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE game_players SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.execute(
            "UPDATE game_location_progress SET last_collected = ? WHERE user_id = ? AND location_id = ?",
            (now, user_id, location_id),
        )
        await db.commit()


async def game_spend_coins(user_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT coins FROM game_players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute("UPDATE game_players SET coins = coins - ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        return True


async def game_buy_shares(user_id: int, location_id: str, qty: int, cost: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT coins FROM game_players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < cost:
            return False
        now = datetime.utcnow().isoformat()
        await db.execute("UPDATE game_players SET coins = coins - ? WHERE user_id = ?", (cost, user_id))
        await db.execute(
            """INSERT INTO game_location_progress (user_id, location_id, reputation, shares, last_collected)
               VALUES (?, ?, 0, ?, ?)
               ON CONFLICT(user_id, location_id) DO UPDATE SET shares = shares + ?""",
            (user_id, location_id, qty, now, qty),
        )
        await db.commit()
        return True


async def game_sell_shares(user_id: int, location_id: str, qty: int, gain: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT shares FROM game_location_progress WHERE user_id = ? AND location_id = ?",
            (user_id, location_id),
        )
        row = await cur.fetchone()
        if not row or row[0] < qty:
            return False
        await db.execute("UPDATE game_players SET coins = coins + ? WHERE user_id = ?", (gain, user_id))
        await db.execute(
            "UPDATE game_location_progress SET shares = shares - ? WHERE user_id = ? AND location_id = ?",
            (qty, user_id, location_id),
        )
        await db.commit()
        return True


async def game_use_hint(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT hint_charges FROM game_players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < 1:
            return False
        await db.execute(
            "UPDATE game_players SET hint_charges = hint_charges - 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        return True


async def game_use_xp_boost(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT xp_boost_charges FROM game_players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < 1:
            return False
        await db.execute(
            "UPDATE game_players SET xp_boost_charges = xp_boost_charges - 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()
        return True


async def game_update_daily_task(
    user_id: int, date_str: str, task_id: str, amount: int, target: int
) -> tuple[int, bool]:
    """Increment task progress. Returns (new_progress, is_completed)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT progress, completed FROM game_daily_progress WHERE user_id=? AND date=? AND task_id=?",
            (user_id, date_str, task_id),
        )
        row = await cur.fetchone()
        if row and row["completed"]:
            return target, True
        current = row["progress"] if row else 0
        new_progress = min(current + amount, target)
        completed = 1 if new_progress >= target else 0
        await db.execute(
            """INSERT INTO game_daily_progress (user_id, date, task_id, progress, completed)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, date, task_id) DO UPDATE SET
                 progress = excluded.progress, completed = excluded.completed""",
            (user_id, date_str, task_id, new_progress, completed),
        )
        await db.commit()
        return new_progress, bool(completed)


async def game_get_daily_progress(user_id: int, date_str: str) -> dict[str, dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT task_id, progress, completed, claimed FROM game_daily_progress WHERE user_id=? AND date=?",
            (user_id, date_str),
        )
        return {r["task_id"]: dict(r) for r in await cur.fetchall()}


async def game_claim_daily_reward(user_id: int, date_str: str, task_id: str, xp: int, coins: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT completed, claimed FROM game_daily_progress WHERE user_id=? AND date=? AND task_id=?",
            (user_id, date_str, task_id),
        )
        row = await cur.fetchone()
        if not row or not row["completed"] or row["claimed"]:
            return False
        await db.execute(
            "UPDATE game_daily_progress SET claimed=1 WHERE user_id=? AND date=? AND task_id=?",
            (user_id, date_str, task_id),
        )
        await db.execute(
            "UPDATE game_players SET xp=xp+?, coins=coins+? WHERE user_id=?",
            (xp, coins, user_id),
        )
        await db.commit()
        return True


async def game_get_leaderboard(limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT u.first_name, p.user_id, p.xp,
                      COUNT(DISTINCT q.quest_id) AS quests_done
               FROM game_players p
               JOIN users u ON p.user_id = u.telegram_id
               LEFT JOIN game_quest_log q ON q.user_id = p.user_id
               WHERE p.xp > 0
               GROUP BY p.user_id
               ORDER BY p.xp DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def game_get_player_rank(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM game_players WHERE xp > (SELECT COALESCE(xp,0) FROM game_players WHERE user_id=?)",
            (user_id,),
        )
        row = await cur.fetchone()
        return (row[0] + 1) if row else 1


async def game_add_shop_item(user_id: int, item: str, cost: int) -> bool:
    col = {"hint": "hint_charges", "xp_boost": "xp_boost_charges"}.get(item)
    if not col:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT coins FROM game_players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < cost:
            return False
        await db.execute(
            f"UPDATE game_players SET coins = coins - ?, {col} = {col} + 1 WHERE user_id = ?",
            (cost, user_id),
        )
        await db.commit()
        return True


# ── Achievements ──────────────────────────────────────────────────────────────

async def game_get_achievements(user_id: int) -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT achievement_id FROM game_achievements WHERE user_id = ?", (user_id,)
        )
        return {row[0] for row in await cur.fetchall()}


async def game_grant_achievement(user_id: int, achievement_id: str) -> bool:
    """Returns True if this is a NEW achievement (not already earned)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM game_achievements WHERE user_id = ? AND achievement_id = ?",
            (user_id, achievement_id),
        )
        if await cur.fetchone():
            return False
        await db.execute(
            "INSERT INTO game_achievements (user_id, achievement_id) VALUES (?, ?)",
            (user_id, achievement_id),
        )
        await db.commit()
        return True


# ── Weekly XP ─────────────────────────────────────────────────────────────────

async def game_add_weekly_xp(user_id: int, week_start: str, amount: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO game_weekly_xp (user_id, week_start, xp_gained) VALUES (?, ?, ?)
               ON CONFLICT(user_id, week_start) DO UPDATE SET xp_gained = xp_gained + excluded.xp_gained""",
            (user_id, week_start, amount),
        )
        await db.commit()


async def game_get_weekly_leaderboard(week_start: str, limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT u.first_name, w.user_id, w.xp_gained,
                      COUNT(DISTINCT q.quest_id) AS quests_done
               FROM game_weekly_xp w
               JOIN users u ON w.user_id = u.telegram_id
               LEFT JOIN game_quest_log q ON q.user_id = w.user_id
               WHERE w.week_start = ? AND w.xp_gained > 0
               GROUP BY w.user_id
               ORDER BY w.xp_gained DESC
               LIMIT ?""",
            (week_start, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def game_get_weekly_rank(user_id: int, week_start: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM game_weekly_xp
               WHERE week_start = ? AND xp_gained > (
                   SELECT COALESCE(xp_gained, 0) FROM game_weekly_xp
                   WHERE user_id = ? AND week_start = ?
               )""",
            (week_start, user_id, week_start),
        )
        row = await cur.fetchone()
        return (row[0] + 1) if row else 1


async def game_get_my_weekly_xp(user_id: int, week_start: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT xp_gained FROM game_weekly_xp WHERE user_id = ? AND week_start = ?",
            (user_id, week_start),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ── Scenarios ─────────────────────────────────────────────────────────────────

async def game_get_completed_scenarios(user_id: int) -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT scenario_id FROM game_scenario_log WHERE user_id = ?", (user_id,)
        )
        return {row[0] for row in await cur.fetchall()}


async def game_save_scenario_result(user_id: int, scenario_id: str, coins: int, xp: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO game_scenario_log (user_id, scenario_id) VALUES (?, ?)",
            (user_id, scenario_id),
        )
        await db.execute(
            "UPDATE game_players SET coins = coins + ?, xp = xp + ? WHERE user_id = ?",
            (coins, xp, user_id),
        )
        await db.commit()


# ── Guild functions ───────────────────────────────────────────────────────────

async def game_create_guild(creator_id: int, name: str, emoji: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO game_guilds (name, emoji, created_by) VALUES (?, ?, ?)",
            (name, emoji, creator_id),
        )
        guild_id = cur.lastrowid
        await db.execute(
            "INSERT OR REPLACE INTO game_guild_members (user_id, guild_id) VALUES (?, ?)",
            (creator_id, guild_id),
        )
        await db.commit()
        return guild_id


async def game_join_guild(user_id: int, guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM game_guilds WHERE id = ?", (guild_id,))
        if not await cur.fetchone():
            return False
        await db.execute(
            "INSERT OR REPLACE INTO game_guild_members (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )
        await db.commit()
        return True


async def game_get_my_guild(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT g.id, g.name, g.emoji, g.created_by,
                      COUNT(gm.user_id) AS members,
                      COALESCE(SUM(gp.xp), 0) AS total_xp
               FROM game_guild_members me
               JOIN game_guilds g ON g.id = me.guild_id
               LEFT JOIN game_guild_members gm ON gm.guild_id = g.id
               LEFT JOIN game_players gp ON gp.user_id = gm.user_id
               WHERE me.user_id = ?
               GROUP BY g.id""",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def game_leave_guild(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM game_guild_members WHERE user_id = ?", (user_id,))
        await db.commit()


async def game_get_guild_leaderboard() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT g.id, g.name, g.emoji,
                      COUNT(gm.user_id) AS members,
                      COALESCE(SUM(gp.xp), 0) AS total_xp
               FROM game_guilds g
               LEFT JOIN game_guild_members gm ON gm.guild_id = g.id
               LEFT JOIN game_players gp ON gp.user_id = gm.user_id
               GROUP BY g.id
               ORDER BY total_xp DESC
               LIMIT 10"""
        )
        return [dict(r) for r in await cur.fetchall()]


async def game_get_guild_members(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT u.first_name, gp.xp, gp.coins, gm.joined_at
               FROM game_guild_members gm
               JOIN game_players gp ON gp.user_id = gm.user_id
               JOIN users u ON u.telegram_id = gm.user_id
               WHERE gm.guild_id = ?
               ORDER BY gp.xp DESC
               LIMIT 20""",
            (guild_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


# ── Streak notification helpers ───────────────────────────────────────────────

async def game_get_streak_reminder_users() -> list[dict]:
    """Users with streak > 0 who haven't been active for 20-23 hours and haven't been reminded today."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT user_id, streak_days, last_active FROM game_players
               WHERE streak_days > 0 AND last_active IS NOT NULL
               AND CAST((julianday('now') - julianday(last_active)) * 24 AS INTEGER) BETWEEN 20 AND 23
               AND (streak_reminded_date IS NULL OR streak_reminded_date != date('now'))"""
        )
        return [dict(r) for r in await cur.fetchall()]


async def game_mark_streak_reminded(user_id: int) -> None:
    """Record that a streak reminder was sent today so it won't be sent again."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE game_players SET streak_reminded_date = date('now') WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


# ── Duel functions ────────────────────────────────────────────────────────────

async def game_create_duel(challenger_id: int, questions_json: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO game_duels (challenger_id, questions_json) VALUES (?, ?)",
            (challenger_id, questions_json),
        )
        await db.commit()
        return cur.lastrowid


async def game_get_duel(duel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM game_duels WHERE id = ?", (duel_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def game_join_duel(duel_id: int, opponent_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT challenger_id, status FROM game_duels WHERE id = ?", (duel_id,)
        )
        row = await cur.fetchone()
        if not row or row[0] == opponent_id or row[1] != "pending":
            return False
        await db.execute(
            "UPDATE game_duels SET opponent_id = ?, status = 'in_progress' WHERE id = ?",
            (opponent_id, duel_id),
        )
        await db.commit()
        return True


async def game_save_duel_result(duel_id: int, user_id: int, score: int) -> dict:
    async with _get_lock(_duel_locks, duel_id):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM game_duels WHERE id = ?", (duel_id,))
            row = await cur.fetchone()
            if row is None:
                return {"challenger_done": False, "opponent_done": False, "duel": {}}
            duel = dict(row)
            if user_id == duel["challenger_id"]:
                await db.execute(
                    "UPDATE game_duels SET challenger_score = ? WHERE id = ?", (score, duel_id)
                )
                duel["challenger_score"] = score
            else:
                await db.execute(
                    "UPDATE game_duels SET opponent_score = ? WHERE id = ?", (score, duel_id)
                )
                duel["opponent_score"] = score
            challenger_done = duel["challenger_score"] >= 0
            opponent_done = duel["opponent_score"] >= 0
            if challenger_done and opponent_done:
                await db.execute(
                    "UPDATE game_duels SET status = 'completed' WHERE id = ?", (duel_id,)
                )
            await db.commit()
            return {"challenger_done": challenger_done, "opponent_done": opponent_done, "duel": duel}


async def game_get_duel_by_challenger(challenger_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM game_duels WHERE challenger_id = ? AND status != 'completed' ORDER BY created_at DESC LIMIT 1",
            (challenger_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ── Mentor functions ──────────────────────────────────────────────────────────

async def game_link_mentor(mentor_id: int, mentee_id: int) -> bool:
    if mentor_id == mentee_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT mentee_id FROM game_mentors WHERE mentee_id = ?", (mentee_id,))
        if await cur.fetchone():
            return False  # already has mentor
        await db.execute(
            "INSERT INTO game_mentors (mentor_id, mentee_id) VALUES (?, ?)",
            (mentor_id, mentee_id),
        )
        await db.commit()
        return True


async def game_get_mentor(mentee_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT mentor_id FROM game_mentors WHERE mentee_id = ?", (mentee_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def game_get_mentees(mentor_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT u.first_name, gp.xp, gm.created_at
               FROM game_mentors gm
               JOIN users u ON u.telegram_id = gm.mentee_id
               JOIN game_players gp ON gp.user_id = gm.mentee_id
               WHERE gm.mentor_id = ?
               ORDER BY gp.xp DESC""",
            (mentor_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def game_add_mentor_bonus(mentor_id: int, xp: int) -> None:
    bonus = max(1, xp // 10)  # 10% of mentee's XP gain
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE game_players SET xp = xp + ?, coins = coins + ? WHERE user_id = ?",
            (bonus, bonus // 2, mentor_id),
        )
        await db.commit()


# ── Co-op functions ───────────────────────────────────────────────────────────

async def game_create_coop(initiator_id: int, quest_id: str, location_id: str, quest_json: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO game_coop_sessions
               (initiator_id, quest_id, location_id, quest_json) VALUES (?, ?, ?, ?)""",
            (initiator_id, quest_id, location_id, quest_json),
        )
        await db.commit()
        return cur.lastrowid


async def game_join_coop(session_id: int, partner_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT initiator_id, status FROM game_coop_sessions WHERE id = ?", (session_id,)
        )
        row = await cur.fetchone()
        if not row or row[0] == partner_id or row[1] != "pending":
            return False
        await db.execute(
            "UPDATE game_coop_sessions SET partner_id = ?, status = 'in_progress' WHERE id = ?",
            (partner_id, session_id),
        )
        await db.commit()
        return True


async def game_get_coop(session_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM game_coop_sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def game_save_coop_answer(session_id: int, user_id: int, correct: bool) -> dict:
    val = 1 if correct else 0
    async with _get_lock(_coop_locks, session_id):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM game_coop_sessions WHERE id = ?", (session_id,))
            sess = dict(await cur.fetchone())
            if user_id == sess["initiator_id"]:
                await db.execute(
                    "UPDATE game_coop_sessions SET initiator_correct = ? WHERE id = ?", (val, session_id)
                )
                sess["initiator_correct"] = val
            else:
                await db.execute(
                    "UPDATE game_coop_sessions SET partner_correct = ? WHERE id = ?", (val, session_id)
                )
                sess["partner_correct"] = val
            both_done = sess["initiator_correct"] >= 0 and sess["partner_correct"] >= 0
            if both_done:
                await db.execute(
                    "UPDATE game_coop_sessions SET status = 'completed' WHERE id = ?", (session_id,)
                )
            await db.commit()
            return {"both_done": both_done, "session": sess}
