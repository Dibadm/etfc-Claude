"""Shared helper for building realistically-signed Telegram initData
strings in tests. Not part of the app itself — test infrastructure only."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode


def make_init_data(bot_token: str, *, user=None, auth_date=None, tamper=False, omit_hash=False, user_field_override=None) -> str:
    if user is None:
        user = {"id": 987654321, "username": "test_bettor", "first_name": "Test"}
    if auth_date is None:
        auth_date = int(time.time())

    pairs = {
        "user": user_field_override if user_field_override is not None else json.dumps(user, separators=(",", ":")),
        "auth_date": str(auth_date),
        "query_id": "AAF1234567890",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if tamper:
        pairs["auth_date"] = str(int(pairs["auth_date"]) + 999999)  # change data after signing

    if not omit_hash:
        pairs["hash"] = computed_hash

    return urlencode(pairs)
