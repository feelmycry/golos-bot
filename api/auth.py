import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Validates Telegram WebApp initData. Returns user dict or raises ValueError."""
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_received = params.pop("hash", "")
    if not hash_received:
        raise ValueError("Missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(hash_computed, hash_received):
        raise ValueError("Invalid hash")

    return json.loads(params.get("user", "{}"))
