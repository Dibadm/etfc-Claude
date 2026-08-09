"""
Settlement: turn an admin-entered fight result into resolved markets and
paid-out (or voided) bets. Runs as a single DB transaction per fight —
either the whole card of markets/bets settles cleanly or none of it does.

Also resolves parlay legs touching this fight (see parlay_service.py).
A parlay can't be graded until every one of its legs' fights has been
settled — since a ticket's legs must each come from a different fight
(correlated-parlay protection), one settle_fight call touches at most
one leg per parlay, so "is this parlay now fully resolved" gets checked
once per affected parlay at the end of each settlement, not per-leg.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Bet,
    BetStatus,
    Fight,
    FightStatus,
    Market,
    MarketOutcome,
    MarketStatus,
    MarketType,
    Parlay,
    ParlayLeg,
    ParlayLegStatus,
    ParlayStatus,
    VictoryMethod,
)
from app.services import wallet_service
from app.services.database_helpers import utcnow


class AlreadySettledError(Exception):
    pass


def settle_fight(
    db: Session,
    fight: Fight,
    winner_fighter_id: str | None,
    result_method: VictoryMethod,
    result_round: int | None = None,
) -> Fight:
    """
    winner_fighter_id: None if result_method is DRAW or NO_CONTEST.
    result_round: the round the fight ended in (KO/TKO or submission).
                  None if result_method is DECISION (went the distance).
    """
    if fight.status == FightStatus.COMPLETED:
        raise AlreadySettledError(f"Fight {fight.id} is already settled")
    if fight.status == FightStatus.CANCELLED:
        raise AlreadySettledError(
            f"Fight {fight.id} was voided — its markets are already refunded and closed. "
            "Settling it now would overwrite that with a fake winner and corrupt the record."
        )

    fight.status = FightStatus.COMPLETED
    fight.winner_fighter_id = winner_fighter_id
    fight.result_method = result_method
    fight.result_round = result_round

    no_contest_result = result_method in (VictoryMethod.DRAW, VictoryMethod.NO_CONTEST)

    markets = (
        db.query(Market)
        .filter(Market.fight_id == fight.id, Market.status.in_([MarketStatus.OPEN, MarketStatus.SUSPENDED]))
        .with_for_update()
        .all()
    )

    affected_parlay_ids: set[str] = set()

    for market in markets:
        if no_contest_result:
            affected_parlay_ids |= _void_market(db, market)
            continue

        outcomes = db.query(MarketOutcome).filter(MarketOutcome.market_id == market.id).all()
        winning_ids = _winning_outcome_ids(market, outcomes, winner_fighter_id, result_method, result_round)

        for outcome in outcomes:
            outcome.is_winning_outcome = outcome.id in winning_ids

        market.status = MarketStatus.SETTLED
        _resolve_bets_for_market(db, market, winning_ids)
        affected_parlay_ids |= _resolve_parlay_legs_for_market(db, market, winning_ids)

    for parlay_id in affected_parlay_ids:
        _finalize_parlay_if_fully_resolved(db, parlay_id)

    db.commit()
    db.refresh(fight)
    return fight


def void_fight(db: Session, fight: Fight) -> Fight:
    """Fight cancelled — void every market and refund every pending bet's stake."""
    if fight.status == FightStatus.COMPLETED:
        raise AlreadySettledError(f"Fight {fight.id} is already settled, cannot void")

    fight.status = FightStatus.CANCELLED
    markets = (
        db.query(Market)
        .filter(Market.fight_id == fight.id, Market.status.in_([MarketStatus.OPEN, MarketStatus.SUSPENDED]))
        .with_for_update()
        .all()
    )
    affected_parlay_ids: set[str] = set()
    for market in markets:
        affected_parlay_ids |= _void_market(db, market)

    for parlay_id in affected_parlay_ids:
        _finalize_parlay_if_fully_resolved(db, parlay_id)

    db.commit()
    db.refresh(fight)
    return fight


def _winning_outcome_ids(
    market: Market,
    outcomes: list[MarketOutcome],
    winner_fighter_id: str,
    result_method: VictoryMethod,
    result_round: int | None,
) -> set[str]:
    if market.market_type == MarketType.MONEYLINE:
        return {o.id for o in outcomes if o.fighter_id == winner_fighter_id}

    if market.market_type == MarketType.METHOD_OF_VICTORY:
        return {o.id for o in outcomes if o.victory_method == result_method}

    if market.market_type == MarketType.ROUND_PROP:
        if result_method == VictoryMethod.DECISION:
            # "Goes the Distance" outcome is stored with round_number = None
            return {o.id for o in outcomes if o.round_number is None}
        return {o.id for o in outcomes if o.round_number == result_round}

    raise ValueError(f"Unknown market type {market.market_type}")


