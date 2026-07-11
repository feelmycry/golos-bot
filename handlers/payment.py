from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, PreCheckoutQuery, LabeledPrice,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, PAYMENTS_TOKEN
from services.subscription import (
    grant_subscription, PLANS, grant_product_access, PRODUCT_PLANS,
    has_any_discount, use_any_discount,
)

router = Router()

_PRODUCT_INVOICES = {
    "learning_basic": {
        "title": "Обучение — Базовый уровень",
        "description": "Полный доступ ко всем урокам базового уровня: уроки 7–17, тесты, XP.",
        "amount": 20000,
        "label": "Базовый уровень — 200 ₽",
        "product": "learning_basic",
    },
    "learning_medium": {
        "title": "Обучение — Средний уровень",
        "description": "Полный доступ ко всем 18 урокам среднего уровня: фундаментальный анализ, мультипликаторы, отчётность, тесты, XP.",
        "amount": 20000,
        "label": "Средний уровень — 200 ₽",
        "product": "learning_medium",
    },
    "learning_pro": {
        "title": "Обучение — Профессиональный уровень",
        "description": "Полный доступ ко всем 20 урокам профессионального уровня: DCF, деривативы, M&A, VaR, тесты, XP.",
        "amount": 30000,
        "label": "Профессиональный уровень — 300 ₽",
        "product": "learning_pro",
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


def _disc(amount: int) -> int:
    return round(amount * 0.9)


async def _show_pay_menu(message, user_id: int, edit: bool = False) -> None:
    has_disc = await has_any_discount(user_id)
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Тренировка — 6 мес (1 390 ₽)", callback_data="pay:half_year")
    b.button(text="🏆 Тренировка — 12 мес (1 790 ₽)", callback_data="pay:year")
    b.button(text="📘 Базовый уровень обучения — 200 ₽", callback_data="pay_prod:learning_basic")
    b.button(text="📗 Средний уровень обучения — 200 ₽", callback_data="pay_prod:learning_medium")
    b.button(text="📙 Профессиональный уровень — 300 ₽", callback_data="pay_prod:learning_pro")
    b.button(text="📈 Анализ акций — 1 мес (1 400 ₽)", callback_data="pay_prod:stocks_monthly")
    if has_disc:
        b.button(text="🎁 Скидка 10% доступна! Применить", callback_data="pay:discount_menu")
    b.button(text="🤝 Приведи друга и -10% к цене", callback_data="pay:referral")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    text = (
        "💳 <b>Оплата</b>\n\n"
        "Выберите, что хотите оплатить:\n\n"
        "━━━ 🎯 Тренировка ━━━\n"
        "📅 <b>6 месяцев</b> — 1 390 ₽\n"
        "🏆 <b>12 месяцев</b> — 1 790 ₽\n\n"
        "━━━ 📚 Обучение ━━━\n"
        "📘 <b>Базовый уровень</b> — 200 ₽\n"
        "📗 <b>Средний уровень</b> — 200 ₽\n"
        "📙 <b>Профессиональный уровень</b> — 300 ₽\n\n"
        "━━━ 📈 Анализ ━━━\n"
        "📊 <b>Анализ акций</b> — 1 400 ₽ / мес"
    )
    if has_disc:
        text += "\n\n🎁 <b>У вас есть скидка 10%!</b> Нажмите кнопку ниже чтобы применить."
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "pay:menu")
async def show_pay_menu_cb(callback: CallbackQuery):
    await callback.answer()
    await _show_pay_menu(callback.message, callback.from_user.id, edit=True)


@router.callback_query(F.data == "pay:referral")
async def show_referral(callback: CallbackQuery):
    await callback.answer()
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад к оплате", callback_data="pay:menu")
    b.adjust(1)
    text = (
        "🤝 <b>Приведи друга и получи скидку -10%</b>\n\n"
        "Поделитесь вашей персональной ссылкой с другом:\n\n"
        f"<code>{ref_link}</code>\n\n"
        "Когда друг зайдёт в бот по этой ссылке, он получит возможность "
        "оплатить <b>любой один модуль со скидкой 10%</b>.\n\n"
        "Скидка применяется один раз на один модуль по выбору друга."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "pay:discount_menu")
async def show_discount_menu(callback: CallbackQuery):
    if not await has_any_discount(callback.from_user.id):
        await callback.answer("Скидка уже использована или недоступна.", show_alert=True)
        return
    await callback.answer()
    b = InlineKeyboardBuilder()
    b.button(text=f"🎯 Тренировка 6 мес — 1 251 ₽ (-10%)", callback_data="pay:disc:half_year")
    b.button(text=f"🏆 Тренировка 12 мес — 1 611 ₽ (-10%)", callback_data="pay:disc:year")
    b.button(text=f"📘 Базовый уровень — 180 ₽ (-10%)", callback_data="pay_prod_disc:learning_basic")
    b.button(text=f"📗 Средний уровень — 180 ₽ (-10%)", callback_data="pay_prod_disc:learning_medium")
    b.button(text=f"📙 Проф. уровень — 270 ₽ (-10%)", callback_data="pay_prod_disc:learning_pro")
    b.button(text=f"📈 Анализ акций — 1 260 ₽ (-10%)", callback_data="pay_prod_disc:stocks_monthly")
    b.button(text="◀️ Назад", callback_data="pay:menu")
    b.adjust(1)
    await callback.message.edit_text(
        "🎁 <b>Скидка 10% — выберите модуль</b>\n\n"
        "Скидка применяется <b>один раз</b> на любой модуль по вашему выбору:",
        parse_mode="HTML",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("pay:disc:"))
async def handle_pay_discounted(callback: CallbackQuery):
    plan = callback.data[len("pay:disc:"):]
    if plan not in _INVOICES:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    if not await has_any_discount(callback.from_user.id):
        await callback.answer("Скидка уже использована.", show_alert=True)
        return
    if not PAYMENTS_TOKEN:
        await callback.answer("Оплата подключается. Следите за обновлениями в @doiteasyeasydoit", show_alert=True)
        return
    inv = _INVOICES[plan]
    await callback.answer()
    await callback.message.answer_invoice(
        title=inv["title"] + " (скидка 10%)",
        description=inv["description"],
        payload=f"subd_{plan}_{callback.from_user.id}",
        provider_token=PAYMENTS_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=inv["label"] + " −10%", amount=_disc(inv["amount"]))],
        start_parameter=f"subd_{plan}",
    )


