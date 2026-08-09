"""
Central configuration for the ETFC betting engine.

WAGERING_ENABLED is the "flip the switch once licensed" control described
in the build plan. It does NOT gate the betting logic itself — markets,
odds, bet placement, and settlement all run identically whether it's on
or off. What it gates is REAL MONEY MOVEMENT:

  - When False (default): deposits/withdrawals of real funds are rejected.
    New users are seeded with a demo balance (DEMO_SEED_BALANCE) so the
    full product — the exact code that will run in production — can be
    demoed to ETFC and the Ethiopian Lottery Service end-to-end.
  - When True: real Telebirr deposits/withdrawals are allowed and the
    demo-seeding behavior stops applying to new users.

This means there is no separate "demo build" to maintain — flipping on
is a config change (env var / DB row), not a code change or redeploy of
different logic.
"""
from decimal import Decimal
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ETFC Betting Engine"

    # The master switch. Keep this False until the Lottery Service
    # licensing approval is actually in hand.
    wagering_enabled: bool = False

    # Balance new users get seeded with while wagering_enabled is False,
    # so the product can be fully demoed with play money.
    demo_seed_balance: Decimal = Decimal("1000.00")

    currency: str = "ETB"

    # House cut taken on settled winning bets, as a fraction (0.20 = 20%),
    # mirrors the split-pot structure already used in Habesha Bet.
    # NOTE: for a fixed-odds sportsbook the "edge" normally lives inside
    # the odds themselves (overround), not as a cut of winnings. Default
    # to 0.0 here — see odds_service docstring — and only set this above
    # zero if you deliberately want an *additional* rake on top of odds.
    house_cut_fraction: Decimal = Decimal("0.00")

    database_url: str = "sqlite:///./etfc_betting.db"

    # Required for the Mini App's Telegram-authenticated endpoints
    # (see app/telegram_auth.py) — the bot token from @BotFather. Also
    # used by bot.py to run the Telegram bot itself.
    telegram_bot_token: str = ""

    # Where the React Mini App is hosted (must be https:// in production —
    # Telegram requires TLS for WebApp URLs). Used by bot.py to build the
    # "Open App" launch button.
    mini_app_url: str = "https://example.com/miniapp"

    # Origins allowed to call this API from a browser (the Mini App's
    # deployed URL, plus localhost for dev). Comma-separated via env var,
    # e.g. ETFC_CORS_ALLOW_ORIGINS="https://your-miniapp.pages.dev,http://localhost:5173"
    cors_allow_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # Bearer token gating every admin-only endpoint (creating fights/
    # markets, adjusting odds, suspending markets, settling/voiding
    # fights, viewing liability). Deliberately has no usable default —
    # see app/admin_auth.py — an unset token fails closed rather than
    # leaving these endpoints open.
    admin_token: str = ""

    # --- Real-money deposits (Telebirr) ---------------------------------
    # See app/services/telebirr_verify.py — ported from Habesha Bet.
    telebirr_verify_enabled: bool = True
    telebirr_verify_timeout: int = 10
    # Deposit accounts rotate round-robin after this many successful
    # deposits on the currently active one.
    rotate_after_deposits: int = 20

    # Displayed in the Mini App (wallet screen) and admin panel for
    # transparency — the NLA sports-betting license this deployment is
    # operating under. Not enforced by any code path; purely informational.
    license_number: str = ""

    # Multi-fight tickets (parlays). Legs must come from different fights
    # (see parlay_service.py — same-fight legs are correlated, not
    # independent risk, and combining them would misprice the payout).
    # A cap exists mostly as a sanity bound, not a hard business need —
    # an ETFC card only ever has so many fights on it anyway.
    max_parlay_legs: int = 10

    model_config = SettingsConfigDict(env_prefix="ETFC_", env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
