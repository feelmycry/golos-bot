import logging
import os
from fastapi import HTTPException, Request
from config import TELEGRAM_TOKEN, ADMIN_IDS
from api.auth import validate_init_data

log = logging.getLogger(__name__)
DEV_USER_ID = int(os.getenv("DEV_USER_ID", "0"))


async def get_current_user(request: Request) -> int:
    if DEV_USER_ID:
        return DEV_USER_ID

    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        try:
            user_data = validate_init_data(init_data, TELEGRAM_TOKEN)
            return int(user_data["id"])
        except (ValueError, KeyError) as e:
            log.warning("initData validation failed: %s", e)

    # Fallback: trust X-Telegram-User-Id only for known admin IDs
    fallback_id = int(request.headers.get("X-Telegram-User-Id", "0") or "0")
    if fallback_id and fallback_id in ADMIN_IDS:
        log.info("Auth via fallback user ID %d (admin)", fallback_id)
        return fallback_id

    raise HTTPException(status_code=401, detail="Unauthorized")
