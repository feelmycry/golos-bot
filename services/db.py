import json
import aiosqlite
from datetime import datetime, date
from config import DB_PATH


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
        for col in ("hint_charges INTEGER DEFAULT 0", "xp_boost_charges INTEGER DEFAULT 0"):
            try:
                await db.execute(f"ALTER TABLE game_players ADD COLUMN {col}")
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET is_complete = 1, completed_at = ?, final_feedback = ? WHERE id = ?",
            (datetime.now().isoformat(), final_feedback, session_id),
        )
        await db.commit()


async def get_admin_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Total users
        cur = await db.execute("SELECT COUNT(*) AS cnt FROM users")
        total_users = (await cur.fetchone())["cnt"]

        # Users list with session counts
        cur = await db.execute("""
            SELECT u.first_name, u.username, u.telegram_id, u.created_at,
                   u.is_blocked,
                   COUNT(s.id) AS sessions_total,
                   SUM(s.is_complete) AS sessions_done
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

        # Product stats
        cur = await db.execute("""
            SELECT product, COUNT(*) cnt, SUM(is_complete) done,
                   AVG(json_array_length(messages)) avg_msgs
            FROM sessions WHERE product IS NOT NULL
            GROUP BY product ORDER BY cnt DESC
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
            "SELECT COUNT(*) AS total, SUM(is_complete) AS completed FROM sessions WHERE user_id = ?",
            (user_id,),
        )
        totals = dict(await cur.fetchone())

        cur = await db.execute(
            """SELECT cohort, COUNT(*) AS total, SUM(is_complete) AS completed
               FROM sessions WHERE user_id = ?
               GROUP BY cohort""",
            (user_id,),
        )
        by_cohort = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            """SELECT stage, COUNT(*) AS total
               FROM sessions WHERE user_id = ?
               GROUP BY stage""",
            (user_id,),
        )
        by_stage = [dict(r) for r in await cur.fetchall()]

    return {
        "total": totals.get("total") or 0,
        "completed": totals.get("completed") or 0,
        "by_cohort": by_cohort,
        "by_stage": by_stage,
    }


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
            "SELECT user_id, xp, coins, streak_days, last_active, hint_charges, xp_boost_charges FROM game_players WHERE user_id = ?",
            (user_id,),
        )
        return dict(await cur.fetchone())


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
