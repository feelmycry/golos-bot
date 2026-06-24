from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.market_data import get_market_snapshot, format_snapshot

router = Router()


def _briefing_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Обновить", callback_data="briefing:refresh")
    b.button(text="🏠 Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.in_({"briefing:open", "briefing:refresh"}))
async def show_briefing(callback: CallbackQuery):
    await callback.answer()
    msg = await callback.message.edit_text("⏳ Загружаю данные...")
    try:
        snap = await get_market_snapshot()
        text = format_snapshot(snap)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=_briefing_kb())
    except Exception as e:
        await msg.edit_text(
            f"❌ Не удалось загрузить данные: {e}",
            reply_markup=_briefing_kb(),
        )
