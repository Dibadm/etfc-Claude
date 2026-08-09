import time

import pytest

from app.telegram_auth import InvalidInitDataError, parse_and_validate
from tests.telegram_test_utils import make_init_data as _make_init_data

BOT_TOKEN = "123456:FAKE-TEST-TOKEN-not-real"


def make_init_data(bot_token: str = BOT_TOKEN, **kwargs):
    return _make_init_data(bot_token, **kwargs)


def test_valid_init_data_is_accepted():
    init_data = make_init_data()
    user = parse_and_validate(init_data, BOT_TOKEN)
    assert user.telegram_id == "987654321"
    assert user.username == "test_bettor"


def test_wrong_bot_token_is_rejected():
    init_data = make_init_data(bot_token=BOT_TOKEN)
    with pytest.raises(InvalidInitDataError, match="signature"):
        parse_and_validate(init_data, "999999:A-DIFFERENT-TOKEN")


def test_tampered_data_after_signing_is_rejected():
    init_data = make_init_data(tamper=True)
    with pytest.raises(InvalidInitDataError, match="signature"):
        parse_and_validate(init_data, BOT_TOKEN)


def test_missing_hash_is_rejected():
    init_data = make_init_data(omit_hash=True)
    with pytest.raises(InvalidInitDataError, match="hash"):
        parse_and_validate(init_data, BOT_TOKEN)


def test_stale_auth_date_is_rejected_as_replay():
    week_old = int(time.time()) - (7 * 24 * 3600)
    init_data = make_init_data(auth_date=week_old)
    with pytest.raises(InvalidInitDataError, match="replayed"):
        parse_and_validate(init_data, BOT_TOKEN)


def test_auth_date_far_in_future_is_rejected():
    future = int(time.time()) + 3600
    init_data = make_init_data(auth_date=future)
    with pytest.raises(InvalidInitDataError, match="future"):
        parse_and_validate(init_data, BOT_TOKEN)


def test_empty_init_data_is_rejected():
    with pytest.raises(InvalidInitDataError, match="Missing"):
        parse_and_validate("", BOT_TOKEN)


def test_malformed_user_field_is_rejected():
    init_data = _make_init_data(BOT_TOKEN, user_field_override="not-json")
    with pytest.raises(InvalidInitDataError, match="malformed"):
        parse_and_validate(init_data, BOT_TOKEN)


def test_recent_auth_date_within_window_accepted():
    ten_min_ago = int(time.time()) - 600
    init_data = make_init_data(auth_date=ten_min_ago)
    user = parse_and_validate(init_data, BOT_TOKEN)
    assert user.telegram_id == "987654321"
