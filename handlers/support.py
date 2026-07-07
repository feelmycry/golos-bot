from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from states.support import SupportState, AdminReply

router = Router()

_CATEGORIES = {
    "payment": "💳 Проблема с оплатой",
    "access":  "🔑 Проблема с доступом",
    "bug":     "🐛 Баги, ошибки, завис бот",
    "idea":    "💡 Предложения по улучшению",
}


def _support_menu_kb():
    b = InlineKeyboardBuilder()
    for key, label in _CATEGORIES.items():
        b.button(text=label, callback_data=f"support:cat:{key}")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "support:menu")
async def support_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "🆘 <b>Поддержка</b>\n\nВыберите тему обращения:",
        parse_mode="HTML",
        reply_markup=_support_menu_kb(),
    )


@router.callback_query(F.data.startswith("support:cat:"))
async def support_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data[len("support:cat:"):]
    if category not in _CATEGORIES:
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    label = _CATEGORIES[category]
    await state.set_state(SupportState.writing_message)
    await state.update_data(support_category=category)
    await callback.answer()

    b = InlineKeyboardBuilder()
    b.button(text="◀️ Отмена", callback_data="support:menu")
    b.adjust(1)

    await callback.message.edit_text(
        f"✏️ <b>{label}</b>\n\nОпишите вашу проблему или идею, и мы ответим вам в ближайшее время:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


@router.message(SupportState.writing_message)
async def support_receive_message(message: Message, state: FSMContext):
    fsm = await state.get_data()
    category = fsm.get("support_category", "unknown")
    label = _CATEGORIES.get(category, category)
    await state.clear()

    user = message.from_user
    mention = f"@{user.username}" if user.username else f"ID <code>{user.id}</code>"
    forward_text = (
        f"📨 <b>Обращение в поддержку</b>\n\n"
        f"Тема: {label}\n"
        f"От: {user.first_name or ''} {mention}\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"<b>Сообщение:</b>\n{message.text or '— (не текст)'}"
    )

    reply_kb = InlineKeyboardBuilder()
    reply_kb.button(text="✉️ Ответить пользователю", callback_data=f"support:reply:{user.id}")
    reply_kb.adjust(1)

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id, forward_text,
                parse_mode="HTML",
                reply_markup=reply_kb.as_markup(),
            )
        except Exception:
            pass

    b = InlineKeyboardBuilder()
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)

    await message.answer(
        "✅ Ваше обращение отправлено. Ответим в ближайшее время!",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("support:reply:"))
async def admin_reply_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    target_user_id = int(callback.data[len("support:reply:"):])
    await state.set_state(AdminReply.writing_reply)
    await state.update_data(reply_to_user=target_user_id)
    await callback.answer()

    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="admin:reply_cancel")
    b.adjust(1)

    await callback.message.answer(
        f"✏️ Введите ответ пользователю <code>{target_user_id}</code>:\n"
        f"(ваш текст будет отправлен ему от имени бота)",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


@router.callback_query(AdminReply.writing_reply, F.data == "admin:reply_cancel")
async def admin_reply_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("❌ Ответ отменён.")


@router.message(AdminReply.writing_reply)
async def admin_reply_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    fsm = await state.get_data()
    target_user_id = fsm.get("reply_to_user")
    await state.clear()

    try:
        await message.bot.send_message(
            target_user_id,
            f"📬 <b>Ответ от поддержки:</b>\n\n{message.text}",
            parse_mode="HTML",
        )
        await message.answer(f"✅ Ответ отправлен пользователю <code>{target_user_id}</code>.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")