@router.callback_query(F.data.startswith("pay_prod_disc:"))
async def handle_pay_product_discounted(callback: CallbackQuery):
    plan = callback.data[len("pay_prod_disc:"):]
    if plan not in _PRODUCT_INVOICES:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return
    if not await has_any_discount(callback.from_user.id):
        await callback.answer("Скидка уже использована.", show_alert=True)
        return
    if not PAYMENTS_TOKEN:
        await callback.answer("Оплата подключается. Следите за обновлениями в @doiteasyeasydoit", show_alert=True)
        return
    inv = _PRODUCT_INVOICES[plan]
    await callback.answer()
    await callback.message.answer_invoice(
        title=inv["title"] + " (скидка 10%)",
        description=inv["description"],
        payload=f"prodd_{plan}_{callback.from_user.id}",
        provider_token=PAYMENTS_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=inv["label"] + " −10%", amount=_disc(inv["amount"]))],
        start_parameter=f"prodd_{plan}",
    )


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
        "🏆 <b>12 месяцев</b> — 1 790 ₽  <i>(экономия 990 руб)</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Полный доступ включает:\n"
        "✅ Неограниченные тренировки с AI-клиентом\n"
        "✅ Все продукты и сценарии продаж\n"
        "✅ Анализ речи и обратная связь тренера"
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


async def show_learning_medium_paywall(callback: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Открыть доступ — 200 ₽", callback_data="pay_prod:learning_medium")
    b.button(text="◀️ Назад к уровням", callback_data="learning:menu")
    b.adjust(1)
    text = (
        "🔒 <b>Средний уровень — платный доступ</b>\n\n"
        "18 уроков по фундаментальному анализу, мультипликаторам, финансовой отчётности и портфельным стратегиям.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Средний уровень</b> — 200 ₽  <i>(навсегда)</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Включает:\n"
        "✅ 18 уроков среднего уровня\n"
        "✅ Тесты с разбором ошибок\n"
        "✅ XP и прогресс"
    )
    await callback.answer()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())


async def show_learning_pro_paywall(callback: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Открыть доступ — 300 ₽", callback_data="pay_prod:learning_pro")
    b.button(text="◀️ Назад к уровням", callback_data="learning:menu")
    b.adjust(1)
    text = (
        "🔒 <b>Профессиональный уровень — платный доступ</b>\n\n"
        "20 уроков по DCF-моделям, деривативам, M&amp;A, управлению рисками и работе с HNWI-клиентами.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>Профессиональный уровень</b> — 300 ₽  <i>(навсегда)</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Включает:\n"
        "✅ 20 уроков профессионального уровня\n"
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
    # payload formats:
    #   sub_{plan}_{user_id}   — regular subscription
    #   subd_{plan}_{user_id}  — discounted subscription
    #   prod_{plan}_{user_id}  — regular product
    #   prodd_{plan}_{user_id} — discounted product
    parts = payload.split("_")
    kind = parts[0]  # "sub", "subd", "prod", "prodd"
    is_discounted = kind.endswith("d") and kind != "prod"
    base_kind = "sub" if kind.startswith("sub") else "prod"
    plan = "_".join(parts[1:-1])

    from handlers.start import _main_kb
    from services.miniapp_auth import create_token
    token = create_token(message.from_user.id)

    if is_discounted:
        await use_any_discount(message.from_user.id, f"{base_kind}_{plan}")

    if base_kind == "prod":
        product_map = {
            "learning_basic": "learning_basic",
            "learning_medium": "learning_medium",
            "learning_pro": "learning_pro",
            "stocks_monthly": "stocks",
        }
        product = product_map.get(plan, plan)
        paid_until = await grant_product_access(message.from_user.id, product, plan, payment_id)
        prod_labels = {
            "learning_basic": "Базовый уровень обучения",
            "learning_medium": "Средний уровень обучения",
            "learning_pro": "Профессиональный уровень обучения",
            "stocks_monthly": "Анализ акций (1 мес)",
        }
        disc_note = " (со скидкой 10% 🎁)" if is_discounted else ""
        await message.answer(
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Доступ: <b>{prod_labels.get(plan, plan)}</b>{disc_note}\n"
            f"Активен до: <b>{paid_until.strftime('%d.%m.%Y')}</b>\n\n"
            f"Приятного обучения! 🚀",
            parse_mode="HTML",
            reply_markup=_main_kb(message.from_user.id, token),
        )
    else:
        paid_until = await grant_subscription(message.from_user.id, plan, payment_id)
        plan_labels = {"half_year": "6 месяцев", "year": "12 месяцев"}
        disc_note = " (со скидкой 10% 🎁)" if is_discounted else ""
        await message.answer(
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Тариф: <b>{plan_labels.get(plan, plan)}</b>{disc_note}\n"
            f"Доступ активен до: <b>{paid_until.strftime('%d.%m.%Y')}</b>\n\n"
            f"Тренируйтесь без ограничений! 💪",
            parse_mode="HTML",
            reply_markup=_main_kb(message.from_user.id, token),
        )
