from config import REDIS_URL

_redis = None


async def get_redis():
    global _redis
    if _redis is None and REDIS_URL:
        from redis.asyncio import Redis
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis
