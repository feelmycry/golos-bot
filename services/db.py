import json
import aiosqlite
from datetime import datetime
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
