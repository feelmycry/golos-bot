from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS

CHANNEL_USERNAME = "@doiteasyeasydoit"
CHANNEL_URL = "https://t.me/doiteasyeasydoit"

_SUB_TEXT = (
    "🔒 <b>Для доступа к боту нужно подписаться на канал</b>\n\n"
    "1. Нажмите кнопку «Подписаться на канал»\n"
    "2. Подпишитесь\n"
    "3. Нажмите «Я подписался ✅»"
)


def _sub_kb():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL))
    kb.row(InlineKeyboardButton(text="Я подписался ✅", callback_data="check_sub"))
    return kb.as_markup()


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user
            if user and user.id not in ADMIN_IDS:
                bot = data["bot"]
                try:
                    member = await bot.get_chat_member(
                        chat_id=CHANNEL_USERNAME, user_id=user.id
                    )
                    is_member = member.status not in ("left", "kicked")
                except Exception:
                    is_member = True  # fail open if bot lacks admin rights

                if not is_member:
                    if isinstance(event, CallbackQuery):
                        if event.data == "check_sub":
                            await event.answer(
                                "❌ Вы ещё не подписались на канал. Подпишитесь и нажмите кнопку снова.",
                                show_alert=True,
                            )
                        else:
                            await event.answer()
                            try:
                                await event.message.edit_text(
                                    _SUB_TEXT,
                                    parse_mode="HTML",
                                    reply_markup=_sub_kb(),
                                )
                            except Exception:
                                await event.message.answer(
                                    _SUB_TEXT,
                                    parse_mode="HTML",
                                    reply_markup=_sub_kb(),
                                )
                    else:
                        await event.answer(
                            _SUB_TEXT, parse_mode="HTML", reply_markup=_sub_kb()
                        )
                    return

        return await handler(event, data)
