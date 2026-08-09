from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import BetStatus, FightStatus, MarketStatus, MarketType, ParlayLegStatus, ParlayStatus, VictoryMethod

MIN_DECIMAL_ODDS = Decimal("1.01")


def _check_odds(value: Decimal, field_name: str) -> Decimal:
    if value < MIN_DECIMAL_ODDS:
        raise ValueError(
            f"{field_name} must be at least {MIN_DECIMAL_ODDS} (decimal odds of 1.00 or "
            "below imply the bettor can't win money, which isn't a valid market)"
        )
    return value


class FighterCreate(BaseModel):
    name: str
    nickname: str | None = None
    image_url: str | None = None


class FighterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    nickname: str | None
    image_url: str | None


class FighterUpdate(BaseModel):
    """All fields optional — PATCH semantics, only supplied fields change."""
    name: str | None = None
    nickname: str | None = None
    image_url: str | None = None


class FightCreate(BaseModel):
    event_name: str
    weight_class: str | None = None
    fighter_a_id: str
    fighter_b_id: str
    scheduled_at: datetime
    is_main_event: bool = False


class FightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_name: str
    weight_class: str | None
    fighter_a_id: str
    fighter_b_id: str
    scheduled_at: datetime
    status: FightStatus
    is_main_event: bool
    winner_fighter_id: str | None
    result_method: VictoryMethod | None
    result_round: int | None


class FightWithFightersOut(BaseModel):
    """Richer fight representation for listing screens (the Mini App's
    fight list) so the frontend doesn't have to make N extra requests to
    resolve fighter_a_id/fighter_b_id into names."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_name: str
    weight_class: str | None
    scheduled_at: datetime
    status: FightStatus
    is_main_event: bool
    fighter_a: FighterOut
    fighter_b: FighterOut
    moneyline_odds_a: Decimal | None = None
    moneyline_odds_b: Decimal | None = None


class MoneylineMarketCreate(BaseModel):
    fight_id: str
    odds_fighter_a: Decimal
    odds_fighter_b: Decimal

    _v_a = field_validator("odds_fighter_a")(lambda v: _check_odds(v, "odds_fighter_a"))
    _v_b = field_validator("odds_fighter_b")(lambda v: _check_odds(v, "odds_fighter_b"))


class MethodOfVictoryMarketCreate(BaseModel):
    fight_id: str
    odds_ko_tko: Decimal
    odds_submission: Decimal
    odds_decision: Decimal

    _v1 = field_validator("odds_ko_tko")(lambda v: _check_odds(v, "odds_ko_tko"))
    _v2 = field_validator("odds_submission")(lambda v: _check_odds(v, "odds_submission"))
    _v3 = field_validator("odds_decision")(lambda v: _check_odds(v, "odds_decision"))


class RoundPropMarketCreate(BaseModel):
    fight_id: str
    total_rounds: int
    odds_by_round: dict[int, Decimal]
    odds_goes_the_distance: Decimal

    @field_validator("odds_by_round")
    @classmethod
    def _v_odds_by_round(cls, value: dict[int, Decimal]) -> dict[int, Decimal]:
        for round_number, odds in value.items():
            _check_odds(odds, f"odds_by_round[{round_number}]")
        return value

    _v_distance = field_validator("odds_goes_the_distance")(lambda v: _check_odds(v, "odds_goes_the_distance"))


class MarketOutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    odds: Decimal
    is_winning_outcome: bool | None


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    fight_id: str
    market_type: MarketType
    status: MarketStatus
    outcomes: list[MarketOutcomeOut]


class UserCreate(BaseModel):
    telegram_id: str
    username: str | None = None


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    balance: Decimal
    currency: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    telegram_id: str
    username: str | None
    is_demo_account: bool
    wallet: WalletOut


class BetCreate(BaseModel):
    user_id: str
    outcome_id: str
    stake: Decimal


class MiniAppBetCreate(BaseModel):
    """Same as BetCreate but without user_id — the Mini App never gets to
    say who it's betting as; that's derived from the validated Telegram
    initData on the request, not the request body."""
    outcome_id: str
    stake: Decimal


class BetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    market_id: str
    outcome_id: str
    stake: Decimal
    odds_at_placement: Decimal
    potential_payout: Decimal
    status: BetStatus


class SettleFightRequest(BaseModel):
    winner_fighter_id: str | None = None
    result_method: VictoryMethod
    result_round: int | None = None


class OddsUpdateRequest(BaseModel):
    new_odds: Decimal

    _v = field_validator("new_odds")(lambda v: _check_odds(v, "new_odds"))


class LiabilityOutcome(BaseModel):
    outcome_id: str
    label: str
    odds: Decimal
    pending_bet_count: int
    total_stake: Decimal
    # Worst case for the house: what's owed if THIS outcome wins.
    total_potential_payout: Decimal


class LiabilityMarket(BaseModel):
    market_id: str
    market_type: MarketType
    market_status: MarketStatus
    outcomes: list[LiabilityOutcome]


class DepositAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    phone: str
    recipient_name: str
    is_active: bool
    deposit_count: int


class DepositAccountCreate(BaseModel):
    phone: str
    recipient_name: str


class DepositSmsSubmit(BaseModel):
    sms_text: str
    expected_amount: Decimal | None = None


class ParlayCreate(BaseModel):
    outcome_ids: list[str]
    stake: Decimal


class ParlayLegOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    market_id: str
    outcome_id: str
    fight_id: str
    odds_at_placement: Decimal
    status: ParlayLegStatus


class ParlayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    stake: Decimal
    combined_odds: Decimal
    potential_payout: Decimal
    status: ParlayStatus
    legs: list[ParlayLegOut]
