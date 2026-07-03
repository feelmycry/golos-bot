import os
from fastapi import HTTPException, Request
from config import TELEGRAM_TOKEN
from api.auth import validate_init_data

DEV_USER_ID = int(os.getenv("DEV_USER_ID", "0"))


async def get_current_user(request: Request) -> int:
    if DEV_USER_ID:
        return DEV_USER_ID
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data")
    try:
        user_data = validate_init_data(init_data, TELEGRAM_TOKEN)
        return int(user_data["id"])
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid init data")
