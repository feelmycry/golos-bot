from datetime import date, timedelta
import aiosqlite
from config import DB_PATH

PLANS = {
    "half_year": {"days": 180, "price": 1390, "label": "6 месяцев"},
    "year":      {"days": 365, "price": 1790, "label": "12 месяцев"},
}


async def is_subscribed(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT paid_until FROM subscriptions WHERE user_id = ?", (user_id,)
        )).fetchone()
        if not row:
            return False
        return date.fromisoformat(row["paid_until"]) >= date.today()


async def get_subscription_info(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT plan, paid_until FROM subscriptions WHERE user_id = ?", (user_id,)
        )).fetchone()
        if not row:
            return None
        return {"plan": row["plan"], "paid_until": row["paid_until"]}


async def grant_subscription(user_id: int, plan: str, payment_id: str | None = None) -> date:
    plan_days = PLANS.get(plan, {}).get("days", 90)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT paid_until FROM subscriptions WHERE user_id = ?", (user_id,)
        )).fetchone()
        today = date.today()
        if row and date.fromisoformat(row["paid_until"]) > today:
            paid_until = date.fromisoformat(row["paid_until"]) + timedelta(days=plan_days)
        else:
            paid_until = today + timedelta(days=plan_days)
        await db.execute("""
            INSERT INTO subscriptions (user_id, plan, paid_until, payment_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan=excluded.plan,
                paid_until=excluded.paid_until,
                payment_id=excluded.payment_id
        """, (user_id, plan, paid_until.isoformat(), payment_id))
        await db.commit()
    return paid_until
