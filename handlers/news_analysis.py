from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states.news_analysis import NewsAnalysis
from prompts.news_prompts import PRODUCT_NAMES
from services.claude import analyze_news_impact
from services.news_fetcher import fetch_news, format_news_for_prompt

router = Router()

_OPIF_PRODUCTS = {"obligplus", "obligincome", "balanced", "stocks", "money", "bonds"}
_OMS_PRODUCTS = {"gold", "silver", "platinum", "palladium"}
_STRATEGY_PRODUCTS = {"tg", "nav", "eternal"}


# ── Keyboards ────────────────────────────────────────────────────────────────

def _news_main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🌍 Общее влияние на рынок", callback_data="news:cat:general")
    b.button(text="📊 На ОПИФ", callback_data="news:cat:opif")
    b.button(text="🥇 На ОМС", callback_data="news:cat:oms")
    b.button(text="⚡ На Стратегии", callback_data="news:cat:strategy")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


def _opif_kb():
    b = InlineKeyboardBuilder()
    b.button(text="Облигации Плюс", callback_data="news:prod:obligplus")
    b.button(text="Облигации с выплатой дохода", callback_data="news:prod:obligincome")
    b.button(text="Сбалансированный с выплатой дохода", callback_data="news:prod:balanced")
    b.button(text="Управляемые акции с выплатой дохода", callback_data="news:prod:stocks")
    b.button(text="Денежный рынок", callback_data="news:prod:money")
    b.button(text="Управляемые облигации", callback_data="news:prod:bonds")
    b.button(text="◀️ Назад", callback_data="news:menu")
    b.adjust(1)
    return b.as_markup()


def _oms_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🥇 Золото", callback_data="news:prod:gold")
    b.button(text="🥈 Серебро", callback_data="news:prod:silver")
    b.button(text="⬜ Платина", callback_data="news:prod:platinum")
    b.button(text="⬜ Палладий", callback_data="news:prod:palladium")
    b.button(text="◀️ Назад", callback_data="news:menu")
    b.adjust(1)
    return b.as_markup()


def _strategy_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🏝 Тихая Гавань", callback_data="news:prod:tg")
    b.button(text="🧭 Навигатор фондов", callback_data="news:prod:nav")
    b.button(text="♾ Вечный портфель", callback_data="news:prod:eternal")
    b.button(text="◀️ Назад", callback_data="news:menu")
    b.adjust(1)
    return b.as_markup()


def _input_mode_kb(product_id: str):
    b = InlineKeyboardBuilder()
    b.button(text="📝 Вставить новость", callback_data=f"news:input:manual:{product_id}")
    b.button(text="🔄 Новости за 48 часов", callback_data=f"news:input:auto:{product_id}")
    b.button(text="◀️ Назад", callback_data=f"news:back:{product_id}")
    b.adjust(1)
    return b.as_markup()


