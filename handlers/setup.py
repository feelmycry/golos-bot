from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states.training import Training
from services.client_gen import generate_client
from services.claude import get_opening_message
from services.db import upsert_user, create_session, update_messages

router = Router()


# ── Keyboards ────────────────────────────────────────────────────────────────

def _scenario_kb():
    b = InlineKeyboardBuilder()
    b.button(text="💰 Оформление депозита", callback_data="scenario:deposit")
    b.button(text="🏦 Другая операция", callback_data="scenario:other")
    b.adjust(1)
    return b.as_markup()


def _mode_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Полная встреча", callback_data="mode:full")
    b.button(text="📍 Конкретный этап", callback_data="mode:stage")
    b.adjust(1)
    return b.as_markup()


def _stage_kb():
    b = InlineKeyboardBuilder()
    b.button(text="👋 Приветствие", callback_data="stage:greeting")
    b.button(text="🔍 Выявление потребности", callback_data="stage:needs")
    b.button(text="📢 Презентация продукта", callback_data="stage:presentation")
    b.button(text="💬 Отработка возражений", callback_data="stage:objections")
    b.button(text="🤝 Закрытие сделки", callback_data="stage:closing")
    b.adjust(1)
    return b.as_markup()


def _product_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🏦 ПДС (Альфа НПФ)", callback_data="product:pds")
    b.button(text="🛡 НСЖ (Альфа-Страхование)", callback_data="product:nsj")
    b.button(text="📈 ОПИФ (Альфа-Капитал)", callback_data="product:opif")
    b.button(text="🥇 ОМС (металлические счета)", callback_data="product:oms")
    b.button(text="⚡ Стратегия (автоследование)", callback_data="product:strategy")
    b.button(text="💼 Портфель (диверсификация)", callback_data="product:portfolio")
    b.adjust(1)
    return b.as_markup()


def _cohort_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🧑 Молодой (до 35)", callback_data="cohort:young")
    b.button(text="👔 Средний возраст (35–50)", callback_data="cohort:middle")
    b.button(text="🧓 Взрослый (50–60)", callback_data="cohort:adult")
    b.button(text="👴 Пенсионер (60+)", callback_data="cohort:pensioner")
    b.adjust(1)
    return b.as_markup()


def _dialog_kb():
    b = InlineKeyboardBuilder()
    b.button(text="💡 Подсказка", callback_data="dialog:hint")
    b.button(text="🏁 Завершить", callback_data="dialog:end")
    b.adjust(2)
    return b.as_markup()


