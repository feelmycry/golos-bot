import uuid

TOKEN_TTL = 3600  # 1 час


async def create_token(user_id: int) -> str | None:
    from services.redis_client import get_redis
    redis = await get_redis()
    if not redis:
        return None
    token = str(uuid.uuid4())
    await redis.setex(f"miniapp_token:{token}", TOKEN_TTL, str(user_id))
    return token


async def validate_token(token: str) -> int | None:
    if not token:
        return None
    from services.redis_client import get_redis
    redis = await get_redis()
    if not redis:
        return None
    uid = await redis.get(f"miniapp_token:{token}")
    return int(uid) if uid else None