def _after_analysis_kb(product_id: str):
    b = InlineKeyboardBuilder()
    b.button(text="📝 Ещё новость", callback_data=f"news:input:manual:{product_id}")
    b.button(text="◀️ К продуктам", callback_data=f"news:back:{product_id}")
    b.button(text="🏠 Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


# ── Category handlers ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "news:menu")
async def news_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(NewsAnalysis.choosing_category)
    await callback.message.edit_text(
        "📰 <b>Анализ новостей</b>\n\nВыберите категорию:",
        parse_mode="HTML",
        reply_markup=_news_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:general")
async def news_cat_general(callback: CallbackQuery, state: FSMContext):
    await state.update_data(product_id="general")
    await state.set_state(NewsAnalysis.choosing_input_mode)
    await callback.message.edit_text(
        f"🌍 <b>{PRODUCT_NAMES['general']}</b>\n\nВыберите способ анализа:",
        parse_mode="HTML",
        reply_markup=_input_mode_kb("general"),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:opif")
async def news_cat_opif(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewsAnalysis.choosing_product)
    await callback.message.edit_text(
        "📊 <b>ОПИФ — выберите фонд:</b>",
        parse_mode="HTML",
        reply_markup=_opif_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:oms")
async def news_cat_oms(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewsAnalysis.choosing_product)
    await callback.message.edit_text(
        "🥇 <b>ОМС — выберите металл:</b>",
        parse_mode="HTML",
        reply_markup=_oms_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "news:cat:strategy")
async def news_cat_strategy(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NewsAnalysis.choosing_product)
    await callback.message.edit_text(
        "⚡ <b>Стратегии — выберите стратегию:</b>",
        parse_mode="HTML",
        reply_markup=_strategy_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("news:prod:"))
async def news_select_product(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:prod:"):]
    await state.update_data(product_id=product_id)
    await state.set_state(NewsAnalysis.choosing_input_mode)
    product_name = PRODUCT_NAMES.get(product_id, product_id)
    await callback.message.edit_text(
        f"📌 <b>{product_name}</b>\n\nВыберите способ анализа:",
        parse_mode="HTML",
        reply_markup=_input_mode_kb(product_id),
    )
    await callback.answer()


# ── Input mode handlers ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("news:input:manual:"))
async def news_input_manual(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:input:manual:"):]
    await state.update_data(product_id=product_id)
    await state.set_state(NewsAnalysis.waiting_news)
    product_name = PRODUCT_NAMES.get(product_id, product_id)
    await callback.message.edit_text(
        f"📝 <b>Введите текст новости</b>\n\n"
        f"Продукт: <i>{product_name}</i>\n\n"
        f"Вставьте или напишите текст новости для анализа:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("news:input:auto:"))
async def news_input_auto(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:input:auto:"):]
    product_name = PRODUCT_NAMES.get(product_id, product_id)

    await callback.answer()
    status = await callback.message.edit_text("⏳ Ищу свежие новости...")

    news_items = await fetch_news()

    if not news_items:
        await status.edit_text(
            "❌ Свежих новостей не найдено. Попробуйте вставить новость вручную.",
            reply_markup=_input_mode_kb(product_id),
        )
        return

    news_text = format_news_for_prompt(news_items)
    await status.edit_text(
        f"🤔 Анализирую {len(news_items)} новостей для <b>{product_name}</b>...",
        parse_mode="HTML",
    )

    try:
        result = await analyze_news_impact(news_text, product_id)
        await status.edit_text(result, parse_mode="HTML", reply_markup=_after_analysis_kb(product_id))
    except Exception as e:
        await status.edit_text(f"❌ Ошибка анализа: {e}", reply_markup=_input_mode_kb(product_id))


# ── Text input handler ────────────────────────────────────────────────────────

@router.message(NewsAnalysis.waiting_news, F.text)
async def news_receive_text(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id", "general")
    product_name = PRODUCT_NAMES.get(product_id, product_id)

    news_text = message.text[:3000]
    warning = "⚠️ Текст обрезан до 3000 символов.\n\n" if len(message.text) > 3000 else ""

    status = await message.answer(
        f"🤔 Анализирую новость для <b>{product_name}</b>...",
        parse_mode="HTML",
    )

    try:
        result = await analyze_news_impact(news_text, product_id)
        await status.edit_text(
            warning + result,
            parse_mode="HTML",
            reply_markup=_after_analysis_kb(product_id),
        )
    except Exception as e:
        await status.edit_text(f"❌ Ошибка анализа: {e}")


@router.message(NewsAnalysis.waiting_news, ~F.text)
async def news_wrong_input(message: Message):
    await message.answer(
        "📝 Пожалуйста, отправьте <b>текст</b> новости.",
        parse_mode="HTML",
    )


# ── Back navigation ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("news:back:"))
async def news_back(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data[len("news:back:"):]
    if product_id == "general":
        await news_menu(callback, state)
    elif product_id in _OPIF_PRODUCTS:
        await news_cat_opif(callback, state)
    elif product_id in _OMS_PRODUCTS:
        await news_cat_oms(callback, state)
    elif product_id in _STRATEGY_PRODUCTS:
        await news_cat_strategy(callback, state)
    else:
        await news_menu(callback, state)
