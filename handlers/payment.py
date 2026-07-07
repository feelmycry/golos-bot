from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, PreCheckoutQuery, LabeledPrice,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, PAYMENTS_TOKEN
from services.subscription import grant_subscription, PLANS, grant_product_access, PRODUCT_PLANS

router = Router()

_PRODUCT_INVOICES = {
    "learning_basic": {
        "title": "Обучение — Базовый уровень",
        "description": "Полный доступ ко всем урокам базового уровня: уроки 7–17, тесты, XP.",
        "amount": 20000,
        "label": "Базовый уровень — 200 ₽",
        "product": "learning_basic",
    },
    "stocks_monthly": {
        "title": "Анализ акций — 1 месяц",
        "description": "Полный доступ к анализу акций на 1 месяц: мультипликаторы, дивиденды, AI анализ, отчётность.",
        "amount": 140000,
        "label": "Анализ акций — 1 400 ₽ / мес",
        "product": "stocks",
    },
}

_INVOICES = {
    "half_year": {
        "title": "Тренажёр продаж — 6 месяцев",
        "description": (
            "Полный доступ на 6 месяцев: неограниченные тренировки с AI-клиентом, "
            "все продукты и сценарии, анализ речи и обратная связь тренера."
        ),
        "amount": 139000,
        "label": "6 месяцев — 1 390 ₽",
    },
    "year": {
        "title": "Тренажёр продаж — 12 месяцев",
        "description": (
            "Полный доступ на 12 месяцев: неограниченные тренировки с AI-клиентом, "
            "все продукты и сценарии, анализ речи и обратная связь тренера."
        ),
        "amount": 179000,
        "label": "12 месяцев — 1 790 ₽",
    },
}


def _paywall_kb():
    b = InlineKeyboardBuilder()
    b.button(text="💳 6 месяцев — 1 390 ₽", callback_data="pay:half_year")
    b.button(text="🏆 12 месяцев — 1 790 ₽", callback_data="pay:year")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


async def show_paywall(message: Message) -> None:
    text = (
        "🔒 <b>Пробная тренировка завершена</b>\n\n"
        "Вы провели первый диалог с AI-клиентом — отличный старт! 💪\n\n"
        "Чтобы продолжить тренировки без ограничений, выберите тариф:\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>6 месяцев</b> — 1 390 ₽\n"
        "🏆 <b>12 месяцев</b> — 1 790 ₽  <i>(выгоднее)</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Полный доступ включает:\n"
        "✅ Неограниченные тренировки с AI-клиентом\n"
        "✅ Все продукты и сценарии продаж\n"
        "✅ Анализ речи и обратная связь тренера\n"
        "✅ Курс по инвестиционным продуктам"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=_paywall_kb())


async def show_learning_paywall(callback: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Открыть доступ — 200 ₽", callback_data="pay_prod:learning_basic")
    b.button(text="◀️ Назад к урокам", callback_data="learn:mod:m1")
    b.adjust(1)
    text = (
        "🔒 <b>Уроки 7–17 — платный доступ</b>\n\n"
        "Вы прошли бесплатную часть базового курса.\n\n"
        "Открытие оставшихся 11 уроков:\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📚 <b>Базовый уровень</b> — 200 ₽  <i>(навсегда)</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Включает:\n"
        "✅ Уроки 7–17 базового уровня\n"
        "✅ Тесты с разбором ошибок\n"
        "✅ XP и прогресс"
    )
    await callback.answer()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())


async def show_stocks_paywall(callback: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.button(text="💳 1 месяц — 1 400 ₽", callback_data="pay_prod:stocks_monthly")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    text = (
        "🔒 <b>Полный анализ акций — подписка</b>\n\n"
        "Базовые данные о компании доступны бесплатно.\n\n"
        "Для глубокого анализа подключите подписку:\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📈 <b>1 месяц</b> — 1 400 ₽\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Включает:\n"
        "✅ Мультипликаторы и финансы\n"
        "✅ История дивидендов и прогнозы\n"
        "✅ Стакан заявок\n"
        "✅ Скачивание отчётности\n"
        "✅ AI анализ компании"
    )
    await callback.answer()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("pay_prod:"))
async def handle_pay_product(callback: CallbackQuery):
    plan = callback.data[len("pay_prod:"):]
    if plan not in _PRODUCT_INVOICES:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    if not PAYMENTS_TOKEN:
        await callback.answer(
            "Оплата подключается. Следите за обновлениями в @doiteasyeasydoit",
            show_alert=True,
        )
        return

    inv = _PRODUCT_INVOICES[plan]
    await callback.answer()
    await callback.message.answer_invoice(
        title=inv["title"],
        description=inv["description"],
        payload=f"prod_{plan}_{callback.from_user.id}",
        provider_token=PAYMENTS_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=inv["label"], amount=inv["amount"])],
        start_parameter=f"prod_{plan}",
    )


@router.callback_query(F.data.startswith("pay:"))
async def handle_pay(callback: CallbackQuery):
    plan = callback.data[4:]
    if plan not in _INVOICES:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    if not PAYMENTS_TOKEN:
        await callback.answer(
            "Оплата подключается. Следите за обновлениями в @doiteasyeasydoit",
            show_alert=True,
        )
        return

    inv = _INVOICES[plan]
    await callback.answer()
    await callback.message.answer_invoice(
        title=inv["title"],
        description=inv["description"],
        payload=f"sub_{plan}_{callback.from_user.id}",
        provider_token=PAYMENTS_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=inv["label"], amount=inv["amount"])],
        start_parameter=f"sub_{plan}",
    )


@router.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    payment_id = message.successful_payment.telegram_payment_charge_id
    # payload: "sub_{plan}_{user_id}" or "prod_{plan}_{user_id}"
    parts = payload.split("_")
    kind = parts[0]  # "sub" or "prod"
    plan = "_".join(parts[1:-1])  # handles underscores in plan names

    from handlers.start import _main_kb
    from services.miniapp_auth import create_token
    token = create_token(message.from_user.id)

    if kind == "prod":
        product_map = {"learning_basic": "learning_basic", "stocks_monthly": "stocks"}
        product = product_map.get(plan, plan)
        paid_until = await grant_product_access(message.from_user.id, product, plan, payment_id)
        prod_labels = {"learning_basic": "Базовый уровень обучения", "stocks_monthly": "Анализ акций (1 мес)"}
        await message.answer(
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Доступ: <b>{prod_labels.get(plan, plan)}</b>\n"
            f"Активен до: <b>{paid_until.strftime('%d.%m.%Y')}</b>\n\n"
            f"Приятного обучения! 🚀",
            parse_mode="HTML",
            reply_markup=_main_kb(message.from_user.id, token),
        )
    else:
        paid_until = await grant_subscription(message.from_user.id, plan, payment_id)
        plan_labels = {"half_year": "6 месяцев", "year": "12 месяцев"}
        await message.answer(
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Тариф: <b>{plan_labels.get(plan, plan)}</b>\n"
            f"Доступ активен до: <b>{paid_until.strftime('%d.%m.%Y')}</b>\n\n"
            f"Тренируйтесь без ограничений! 💪",
            parse_mode="HTML",
            reply_markup=_main_kb(message.from_user.id, token),
        )
