import csv
import html
import io
import logging
from datetime import datetime, date as _date

from aiogram import F, Router
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from services.db import (
    get_admin_stats, get_all_sessions_export,
    get_user_sessions, set_user_blocked, get_user_by_username,
)
from services.subscription import (
    grant_subscription, get_subscription_info, PLANS,
    grant_product_access, PRODUCT_PLANS,
    get_all_subscriptions, get_all_product_access,
    revoke_subscription, revoke_product_access,
    get_all_referrals,
)

log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        result = event.from_user.id in ADMIN_IDS
        if not result:
            log.warning("Admin access denied for user %s (ADMIN_IDS=%s)", event.from_user.id, ADMIN_IDS)
        return result


class AdminMsg(StatesGroup):
    waiting_text = State()


class AdminGrant(StatesGroup):
    waiting_user = State()


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_STAGE_LABELS = {
    "greeting": "Приветствие",
    "needs": "Выявление потребности",
    "presentation": "Презентация",
    "objections": "Возражения",
    "closing": "Закрытие сделки",
    "full": "Полная встреча",
}
_COHORT_LABELS = {
    "young": "Молодой (&lt;35)",
    "middle": "Средний (35-50)",
    "adult": "Взрослый (50-60)",
    "pensioner": "Пенсионер (60+)",
}


def _split_html(text: str, limit: int = 4000) -> list[str]:
    chunks, current = [], []
    current_len = 0
    for line in text.split("\n"):
        if current_len + len(line) + 1 > limit and current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика",      callback_data="admin:stats")
    b.button(text="🗂 Сессии",          callback_data="admin:sessions")
    b.button(text="👥 Пользователи",    callback_data="admin:users")
    b.button(text="📋 Подписки",        callback_data="admin:subs")
    b.button(text="🤝 Рефералы",        callback_data="admin:referrals")
    b.button(text="🎁 Выдать доступ",   callback_data="admin:grant")
    b.button(text="📥 Выгрузить CSV",   callback_data="admin:export_csv")
    b.adjust(2)
    return b.as_markup()


def _back_main():
    b = InlineKeyboardBuilder()
    b.button(text="← Главное меню", callback_data="admin:main")
    return b.as_markup()


def _grant_products_kb(user_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Тренировка — 6 мес",      callback_data=f"admin:gd:{user_id}:half_year:sub")
    b.button(text="🎯 Тренировка — 12 мес",     callback_data=f"admin:gd:{user_id}:year:sub")
    b.button(text="📚 Базовый уровень обучения", callback_data=f"admin:gd:{user_id}:learning_basic:prod")
    b.button(text="📈 Анализ акций — 1 мес",    callback_data=f"admin:gd:{user_id}:stocks_monthly:prod")
    b.button(text="← Отмена", callback_data="admin:main")
    b.adjust(1)
    return b.as_markup()


# ── /admin entry ──────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=_main_kb(),
    )


@router.callback_query(F.data == "admin:main")
async def admin_main(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=_main_kb(),
    )


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    st = await get_admin_stats()

    lines = ["📊 <b>Статистика бота</b>\n"]
    lines.append(f"👥 Пользователей: <b>{st['total_users']}</b>")
    lines.append(f"🗂 Сессий всего: <b>{st['sess_total']}</b>, завершено: <b>{int(st['sess_done'] or 0)}</b>")
    if st["avg_duration_min"]:
        lines.append(f"⏱ Среднее время сессии: <b>{st['avg_duration_min']} мин</b>")

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=_back_main()
    )


# ── Sessions ──────────────────────────────────────────────────────────────────

def _sessions_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📈 По этапам",      callback_data="admin:sess:stages")
    b.button(text="🛍 По продуктам",   callback_data="admin:sess:products")
    b.button(text="👤 По когортам",    callback_data="admin:sess:cohorts")
    b.button(text="🕐 Последние 50",   callback_data="admin:sess:recent")
    b.button(text="← Главное меню",   callback_data="admin:main")
    b.adjust(2, 2, 1)
    return b.as_markup()


