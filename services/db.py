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
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
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
