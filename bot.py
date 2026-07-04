import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import TELEGRAM_TOKEN, REDIS_URL
from handlers import start, setup, dialog, news_analysis, briefing, admin, stocks, learning, game
from handlers.game import streak_reminder_task
from middlewares.block import BlockMiddleware
from middlewares.subscription import SubscriptionMiddleware
from services.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _build_storage():
    if REDIS_URL:
        try:
            from redis.asyncio import Redis
            from aiogram.fsm.storage.redis import RedisStorage
            redis = Redis.from_url(REDIS_URL, decode_responses=False)
            logging.info("FSM storage: Redis (%s)", REDIS_URL.split("@")[-1])
            return RedisStorage(redis=redis)
        except Exception as e:
            logging.warning("Redis unavailable (%s), falling back to MemoryStorage", e)
    logging.info("FSM storage: MemoryStorage (state lost on restart)")
    return MemoryStorage()


async def main():
    await init_db()

    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher(storage=_build_storage())
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

    asyncio.create_task(streak_reminder_task(bot))

    port = int(os.getenv("PORT", 0))
    if port:
        import uvicorn
        from api.server import app as api_app
        config = uvicorn.Config(api_app, host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        logging.info("API server started on port %d", port)

    logging.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
