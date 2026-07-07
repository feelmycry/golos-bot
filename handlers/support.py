from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from states.support import SupportState

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
        f"От: {user.first_name or ''} {mention}\n\n"
        f"<b>Сообщение:</b>\n{message.text or '— (не текст)'}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, forward_text, parse_mode="HTML")
        except Exception:
            pass

    b = InlineKeyboardBuilder()
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)

    await message.answer(
        "✅ Ваше обращение отправлено. Ответим в ближайшее время!",
        reply_markup=b.as_markup(),
    )
