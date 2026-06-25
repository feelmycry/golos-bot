import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import TELEGRAM_TOKEN
from handlers import start, setup, dialog, news_analysis, briefing, admin, stocks, learning, game
from middlewares.block import BlockMiddleware
from middlewares.subscription import SubscriptionMiddleware
from services.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main():
    await init_db()

    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(BlockMiddleware())
    dp.callback_query.middleware(BlockMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    dp.include_router(start.router)
    dp.include_router(setup.router)
    dp.include_router(dialog.router)
    dp.include_router(news_analysis.router)
    dp.include_router(briefing.router)
    dp.include_router(admin.router)
    dp.include_router(stocks.router)
    dp.include_router(learning.router)
    dp.include_router(game.router)

    logging.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
