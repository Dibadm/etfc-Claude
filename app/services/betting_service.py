from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Bet, BetStatus, Market, MarketOutcome, MarketStatus, User
from app.services import wallet_service


class MarketNotOpenError(Exception):
    pass


class InvalidStakeError(Exception):
    pass


class OutcomeNotFoundError(Exception):
    """Bad outcome_id from the caller — should map to a 404, not a 500."""
    pass


class UserNotFoundError(Exception):
    """Bad user_id from the caller — should map to a 404, not a 500."""
    pass


def place_bet(
    db: Session,
    user_id: str,
    outcome_id: str,
    stake: Decimal,
) -> Bet:
    if stake <= 0:
        raise InvalidStakeError("Stake must be positive")

    # Validate the user up front, before creating any rows — with FK
    # enforcement on, an INSERT with a bad user_id would otherwise fail
    # as a raw IntegrityError instead of a clean, catchable error.
    if db.query(User).filter(User.id == user_id).one_or_none() is None:
        raise UserNotFoundError(f"No such user {user_id}")

    # Lock the outcome's market row implicitly by re-fetching fresh —
    # combined with the wallet row lock in hold_for_bet, this keeps
    # "market still open + enough balance" checked atomically against
    # concurrent bets/settlement on Postgres.
    outcome = db.query(MarketOutcome).filter(MarketOutcome.id == outcome_id).one_or_none()
    if outcome is None:
        raise OutcomeNotFoundError(f"No such outcome {outcome_id}")

    market = db.query(Market).filter(Market.id == outcome.market_id).with_for_update().one()
    if market.status != MarketStatus.OPEN:
        raise MarketNotOpenError(f"Market {market.id} is {market.status.value}, not open")

    odds_at_placement = outcome.odds  # snapshot — later odds moves won't affect this bet
    potential_payout = (stake * odds_at_placement).quantize(Decimal("0.01"))

    bet = Bet(
        user_id=user_id,
        market_id=market.id,
        outcome_id=outcome.id,
        stake=stake,
        odds_at_placement=odds_at_placement,
        potential_payout=potential_payout,
        status=BetStatus.PENDING,
    )
    db.add(bet)
    db.flush()  # assign bet.id before it's used as a wallet tx reference

    try:
        wallet_service.hold_for_bet(db, user_id, stake, bet_id=bet.id)
    except (wallet_service.InsufficientFundsError, wallet_service.WalletNotFoundError):
        db.rollback()
        raise

    db.commit()
    db.refresh(bet)
    return bet
