import csv
import html
import io
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from services.db import get_admin_stats, get_all_sessions_export, get_user_sessions, set_user_blocked
from services.subscription import grant_subscription, get_subscription_info, PLANS


class AdminMsg(StatesGroup):
    waiting_text = State()

router = Router()

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
    """Split text into chunks at line boundaries, never breaking HTML tags."""
    chunks, current = [], []
    current_len = 0
    for line in text.split("\n"):
        # +1 for the newline we'll re-join with
        if current_len + len(line) + 1 > limit and current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _users_kb(users: list) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for u in users:
        name = u["first_name"] or "—"
        uname = f" (@{u['username']})" if u["username"] else ""
        blocked_icon = "🚫 " if u.get("is_blocked") else "👤 "
        label = f"{blocked_icon}{name}{uname}"
        kb.row(InlineKeyboardButton(text=label, callback_data=f"admin:user:{u['telegram_id']}"))
    kb.row(InlineKeyboardButton(text="📥 Выгрузить CSV", callback_data="admin:export_csv"))
    return kb


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await _send_admin_summary(message)


async def _send_admin_summary(target):
    st = await get_admin_stats()
    lines = ["📊 <b>Статистика бота</b>\n"]

    lines.append(f"👥 <b>Пользователи:</b> {st['total_users']}")
    for u in st["users"]:
        name = html.escape(u["first_name"] or "—")
        uname = f"@{html.escape(u['username'])}" if u["username"] else "без username"
        done = int(u["sessions_done"] or 0)
        sc = u.get("avg_score")
        sc_str = f", ср. балл {sc}/10" if sc else ""
        lines.append(f"  • {name} ({uname}) — {u['sessions_total']} сессий, завершено {done}{sc_str}")

    lines.append(f"\n🗂 <b>Сессии:</b> {st['sess_total']} всего, завершено {int(st['sess_done'] or 0)}")
    if st["avg_duration_min"]:
        lines.append(f"⏱ Среднее время завершённой сессии: <b>{st['avg_duration_min']} мин</b>")

    if st["by_stage"]:
        lines.append("\n📈 <b>По этапам:</b>")
        for r in st["by_stage"]:
            label = _STAGE_LABELS.get(r["stage"], r["stage"])
            done = int(r["done"] or 0)
            avg_msgs = round(r["avg_msgs"] or 0, 1)
            avg_min = f", ~{round(r['avg_min'], 1)} мин" if r.get("avg_min") else ""
            lines.append(f"  • <b>{label}</b>: {r['cnt']} сессий, завершено {done}, ~{avg_msgs} сообщ{avg_min}")

    if st["by_product"]:
        lines.append("\n🛍 <b>По продуктам (сортировка: слабейший сначала):</b>")
        for r in st["by_product"]:
            done = int(r["done"] or 0)
            avg_msgs = round(r["avg_msgs"] or 0, 1)
            sc = r.get("avg_score")
            sc_str = f", ср. балл <b>{sc}/10</b>" if sc else ""
            lines.append(f"  • {html.escape(r['product'] or '—')}: {r['cnt']} сессий, завершено {done}, ~{avg_msgs} сообщ{sc_str}")

    if st["by_cohort"]:
        lines.append("\n👤 <b>По когортам клиентов:</b>")
        for r in st["by_cohort"]:
            label = _COHORT_LABELS.get(r["cohort"], r["cohort"])
            done = int(r["done"] or 0)
            lines.append(f"  • {label}: {r['cnt']} сессий, завершено {done}")

    if st["recent"]:
        lines.append("\n🕐 <b>Последние 50 сессий:</b>")
        for r in st["recent"]:
            stage = _STAGE_LABELS.get(r["stage"], r["stage"])
            status = "✅" if r["is_complete"] else "🔄"
            started = r["started_at"][:16] if r["started_at"] else "?"
            lines.append(
                f"  {status} {html.escape(r['first_name'] or '—')} | {stage} | "
                f"{html.escape(r['product'] or '—')} | {r['msg_count']} сообщ | {started}"
            )

    lines.append("\n\n<i>Нажми на пользователя для детального разреза:</i>")
    kb = _users_kb(st["users"])

    text = "\n".join(lines)
    try:
        if isinstance(target, Message):
            if len(text) <= 4096:
                await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
            else:
                chunks = _split_html(text)
                for chunk in chunks[:-1]:
                    await target.answer(chunk, parse_mode="HTML")
                await target.answer(chunks[-1], parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            if len(text) <= 4096:
                await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
            else:
                chunks = _split_html(text)
                await target.message.edit_text(chunks[0], parse_mode="HTML")
                for chunk in chunks[1:-1]:
                    await target.message.answer(chunk, parse_mode="HTML")
                await target.message.answer(chunks[-1], parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        err = f"❌ Ошибка при отображении статистики: {e}"
        if isinstance(target, Message):
            await target.answer(err)
        else:
            await target.message.answer(err)


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

        dur_str = ""
        if s["duration_min"] is not None:
            dur_str = f" | {round(s['duration_min'], 0):.0f} мин"

        lines.append(
            f"{i}. {status} {started} | {stage} | {product} | {cohort} | {msgs} сообщ{dur_str}"
        )

    # Determine current block status from sessions query (first row has user data)
    from services.db import is_user_blocked
    blocked = await is_user_blocked(user_id)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="✉️ Написать в ЛС",
        callback_data=f"admin:msg:{user_id}",
    ))
    if blocked:
        kb.row(InlineKeyboardButton(
            text="✅ Разблокировать",
            callback_data=f"admin:unblock:{user_id}",
        ))
    else:
        kb.row(InlineKeyboardButton(
            text="🚫 Заблокировать",
            callback_data=f"admin:block:{user_id}",
        ))
    kb.row(InlineKeyboardButton(text="← Назад к статистике", callback_data="admin:back"))

    await callback.answer()
    full_text = "\n".join(lines)
    # Telegram message limit is 4096 chars; split if needed
    if len(full_text) <= 4096:
        await callback.message.edit_text(full_text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        # Send first chunk as edit (no keyboard), rest as new messages, last gets keyboard
        chunks = _split_html(full_text)
        await callback.message.edit_text(chunks[0], parse_mode="HTML")
        for chunk in chunks[1:-1]:
            await callback.message.answer(chunk, parse_mode="HTML")
        await callback.message.answer(chunks[-1], parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.answer()
    await _send_admin_summary(callback)


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
    await callback.message.answer_document(file, caption=f"📊 Экспорт данных — {len(rows)} сессий")


@router.callback_query(F.data.startswith("admin:block:"))
async def admin_block_user(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    user_id = int(callback.data[len("admin:block:"):])
    await set_user_blocked(user_id, True)
    await callback.answer("🚫 Пользователь заблокирован", show_alert=True)
    # Refresh the user detail view
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


@router.callback_query(F.data.startswith("admin:msg:"))
async def admin_msg_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    user_id = int(callback.data[len("admin:msg:"):])
    await state.set_state(AdminMsg.waiting_text)
    await state.update_data(target_user_id=user_id)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:msg_cancel:{user_id}"))

    await callback.answer()
    await callback.message.edit_text(
        f"✉️ Введите текст сообщения для пользователя <code>{user_id}</code>.\n\n"
        "Сообщение будет отправлено от имени бота:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
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
        await message.answer(f"✅ Сообщение отправлено пользователю <code>{target_user_id}</code>.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: <code>{e}</code>", parse_mode="HTML")


@router.message(Command("grant_sub"))
async def cmd_grant_sub(message: Message):
    """Usage: /grant_sub <user_id> <plan>   plan = quarter | year"""
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) != 3 or parts[2] not in PLANS:
        plans_str = " | ".join(PLANS.keys())
        await message.answer(
            f"Использование: <code>/grant_sub &lt;user_id&gt; &lt;plan&gt;</code>\n"
            f"Планы: {plans_str}",
            parse_mode="HTML",
        )
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом", parse_mode="HTML")
        return
    plan = parts[2]
    paid_until = await grant_subscription(user_id, plan)
    await message.answer(
        f"✅ Подписка выдана пользователю <code>{user_id}</code>\n"
        f"Тариф: <b>{PLANS[plan]['label']}</b>\n"
        f"До: <b>{paid_until.strftime('%d.%m.%Y')}</b>",
        parse_mode="HTML",
    )


@router.message(Command("check_sub"))
async def cmd_check_sub(message: Message):
    """Usage: /check_sub <user_id>"""
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
        from datetime import date
        from services.subscription import is_subscribed
        active = await is_subscribed(user_id)
        status = "✅ активна" if active else "⛔ истекла"
        await message.answer(
            f"👤 <code>{user_id}</code>\n"
            f"Тариф: {info['plan']}\n"
            f"До: {info['paid_until']}\n"
            f"Статус: {status}",
            parse_mode="HTML",
        )
