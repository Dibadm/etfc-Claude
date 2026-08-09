"""
Validates Telegram Mini App `initData` per Telegram's documented algorithm:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Why this exists: the Mini App frontend can't be trusted to say "I am user X" —
anyone can open browser devtools and change a user_id in a request body. Telegram
signs the data it hands to the Mini App with the bot token, so the backend can
verify a request really came from Telegram, for the Telegram user it claims to
be, and wasn't replayed from days ago. This is what every /miniapp/* endpoint
relies on for "who is making this request" — the Phase 1 endpoints that take a
raw user_id in the body are left alone for internal/admin testing.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.config import get_settings


class InvalidInitDataError(Exception):
    pass


@dataclass
class TelegramUser:
    telegram_id: str
    username: str | None
    first_name: str | None


def _compute_hash(data_check_string: str, bot_token: str) -> str:
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def parse_and_validate(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> TelegramUser:
    """Raises InvalidInitDataError on any failure — bad signature, missing
    fields, or stale auth_date (replay of an old initData string)."""
    if not init_data:
        raise InvalidInitDataError("Missing initData")

    pairs = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InvalidInitDataError("initData has no hash field")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    expected_hash = _compute_hash(data_check_string, bot_token)

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InvalidInitDataError("initData signature does not match — not from Telegram")

    auth_date = pairs.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        raise InvalidInitDataError("initData missing/invalid auth_date")
    age = time.time() - int(auth_date)
    if age > max_age_seconds:
        raise InvalidInitDataError(f"initData is {int(age)}s old — likely replayed, rejecting")
    if age < -60:  # allow small clock skew
        raise InvalidInitDataError("initData auth_date is in the future")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InvalidInitDataError("initData missing user field")
    try:
        user_json = json.loads(user_raw)
        telegram_id = str(user_json["id"])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise InvalidInitDataError(f"initData user field is malformed: {e}")

    return TelegramUser(
        telegram_id=telegram_id,
        username=user_json.get("username"),
        first_name=user_json.get("first_name"),
    )


def get_telegram_user(x_telegram_init_data: str = Header(...)) -> TelegramUser:
    """FastAPI dependency — the Mini App frontend sends the raw initData
    string (from window.Telegram.WebApp.initData) in this header on every
    request. Raises 401 on anything invalid."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        # Fails closed: refuse to fake-authenticate if the token isn't
        # configured, rather than silently trusting unsigned data.
        raise HTTPException(500, "Server is missing ETFC_TELEGRAM_BOT_TOKEN — cannot validate Telegram auth")
    try:
        return parse_and_validate(x_telegram_init_data, settings.telegram_bot_token)
    except InvalidInitDataError as e:
        raise HTTPException(401, str(e))