def _resolve_bets_for_market(db: Session, market: Market, winning_outcome_ids: set[str]) -> None:
    settings = get_settings()
    bets = (
        db.query(Bet)
        .filter(Bet.market_id == market.id, Bet.status == BetStatus.PENDING)
        .with_for_update()
        .all()
    )
    for bet in bets:
        if bet.outcome_id in winning_outcome_ids:
            bet.status = BetStatus.WON
            profit = bet.potential_payout - bet.stake
            net_profit = (profit * (Decimal("1.00") - settings.house_cut_fraction)).quantize(Decimal("0.01"))
            payout_amount = bet.stake + net_profit
            wallet_service.payout_for_bet(db, bet.user_id, payout_amount, bet_id=bet.id)
        else:
            bet.status = BetStatus.LOST
        bet.settled_at = utcnow()


def _void_market(db: Session, market: Market) -> set[str]:
    market.status = MarketStatus.VOID
    bets = (
        db.query(Bet)
        .filter(Bet.market_id == market.id, Bet.status == BetStatus.PENDING)
        .with_for_update()
        .all()
    )
    for bet in bets:
        bet.status = BetStatus.VOID
        bet.settled_at = utcnow()
        wallet_service.refund_for_bet(db, bet.user_id, bet.stake, bet_id=bet.id)

    return _void_parlay_legs_for_market(db, market)


# --- Parlay leg resolution ---------------------------------------------

def _resolve_parlay_legs_for_market(db: Session, market: Market, winning_outcome_ids: set[str]) -> set[str]:
    legs = (
        db.query(ParlayLeg)
        .filter(ParlayLeg.market_id == market.id, ParlayLeg.status == ParlayLegStatus.PENDING)
        .with_for_update()
        .all()
    )
    affected_parlay_ids = set()
    for leg in legs:
        leg.status = ParlayLegStatus.WON if leg.outcome_id in winning_outcome_ids else ParlayLegStatus.LOST
        affected_parlay_ids.add(leg.parlay_id)
    return affected_parlay_ids


def _void_parlay_legs_for_market(db: Session, market: Market) -> set[str]:
    legs = (
        db.query(ParlayLeg)
        .filter(ParlayLeg.market_id == market.id, ParlayLeg.status == ParlayLegStatus.PENDING)
        .with_for_update()
        .all()
    )
    affected_parlay_ids = set()
    for leg in legs:
        leg.status = ParlayLegStatus.VOID
        affected_parlay_ids.add(leg.parlay_id)
    return affected_parlay_ids


def _finalize_parlay_if_fully_resolved(db: Session, parlay_id: str) -> None:
    parlay = db.query(Parlay).filter(Parlay.id == parlay_id).with_for_update().one()
    if parlay.status != ParlayStatus.PENDING:
        return  # already finalized — shouldn't happen, but never double-process a payout

    legs = db.query(ParlayLeg).filter(ParlayLeg.parlay_id == parlay.id).all()
    if any(leg.status == ParlayLegStatus.PENDING for leg in legs):
        return  # still waiting on at least one other fight

    settings = get_settings()

    if any(leg.status == ParlayLegStatus.LOST for leg in legs):
        # One loss sinks the whole ticket — stake was already held at
        # placement, nothing further to move.
        parlay.status = ParlayStatus.LOST
        parlay.settled_at = utcnow()
        return

    won_legs = [leg for leg in legs if leg.status == ParlayLegStatus.WON]
    if not won_legs:
        # Every leg voided (e.g. the whole card got cancelled) — a full
        # refund, not a "win": there's nothing to actually multiply.
        parlay.status = ParlayStatus.VOID
        parlay.settled_at = utcnow()
        wallet_service.refund_for_bet(db, parlay.user_id, parlay.stake, bet_id=parlay.id)
        return

    # Recompute from won legs only — a voided leg is excluded (treated as
    # if it were never in the ticket), not counted as a loss and not
    # counted at its original odds either.
    combined_odds = Decimal("1")
    for leg in won_legs:
        combined_odds *= leg.odds_at_placement
    payout_amount = (parlay.stake * combined_odds).quantize(Decimal("0.01"))

    profit = payout_amount - parlay.stake
    net_profit = (profit * (Decimal("1.00") - settings.house_cut_fraction)).quantize(Decimal("0.01"))
    final_payout = parlay.stake + net_profit

    parlay.status = ParlayStatus.WON
    parlay.settled_at = utcnow()
    wallet_service.payout_for_bet(db, parlay.user_id, final_payout, bet_id=parlay.id)
