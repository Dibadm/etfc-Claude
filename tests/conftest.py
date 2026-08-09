import os
import tempfile

import pytest

# Must happen before any `app.*` module is imported, since app.config's
# get_settings() is lru_cache'd at first import.
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["ETFC_DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"
os.environ["ETFC_WAGERING_ENABLED"] = "false"
os.environ["ETFC_TELEGRAM_BOT_TOKEN"] = "123456:TEST-ONLY-TOKEN-not-a-real-bot"
os.environ["ETFC_ADMIN_TOKEN"] = "test-admin-token-not-real"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import Base, engine  # noqa: E402
from tests.telegram_test_utils import make_init_data  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    """Fresh tables for every test — cheap on SQLite, keeps tests independent."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Rate limiters (app/admin_auth.py, app/main.py) are process-local,
    module-level state — without resetting them, tests that intentionally
    trigger rate limits would leave hits behind for the next test, and
    the global per-IP limiter would eventually start rejecting unrelated
    later tests that happen to share TestClient's default IP."""
    from app.admin_auth import _admin_auth_failures
    from app.main import _bet_limiter, _deposit_limiter, _global_ip_limiter

    for limiter in (_admin_auth_failures, _bet_limiter, _deposit_limiter, _global_ip_limiter):
        limiter._hits.clear()
    yield
    for limiter in (_admin_auth_failures, _bet_limiter, _deposit_limiter, _global_ip_limiter):
        limiter._hits.clear()


@pytest.fixture
def client():
    # Admin token set as a default header so the ~15 existing call sites
    # that create fights/markets/settle/void don't all need editing now
    # that those endpoints require auth — tests specifically checking
    # admin-auth rejection build their own TestClient() without this.
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {os.environ['ETFC_ADMIN_TOKEN']}"})
    return c


@pytest.fixture
def live_wagering(monkeypatch):
    """Flips ETFC_WAGERING_ENABLED on for one test — most tests run in demo
    mode (see the module-level env var above); real-money-only code paths
    (deposits, withdrawals) need this to even attempt the operation."""
    from app.config import get_settings

    monkeypatch.setenv("ETFC_WAGERING_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("ETFC_WAGERING_ENABLED", "false")
    get_settings.cache_clear()


def make_fighter(client, name):
    r = client.post("/fighters", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def make_user(client, telegram_id):
    r = client.post("/users", json={"telegram_id": telegram_id, "username": telegram_id})
    assert r.status_code == 200, r.text
    return r.json()


def telegram_auth_headers(telegram_id: str, username: str | None = None) -> dict:
    """Builds a real, validly-signed X-Telegram-Init-Data header for the
    given telegram user, using the same test bot token configured above —
    so /miniapp/* tests exercise the real signature-checking code path.
    telegram_id should be a numeric string, matching real Telegram user ids."""
    init_data = make_init_data(
        bot_token=os.environ["ETFC_TELEGRAM_BOT_TOKEN"],
        user={"id": int(telegram_id), "username": username or f"user{telegram_id}"},
    )
    return {"X-Telegram-Init-Data": init_data}
