import hmac
import hashlib
import time

_SECRET = None


def _secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        from config import TELEGRAM_TOKEN
        _SECRET = (TELEGRAM_TOKEN or "fallback").encode()
    return _SECRET


def create_token(user_id: int) -> str:
    ts = int(time.time())
    data = f"{user_id}:{ts}"
    sig = hmac.new(_secret(), data.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{user_id}.{ts}.{sig}"


def validate_token(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        user_id_s, ts_s, sig = parts
        ts = int(ts_s)
        if abs(time.time() - ts) > 3600:
            return None
        data = f"{user_id_s}:{ts_s}"
        expected = hmac.new(_secret(), data.encode(), hashlib.sha256).hexdigest()[:24]
        if hmac.compare_digest(sig, expected):
            return int(user_id_s)
    except Exception:
        pass
    return None