@router.callback_query(F.data == "admin:sessions")
async def admin_sessions(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_text(
        "🗂 <b>Сессии</b>\n\nВыберите разрез:",
        parse_mode="HTML",
        reply_markup=_sessions_kb(),
    )


@router.callback_query(F.data == "admin:sess:stages")
async def admin_sess_stages(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    st = await get_admin_stats()
    lines = ["📈 <b>По этапам</b>\n"]
    if st["by_stage"]:
        for r in st["by_stage"]:
            label = _STAGE_LABELS.get(r["stage"], r["stage"])
            done = int(r["done"] or 0)
            avg_msgs = round(r["avg_msgs"] or 0, 1)
            avg_min = f", ~{round(r['avg_min'], 1)} мин" if r.get("avg_min") else ""
            lines.append(f"• <b>{label}</b>: {r['cnt']} сессий, завершено {done}, ~{avg_msgs} сообщ{avg_min}")
    else:
        lines.append("<i>Нет данных</i>")

    b = InlineKeyboardBuilder()
    b.button(text="← Сессии", callback_data="admin:sessions")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "admin:sess:products")
async def admin_sess_products(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    st = await get_admin_stats()
    lines = ["🛍 <b>По продуктам</b>\n"]
    if st["by_product"]:
        for r in st["by_product"]:
            done = int(r["done"] or 0)
            avg_msgs = round(r["avg_msgs"] or 0, 1)
            sc = r.get("avg_score")
            sc_str = f", ср. балл <b>{sc}/10</b>" if sc else ""
            lines.append(f"• {html.escape(r['product'] or '—')}: {r['cnt']} сессий, завершено {done}, ~{avg_msgs} сообщ{sc_str}")
    else:
        lines.append("<i>Нет данных</i>")

    b = InlineKeyboardBuilder()
    b.button(text="← Сессии", callback_data="admin:sessions")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "admin:sess:cohorts")
async def admin_sess_cohorts(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    st = await get_admin_stats()
    lines = ["👤 <b>По когортам клиентов</b>\n"]
    if st["by_cohort"]:
        for r in st["by_cohort"]:
            label = _COHORT_LABELS.get(r["cohort"], r["cohort"])
            done = int(r["done"] or 0)
            lines.append(f"• {label}: {r['cnt']} сессий, завершено {done}")
    else:
        lines.append("<i>Нет данных</i>")

    b = InlineKeyboardBuilder()
    b.button(text="← Сессии", callback_data="admin:sessions")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "admin:sess:recent")
async def admin_sess_recent(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    st = await get_admin_stats()
    lines = ["🕐 <b>Последние 50 сессий</b>\n"]
    if st["recent"]:
        for r in st["recent"]:
            stage = _STAGE_LABELS.get(r["stage"], r["stage"])
            status = "✅" if r["is_complete"] else "🔄"
            started = r["started_at"][:16] if r["started_at"] else "?"
            lines.append(
                f"{status} {html.escape(r['first_name'] or '—')} | {stage} | "
                f"{html.escape(r['product'] or '—')} | {r['msg_count']} сообщ | {started}"
            )
    else:
        lines.append("<i>Нет данных</i>")

    b = InlineKeyboardBuilder()
    b.button(text="← Сессии", callback_data="admin:sessions")
    text = "\n".join(lines)
    if len(text) > 4096:
        chunks = _split_html(text)
        await callback.message.edit_text(chunks[0], parse_mode="HTML")
        for chunk in chunks[1:-1]:
            await callback.message.answer(chunk, parse_mode="HTML")
        await callback.message.answer(chunks[-1], parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())


# ── Users ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    st = await get_admin_stats()
    users = st["users"]

    b = InlineKeyboardBuilder()
    for u in users:
        name = u["first_name"] or "—"
        uname = f" (@{u['username']})" if u["username"] else ""
        blocked_icon = "🚫 " if u.get("is_blocked") else "👤 "
        b.row(InlineKeyboardButton(
            text=f"{blocked_icon}{name}{uname}",
            callback_data=f"admin:user:{u['telegram_id']}",
        ))
    b.row(InlineKeyboardButton(text="← Главное меню", callback_data="admin:main"))

    await callback.message.edit_text(
        f"👥 <b>Пользователи</b> — {len(users)} чел.\n\nНажмите на пользователя:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    user_id = int(callback.data[len("admin:user:"):])
    sessions = await get_user_sessions(user_id)

    if not sessions:
        await callback.answer("Сессий не найдено", show_alert=True)
        return

    u = sessions[0]
    name = html.escape(u["first_name"] or "—")
    uname = f" (@{html.escape(u['username'])})" if u["username"] else ""
    registered = (u["created_at"] or "")[:10]
    total = len(sessions)
    done = sum(1 for s in sessions if s["is_complete"])

    lines = [
        f"👤 <b>{name}{uname}</b>",
        f"📅 Зарегистрирован: {registered}",
        f"📊 Сессий: {total} всего, завершено {done}\n",
        "<b>Все сессии:</b>",
    ]
    for i, s in enumerate(sessions, 1):
        status = "✅" if s["is_complete"] else "🔄"
        stage = _STAGE_LABELS.get(s["stage"] or "", s["stage"] or "—")
        product = html.escape(s["product"] or "—")
        cohort = _COHORT_LABELS.get(s["cohort"] or "", s["cohort"] or "—")
        msgs = s["msg_count"] or 0
        started = (s["started_at"] or "")[:16].replace("T", " ")
        dur_str = f" | {round(s['duration_min'], 0):.0f} мин" if s["duration_min"] is not None else ""
        lines.append(f"{i}. {status} {started} | {stage} | {product} | {cohort} | {msgs} сообщ{dur_str}")

    from services.db import is_user_blocked
    blocked = await is_user_blocked(user_id)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎁 Выдать доступ",  callback_data=f"admin:grant:{user_id}"))
    kb.row(InlineKeyboardButton(text="✉️ Написать в ЛС",  callback_data=f"admin:msg:{user_id}"))
    if blocked:
        kb.row(InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin:unblock:{user_id}"))
    else:
        kb.row(InlineKeyboardButton(text="🚫 Заблокировать",  callback_data=f"admin:block:{user_id}"))
    kb.row(InlineKeyboardButton(text="← Пользователи", callback_data="admin:users"))

    await callback.answer()
    full_text = "\n".join(lines)
    if len(full_text) <= 4096:
        await callback.message.edit_text(full_text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        chunks = _split_html(full_text)
        await callback.message.edit_text(chunks[0], parse_mode="HTML")
        for chunk in chunks[1:-1]:
            await callback.message.answer(chunk, parse_mode="HTML")
        await callback.message.answer(chunks[-1], parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("admin:block:"))
async def admin_block_user(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    user_id = int(callback.data[len("admin:block:"):])
    await set_user_blocked(user_id, True)
    await callback.answer("🚫 Пользователь заблокирован", show_alert=True)
    callback.data = f"admin:user:{user_id}"
    await admin_user_detail(callback)


@router.callback_query(F.data.startswith("admin:unblock:"))
async def admin_unblock_user(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    user_id = int(callback.data[len("admin:unblock:"):])
    await set_user_blocked(user_id, False)
    await callback.answer("✅ Пользователь разблокирован", show_alert=True)
    callback.data = f"admin:user:{user_id}"
    await admin_user_detail(callback)


# ── Message to user ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:msg:"))
async def admin_msg_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    user_id = int(callback.data[len("admin:msg:"):])
    await state.set_state(AdminMsg.waiting_text)
    await state.update_data(target_user_id=user_id)

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:msg_cancel:{user_id}"))
    await callback.answer()
    await callback.message.edit_text(
        f"✉️ Введите текст сообщения для <code>{user_id}</code>:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("admin:msg_cancel:"))
async def admin_msg_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await state.clear()
    user_id = int(callback.data[len("admin:msg_cancel:"):])
    await callback.answer("Отменено")
    callback.data = f"admin:user:{user_id}"
    await admin_user_detail(callback)


@router.message(AdminMsg.waiting_text)
async def admin_msg_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()
    try:
        await message.bot.send_message(target_user_id, message.text)
        await message.answer(f"✅ Сообщение отправлено <code>{target_user_id}</code>.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: <code>{e}</code>", parse_mode="HTML")


# ── Subscriptions ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:referrals")
async def admin_referrals(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    refs = await get_all_referrals()

    lines = ["🤝 <b>Реферальная программа</b>\n"]
    if not refs:
        lines.append("<i>Рефералов пока нет</i>")
    else:
        lines.append(f"Всего: <b>{len(refs)}</b>\n")
        for r in refs:
            ref_name = html.escape(r["referrer_name"] or str(r["referrer_id"]))
            ref_un = f"@{html.escape(r['referrer_username'])}" if r["referrer_username"] else f"<code>{r['referrer_id']}</code>"
            inv_name = html.escape(r["referred_name"] or str(r["referred_id"]))
            inv_un = f"@{html.escape(r['referred_username'])}" if r["referred_username"] else f"<code>{r['referred_id']}</code>"
            date = (r["created_at"] or "")[:10]

            ref_disc = "✅ использована" if r["referrer_discount_used"] else "🎁 доступна"
            inv_disc = "✅ использована" if r["discount_used"] else "🎁 доступна"

            lines.append(
                f"📅 {date}\n"
                f"  Реферер: {ref_name} ({ref_un}) — скидка реферера: {ref_disc}\n"
                f"  Приглашён: {inv_name} ({inv_un}) — скидка друга: {inv_disc}"
            )
            lines.append("")

    b = InlineKeyboardBuilder()
    b.button(text="← Главное меню", callback_data="admin:main")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "…"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "admin:subs")
async def admin_subs_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    today = _date.today().isoformat()
    subs = await get_all_subscriptions()
    prod = await get_all_product_access()

    lines = ["📋 <b>Активные подписки</b>\n"]
    if subs:
        lines.append("<b>Тренировка:</b>")
        for s in subs:
            active = "✅" if s["paid_until"] >= today else "⛔"
            lines.append(f"  {active} <code>{s['user_id']}</code> — {s['plan']} до {s['paid_until']}")
    else:
        lines.append("<i>Тренировка: нет</i>")

    lines.append("")
    if prod:
        lines.append("<b>Продукты:</b>")
        for p in prod:
            active = "✅" if p["paid_until"] >= today else "⛔"
            lines.append(f"  {active} <code>{p['user_id']}</code> — {p['product']} до {p['paid_until']}")
    else:
        lines.append("<i>Продукты: нет</i>")

    kb = InlineKeyboardBuilder()
    for s in subs:
        if s["paid_until"] >= today:
            kb.row(InlineKeyboardButton(
                text=f"❌ Отозвать тренировку у {s['user_id']}",
                callback_data=f"admin:revoke_sub:{s['user_id']}",
            ))
    for p in prod:
        if p["paid_until"] >= today:
            kb.row(InlineKeyboardButton(
                text=f"❌ Отозвать {p['product']} у {p['user_id']}",
                callback_data=f"admin:revoke_prod:{p['user_id']}:{p['product']}",
            ))
    kb.row(InlineKeyboardButton(text="← Главное меню", callback_data="admin:main"))

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("admin:revoke_sub:"))
async def admin_revoke_sub(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    user_id = int(callback.data[len("admin:revoke_sub:"):])
    await revoke_subscription(user_id)
    await callback.answer(f"✅ Подписка отозвана у {user_id}", show_alert=True)
    callback.data = "admin:subs"
    await admin_subs_list(callback)


@router.callback_query(F.data.startswith("admin:revoke_prod:"))
async def admin_revoke_prod(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    parts = callback.data.split(":")
    user_id = int(parts[2])
    product = parts[3]
    await revoke_product_access(user_id, product)
    await callback.answer(f"✅ Доступ к {product} отозван у {user_id}", show_alert=True)
    callback.data = "admin:subs"
    await admin_subs_list(callback)


# ── Grant access ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:grant")
async def admin_grant_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await state.set_state(AdminGrant.waiting_user)
    await callback.answer()
    b = InlineKeyboardBuilder()
    b.button(text="← Отмена", callback_data="admin:main")
    await callback.message.edit_text(
        "🎁 <b>Выдать доступ</b>\n\nВведите ID или @username пользователя:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("admin:grant:"))
async def admin_grant_known_user(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    user_id = int(callback.data[len("admin:grant:"):])
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        f"🎁 <b>Выдать доступ</b> — <code>{user_id}</code>\n\nВыберите тип:",
        parse_mode="HTML",
        reply_markup=_grant_products_kb(user_id),
    )


@router.message(AdminGrant.waiting_user)
async def admin_grant_lookup(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    query = (message.text or "").strip()
    user = None
    user_id = None

    if query.lstrip("@").isdigit():
        user_id = int(query.lstrip("@"))
    else:
        user = await get_user_by_username(query.lstrip("@"))
        if user:
            user_id = user["telegram_id"]

    if not user_id:
        b = InlineKeyboardBuilder()
        b.button(text="← Отмена", callback_data="admin:main")
        await message.answer(
            f"❌ Пользователь <code>{html.escape(query)}</code> не найден.\nВведите ещё раз:",
            parse_mode="HTML",
            reply_markup=b.as_markup(),
        )
        return

    await state.clear()
    name_str = f" ({user.get('first_name', '')} @{user.get('username', '')})" if user else ""
    await message.answer(
        f"🎁 <b>Выдать доступ</b> — <code>{user_id}</code>{name_str}\n\nВыберите тип:",
        parse_mode="HTML",
        reply_markup=_grant_products_kb(user_id),
    )


@router.callback_query(F.data.startswith("admin:gd:"))
async def admin_grant_do(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    parts = callback.data.split(":")
    user_id = int(parts[2])
    kind = parts[-1]
    plan = "_".join(parts[3:-1])
    await state.clear()

    if kind == "sub":
        paid_until = await grant_subscription(user_id, plan)
        label = PLANS.get(plan, {}).get("label", plan)
    else:
        product_map = {"learning_basic": "learning_basic", "stocks_monthly": "stocks"}
        product = product_map.get(plan, plan)
        paid_until = await grant_product_access(user_id, product, plan)
        label = PRODUCT_PLANS.get(plan, {}).get("label", plan)

    await callback.answer("✅ Доступ выдан!", show_alert=True)
    b = InlineKeyboardBuilder()
    b.button(text="← Главное меню", callback_data="admin:main")
    await callback.message.edit_text(
        f"✅ <b>Доступ выдан</b>\n\n"
        f"Пользователь: <code>{user_id}</code>\n"
        f"Тип: <b>{label}</b>\n"
        f"До: <b>{paid_until.strftime('%d.%m.%Y')}</b>",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


# ── Export CSV ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:export_csv")
async def admin_export_csv(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer("Формирую файл...")
    rows = await get_all_sessions_export()
    if not rows:
        await callback.message.answer("Данных для выгрузки нет.")
        return
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys(), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    filename = f"bot_stats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    file = BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=filename)
    await callback.message.answer_document(file, caption=f"📊 Экспорт — {len(rows)} сессий")


# ── Legacy back (in case old messages still around) ───────────────────────────

@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=_main_kb(),
    )


# ── Legacy commands ───────────────────────────────────────────────────────────

@router.message(Command("grant_sub"))
async def cmd_grant_sub(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) != 3 or parts[2] not in PLANS:
        await message.answer(
            f"Использование: <code>/grant_sub &lt;user_id&gt; &lt;plan&gt;</code>\nПланы: {' | '.join(PLANS.keys())}",
            parse_mode="HTML",
        )
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом", parse_mode="HTML")
        return
    paid_until = await grant_subscription(user_id, parts[2])
    await message.answer(
        f"✅ Подписка выдана <code>{user_id}</code> — {PLANS[parts[2]]['label']} до {paid_until.strftime('%d.%m.%Y')}",
        parse_mode="HTML",
    )


@router.message(Command("check_sub"))
async def cmd_check_sub(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: <code>/check_sub &lt;user_id&gt;</code>", parse_mode="HTML")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом")
        return
    info = await get_subscription_info(user_id)
    if not info:
        await message.answer(f"❌ Подписка для <code>{user_id}</code> не найдена", parse_mode="HTML")
    else:
        from services.subscription import is_subscribed
        active = await is_subscribed(user_id)
        status = "✅ активна" if active else "⛔ истекла"
        await message.answer(
            f"👤 <code>{user_id}</code>\nТариф: {info['plan']}\nДо: {info['paid_until']}\nСтатус: {status}",
            parse_mode="HTML",
        )
