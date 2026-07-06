from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message, PreCheckoutQuery, LabeledPrice,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, PAYMENTS_TOKEN
from services.subscription import grant_subscription, PLANS

router = Router()

_INVOICES = {
    "quarter": {
        "title": "Тренажёр продаж — 3 месяца",
        "description": (
            "Полный доступ на 3 месяца: неограниченные тренировки с AI-клиентом, "
            "все продукты и сценарии, анализ речи и обратная связь тренера."
        ),
        "amount": 110000,
        "label": "3 месяца — 1 100 ₽",
    },
    "year": {
        "title": "Тренажёр продаж — 1 год",
        "description": (
            "Полный доступ на год: неограниченные тренировки с AI-клиентом, "
            "все продукты и сценарии, анализ речи и обратная связь тренера."
        ),
        "amount": 144900,
        "label": "1 год — 1 449 ₽",
    },
}


def _paywall_kb():
    b = InlineKeyboardBuilder()
    b.button(text="💳 Оплатить 1 100 ₽ / 3 мес", callback_data="pay:quarter")
    b.button(text="🏆 Оплатить 1 449 ₽ / год", callback_data="pay:year")
    b.button(text="◀️ Главное меню", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


async def show_paywall(message: Message) -> None:
    text = (
        "🔒 <b>Пробная тренировка завершена</b>\n\n"
        "Вы провели первый диалог с AI-клиентом — отличный старт! 💪\n\n"
        "Чтобы продолжить тренировки без ограничений, выберите тариф:\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>3 месяца</b> — 1 100 ₽\n"
        "🏆 <b>Год</b> — 1 449 ₽  <i>(экономия 950 ₽)</i>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Полный доступ включает:\n"
        "✅ Неограниченные тренировки с AI-клиентом\n"
        "✅ Все продукты и сценарии продаж\n"
        "✅ Анализ речи и обратная связь тренера\n"
        "✅ Курс по инвестиционным продуктам"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=_paywall_kb())


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
    # payload: "sub_{plan}_{user_id}"
    parts = payload.split("_")
    plan = parts[1] if len(parts) >= 3 else "quarter"
    payment_id = message.successful_payment.telegram_payment_charge_id

    paid_until = await grant_subscription(message.from_user.id, plan, payment_id)
    plan_labels = {"quarter": "3 месяца", "year": "1 год"}

    from handlers.start import _main_kb
    from services.miniapp_auth import create_token
    token = create_token(message.from_user.id)

    await message.answer(
        f"🎉 <b>Оплата прошла успешно!</b>\n\n"
        f"Тариф: <b>{plan_labels.get(plan, plan)}</b>\n"
        f"Доступ активен до: <b>{paid_until.strftime('%d.%m.%Y')}</b>\n\n"
        f"Тренируйтесь без ограничений! 💪",
        parse_mode="HTML",
        reply_markup=_main_kb(message.from_user.id, token),
    )
