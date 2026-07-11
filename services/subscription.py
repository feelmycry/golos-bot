from datetime import date, timedelta
import aiosqlite
from config import DB_PATH

PLANS = {
    "half_year": {"days": 180, "price": 1390, "label": "6 месяцев"},
    "year":      {"days": 365, "price": 1790, "label": "12 месяцев"},
}

PRODUCT_PLANS = {
    "learning_basic":  {"days": 36500, "price": 200,  "label": "Базовый уровень (навсегда)"},
    "learning_medium": {"days": 36500, "price": 200,  "label": "Средний уровень (навсегда)"},
    "learning_pro":    {"days": 36500, "price": 300,  "label": "Профессиональный уровень (навсегда)"},
    "stocks_monthly":  {"days": 30,    "price": 1400, "label": "Анализ акций — 1 месяц"},
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


async def is_product_subscribed(user_id: int, product: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT paid_until FROM product_access WHERE user_id = ? AND product = ?",
            (user_id, product)
        )).fetchone()
        if not row:
            return False
        return date.fromisoformat(row["paid_until"]) >= date.today()


async def grant_product_access(user_id: int, product: str, plan: str, payment_id: str | None = None) -> date:
    plan_days = PRODUCT_PLANS.get(plan, {}).get("days", 30)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT paid_until FROM product_access WHERE user_id = ? AND product = ?",
            (user_id, product)
        )).fetchone()
        today = date.today()
        if row and date.fromisoformat(row["paid_until"]) > today:
            paid_until = date.fromisoformat(row["paid_until"]) + timedelta(days=plan_days)
        else:
            paid_until = today + timedelta(days=plan_days)
        await db.execute("""
            INSERT INTO product_access (user_id, product, plan, paid_until, payment_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, product) DO UPDATE SET
                plan=excluded.plan, paid_until=excluded.paid_until, payment_id=excluded.payment_id
        """, (user_id, product, plan, paid_until.isoformat(), payment_id))
        await db.commit()
    return paid_until


async def get_all_referrals() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """SELECT r.referrer_id, r.referred_id, r.discount_used, r.discount_product,
                      r.referrer_discount_used, r.referrer_discount_product, r.created_at,
                      u1.username AS referrer_username, u1.first_name AS referrer_name,
                      u2.username AS referred_username, u2.first_name AS referred_name
               FROM referrals r
               LEFT JOIN users u1 ON u1.telegram_id = r.referrer_id
               LEFT JOIN users u2 ON u2.telegram_id = r.referred_id
               ORDER BY r.created_at DESC"""
        )).fetchall()
        return [dict(r) for r in rows]


async def get_all_subscriptions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT user_id, plan, paid_until FROM subscriptions ORDER BY paid_until DESC"
        )).fetchall()
        return [dict(r) for r in rows]


async def get_all_product_access() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT user_id, product, plan, paid_until FROM product_access ORDER BY paid_until DESC"
        )).fetchall()
        return [dict(r) for r in rows]


async def revoke_subscription(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        await db.commit()


async def revoke_product_access(user_id: int, product: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM product_access WHERE user_id = ? AND product = ?",
            (user_id, product)
        )
        await db.commit()


async def create_referral(referrer_id: int, referred_id: int) -> bool:
    """Record that referred_id was invited by referrer_id. Returns True if newly created."""
    if referrer_id == referred_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        referrer = await (await db.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?", (referrer_id,)
        )).fetchone()
        if not referrer:
            return False
        existing = await (await db.execute(
            "SELECT id FROM referrals WHERE referred_id = ?", (referred_id,)
        )).fetchone()
        if existing:
            return False
        await db.execute(
            "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
            (referrer_id, referred_id)
        )
        await db.commit()
        return True


async def has_referral_discount(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT id FROM referrals WHERE referred_id = ? AND discount_used = 0", (user_id,)
        )).fetchone()
        return row is not None


async def use_referral_discount(user_id: int, product: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE referrals SET discount_used = 1, discount_product = ? WHERE referred_id = ? AND discount_used = 0",
            (product, user_id)
        )
        await db.commit()


async def has_referrer_discount(user_id: int) -> bool:
    """Check if user has an unused discount earned by inviting someone."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT id FROM referrals WHERE referrer_id = ? AND referrer_discount_used = 0",
            (user_id,)
        )).fetchone()
        return row is not None


async def use_referrer_discount(user_id: int, product: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE referrals SET referrer_discount_used = 1, referrer_discount_product = ?
               WHERE referrer_id = ? AND referrer_discount_used = 0""",
            (product, user_id)
        )
        await db.commit()


async def has_any_discount(user_id: int) -> bool:
    return await has_referral_discount(user_id) or await has_referrer_discount(user_id)


async def use_any_discount(user_id: int, product: str) -> None:
    if await has_referral_discount(user_id):
        await use_referral_discount(user_id, product)
    else:
        await use_referrer_discount(user_id, product)


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
