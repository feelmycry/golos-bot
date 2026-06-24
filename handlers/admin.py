import csv
import io
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from services.db import get_admin_stats, get_all_sessions_export, get_user_sessions, set_user_blocked

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
        name = u["first_name"] or "—"
        uname = f"@{u['username']}" if u["username"] else "без username"
        done = int(u["sessions_done"] or 0)
        lines.append(f"  • {name} ({uname}) — {u['sessions_total']} сессий, завершено {done}")

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
        lines.append("\n🛍 <b>По продуктам:</b>")
        for r in st["by_product"]:
            done = int(r["done"] or 0)
            avg_msgs = round(r["avg_msgs"] or 0, 1)
            lines.append(f"  • {r['product']}: {r['cnt']} сессий, завершено {done}, ~{avg_msgs} сообщ")

    if st["by_cohort"]:
        lines.append("\n👤 <b>По когортам клиентов:</b>")
        for r in st["by_cohort"]:
            label = _COHORT_LABELS.get(r["cohort"], r["cohort"])
            done = int(r["done"] or 0)
            lines.append(f"  • {label}: {r['cnt']} сессий, завершено {done}")

    if st["recent"]:
        lines.append("\n🕐 <b>Последние 5 сессий:</b>")
        for r in st["recent"]:
            stage = _STAGE_LABELS.get(r["stage"], r["stage"])
            status = "✅" if r["is_complete"] else "🔄"
            started = r["started_at"][:16] if r["started_at"] else "?"
            lines.append(
                f"  {status} {r['first_name']} | {stage} | "
                f"{r['product'] or '—'} | {r['msg_count']} сообщ | {started}"
            )

    lines.append("\n\n<i>Нажми на пользователя для детального разреза:</i>")
    kb = _users_kb(st["users"])

    text = "\n".join(lines)
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())


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
    name = u["first_name"] or "—"
    uname = f" (@{u['username']})" if u["username"] else ""
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
        product = s["product"] or "—"
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
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


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
