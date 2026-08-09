"""
Multi-fight tickets (parlays / accumulators): one wager combining
selections from several different fights, where every leg must win for
the ticket to pay out and the payout multiplies each leg's odds together.

Placement lives here; how legs actually resolve as their fights get
settled lives in settlement_service.py (it has to — a parlay can't be
graded until every leg's fight has been settled, which usually happens
across several separate settle_fight calls over the course of an event).
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Market, MarketOutcome, MarketStatus, Parlay, ParlayLeg, ParlayLegStatus, ParlayStatus, User
from app.services import wallet_service
from app.services.betting_service import InvalidStakeError, MarketNotOpenError, OutcomeNotFoundError, UserNotFoundError


class TooFewLegsError(Exception):
    pass


class TooManyLegsError(Exception):
    pass


class DuplicateLegError(Exception):
    pass


class CorrelatedLegsError(Exception):
    """More than one selection from the same fight in one ticket. Not
    allowed — outcomes within a single fight aren't independent risk
    (e.g. "Fighter A wins" and "Fighter A wins by KO/TKO" are correlated),
    so multiplying their odds together would misprice the payout in the
    bettor's favor. Real sportsbooks block this for the same reason."""
    pass


def place_parlay(db: Session, user_id: str, outcome_ids: list[str], stake: Decimal) -> Parlay:
    settings = get_settings()

    if stake <= 0:
        raise InvalidStakeError("Stake must be positive")
    if len(outcome_ids) < 2:
        raise TooFewLegsError("A parlay needs at least 2 selections — for one selection, place a single bet instead")
    if len(outcome_ids) > settings.max_parlay_legs:
        raise TooManyLegsError(f"A parlay can have at most {settings.max_parlay_legs} selections")
    if len(set(outcome_ids)) != len(outcome_ids):
        raise DuplicateLegError("The same selection can't appear twice in one ticket")

    if db.query(User).filter(User.id == user_id).one_or_none() is None:
        raise UserNotFoundError(f"No such user {user_id}")

    legs_data: list[tuple[Market, MarketOutcome, Decimal, str]] = []
    seen_fight_ids: set[str] = set()
    combined_odds = Decimal("1")

    for outcome_id in outcome_ids:
        outcome = db.query(MarketOutcome).filter(MarketOutcome.id == outcome_id).one_or_none()
        if outcome is None:
            raise OutcomeNotFoundError(f"No such outcome {outcome_id}")

        market = db.query(Market).filter(Market.id == outcome.market_id).with_for_update().one()
        if market.status != MarketStatus.OPEN:
            raise MarketNotOpenError(f"Market {market.id} is {market.status.value}, not open")

        fight_id = market.fight_id
        if fight_id in seen_fight_ids:
            raise CorrelatedLegsError(
                "A parlay can only include one selection per fight — two markets from the "
                "same fight aren't independent risk and can't be combined in one ticket"
            )
        seen_fight_ids.add(fight_id)

        odds = outcome.odds
        combined_odds *= odds
        legs_data.append((market, outcome, odds, fight_id))

    potential_payout = (stake * combined_odds).quantize(Decimal("0.01"))

    parlay = Parlay(
        user_id=user_id,
        stake=stake,
        combined_odds=combined_odds.quantize(Decimal("0.0001")),
        potential_payout=potential_payout,
        status=ParlayStatus.PENDING,
    )
    db.add(parlay)
    db.flush()  # assign parlay.id before it's used as a wallet tx reference / leg FK

    for market, outcome, odds, fight_id in legs_data:
        db.add(
            ParlayLeg(
                parlay_id=parlay.id,
                market_id=market.id,
                outcome_id=outcome.id,
                fight_id=fight_id,
                odds_at_placement=odds,
                status=ParlayLegStatus.PENDING,
            )
        )
    db.flush()

    try:
        # Reusing hold_for_bet with the parlay's id as the reference — the
        # parameter's called bet_id, but it's just a ledger label with no
        # FK behind it (see wallet_service.py), so this is intentional
        # reuse, not a mismatch.
        wallet_service.hold_for_bet(db, user_id, stake, bet_id=parlay.id)
    except (wallet_service.InsufficientFundsError, wallet_service.WalletNotFoundError):
        db.rollback()
        raise

    db.commit()
    db.refresh(parlay)
    return parlay
