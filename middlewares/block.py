from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import ADMIN_IDS
from services.db import is_user_blocked

_BLOCKED_TEXT = "🚫 Вы заблокированы и не можете использовать этого бота."


class BlockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user
            if user and user.id not in ADMIN_IDS:
                if await is_user_blocked(user.id):
                    if isinstance(event, Message):
                        await event.answer(_BLOCKED_TEXT)
                    else:
                        await event.answer(_BLOCKED_TEXT, show_alert=True)
                    return  # Drop the event
        return await handler(event, data)
