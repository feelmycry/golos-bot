from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.db import upsert_user, get_user_stats

router = Router()

_COHORT_LABELS = {
    "young": "Молодой (до 35)",
    "middle": "Средний возраст (35–50)",
    "adult": "Взрослый (50–60)",
    "pensioner": "Пенсионер (60+)",
}

_STAGE_LABELS = {
    "greeting": "Приветствие",
    "needs": "Выявление потребности",
    "presentation": "Презентация",
    "objections": "Возражения",
    "closing": "Закрытие сделки",
    "full": "Полная встреча",
}


def _main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Начать тренировку", callback_data="start_training")
    b.button(text="📰 Анализ новостей", callback_data="news:menu")
    b.button(text="📊 Моя статистика", callback_data="show_stats")
    b.adjust(1)
    return b.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    name = message.from_user.first_name or "Коллега"
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        f"Я — тренажёр по продажам инвестиционных продуктов <b>Альфа-Банка</b> "
        f"и помощник по анализу новостей на инвестиционные продукты.\n\n"
        f"Помогу отработать навыки продаж:\n"
        f"• НСЖ — Альфа-Страхование жизни\n"
        f"• ПДС — Альфа НПФ\n"
        f"• ОПИФ — Альфа-Капитал\n"
        f"• ОМС — металлические счета\n"
        f"• Стратегии автоследования — Альфа-Инвестиции\n\n"
        f"Отвечай <b>голосовыми сообщениями</b> — я распознаю и анализирую твой ответ через AI.",
        parse_mode="HTML",
        reply_markup=_main_kb(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Сессия сброшена. Выберите действие:", reply_markup=_main_kb())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    name = callback.from_user.first_name or "Коллега"
    await callback.message.edit_text(
        f"Привет, {name}! Выберите действие:",
        reply_markup=_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "show_stats")
async def show_stats(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id)

    lines = [f"📊 <b>Ваша статистика</b>\n\nВсего сессий: {stats['total']} (завершено: {stats['completed']})"]

    if stats["by_cohort"]:
        lines.append("\n<b>По когортам:</b>")
        for row in stats["by_cohort"]:
            label = _COHORT_LABELS.get(row.get("cohort", ""), row.get("cohort", "—"))
            lines.append(f"• {label}: {row['total']} сессий ({row['completed'] or 0} завершено)")

    if stats["by_stage"]:
        lines.append("\n<b>По этапам:</b>")
        for row in stats["by_stage"]:
            label = _STAGE_LABELS.get(row.get("stage", ""), row.get("stage", "—"))
            lines.append(f"• {label}: {row['total']}")

    if stats["total"] == 0:
        lines.append("\nПока нет ни одной сессии. Начните первую тренировку!")

    b = InlineKeyboardBuilder()
    b.button(text="🎯 Начать тренировку", callback_data="start_training")
    b.button(text="◀️ Назад", callback_data="back_to_menu")
    b.adjust(1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=b.as_markup())
    await callback.answer()