# ── Flow ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "start_training")
async def start_training(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите тип клиента:", reply_markup=_scenario_kb())
    await state.set_state(Training.choosing_scenario)
    await callback.answer()


@router.callback_query(Training.choosing_scenario, F.data.startswith("scenario:"))
async def choose_scenario(callback: CallbackQuery, state: FSMContext):
    scenario = callback.data.split(":")[1]
    await state.update_data(scenario=scenario)
    label = "Оформление депозита" if scenario == "deposit" else "Другая операция"
    await callback.message.edit_text(
        f"Сценарий: <b>{label}</b>\n\nЧто хотите отработать?",
        parse_mode="HTML",
        reply_markup=_mode_kb(),
    )
    await state.set_state(Training.choosing_mode)
    await callback.answer()


@router.callback_query(Training.choosing_mode, F.data.startswith("mode:"))
async def choose_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    await state.update_data(mode=mode)

    if mode == "full":
        await state.update_data(target_stage="full")
        await callback.message.edit_text(
            "Полная встреча\n\nКакой продукт планируете предложить клиенту?",
            reply_markup=_product_kb(),
        )
        await state.set_state(Training.choosing_product)
    else:
        await callback.message.edit_text("Выберите этап для отработки:", reply_markup=_stage_kb())
        await state.set_state(Training.choosing_stage)
    await callback.answer()


@router.callback_query(Training.choosing_stage, F.data.startswith("stage:"))
async def choose_stage(callback: CallbackQuery, state: FSMContext):
    stage = callback.data.split(":")[1]
    await state.update_data(target_stage=stage)

    if stage == "greeting":
        await state.update_data(product=None)
        await callback.message.edit_text("Выберите когортную группу клиента:", reply_markup=_cohort_kb())
        await state.set_state(Training.choosing_cohort)
    else:
        stage_labels = {
            "needs": "Выявление потребности",
            "presentation": "Презентация продукта",
            "objections": "Отработка возражений",
            "closing": "Закрытие сделки",
        }
        await callback.message.edit_text(
            f"Этап: <b>{stage_labels.get(stage, stage)}</b>\n\nКакой продукт будете предлагать?",
            parse_mode="HTML",
            reply_markup=_product_kb(),
        )
        await state.set_state(Training.choosing_product)
    await callback.answer()


@router.callback_query(Training.choosing_product, F.data.startswith("product:"))
async def choose_product(callback: CallbackQuery, state: FSMContext):
    product = callback.data.split(":")[1]
    await state.update_data(product=product)
    await callback.message.edit_text("Выберите когортную группу клиента:", reply_markup=_cohort_kb())
    await state.set_state(Training.choosing_cohort)
    await callback.answer()


@router.callback_query(Training.choosing_cohort, F.data.startswith("cohort:"))
async def choose_cohort(callback: CallbackQuery, state: FSMContext):
    cohort = callback.data.split(":")[1]
    data = await state.get_data()

    profile = generate_client(cohort, data["scenario"])
    await state.update_data(cohort=cohort, client_profile=profile, messages=[])

    await upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    session_id = await create_session(
        user_id=callback.from_user.id,
        scenario=data["scenario"],
        mode=data["mode"],
        stage=data["target_stage"],
        product=data.get("product"),
        cohort=cohort,
        client_profile=profile,
    )
    await state.update_data(session_id=session_id)

    # Build profile card
    products_line = f"🏦 Продукты: {profile['products']}" if profile.get("products") else ""
    card = (
        f"👤 <b>Карточка клиента</b>\n\n"
        f"<b>{profile['name']}</b>, {profile['age']} лет\n"
        f"💰 На счёте/депозите: <b>{profile['balance']:,} руб.</b>\n"
        f"{products_line}\n\n"
        f"<i>{profile['appearance']}</i>\n"
        f"Настроение: {profile['mood']}\n\n"
        f"📋 Цель визита: {profile['purpose']}"
    ).replace(",", " ")  # thin non-breaking space for Russian number format

    # Properly format large numbers with spaces for Russian locale
    formatted_balance = f"{profile['balance']:,}".replace(",", " ")
    card = (
        f"👤 <b>Карточка клиента</b>\n\n"
        f"<b>{profile['name']}</b>, {profile['age']} лет\n"
        f"💰 На счёте/депозите: <b>{formatted_balance} руб.</b>\n"
        f"{products_line}\n\n"
        f"<i>{profile['appearance']}</i>\n"
        f"Настроение: {profile['mood']}\n\n"
        f"📋 Цель визита: {profile['purpose']}"
    )

    await callback.message.edit_text(f"{card}\n\n⏳ Генерирую клиента...", parse_mode="HTML")

    stage = data["target_stage"]
    product = data.get("product")

    try:
        opening = await get_opening_message(profile, stage, product)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка AI: {e}\n\nПроверьте ANTHROPIC_API_KEY в файле .env")
        return

    messages = [{"role": "client", "content": opening}]
    await state.update_data(messages=messages)
    await update_messages(session_id, messages)

    await callback.message.edit_text(card, parse_mode="HTML")
    await callback.message.answer(
        f"💬 <b>Клиент говорит:</b>\n\n<i>{opening}</i>\n\n"
        f"🎙 Запишите голосовое сообщение с вашим ответом:",
        parse_mode="HTML",
        reply_markup=_dialog_kb(),
    )
    await state.set_state(Training.in_dialog)
    await callback.answer()
