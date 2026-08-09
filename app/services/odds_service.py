"""
Market and odds management — the admin-facing side of setting up a fight
card before bets can be placed against it.

A note on the house edge: in a real fixed-odds sportsbook, the operator's
margin lives inside the odds themselves (the "overround" — outcome
probabilities implied by the odds are set to sum to a bit over 100%),
not as a cut taken out of a winner's payout after the fact. This engine
follows that model: admins set odds directly per outcome, and whatever
margin you want is baked in there. `settings.house_cut_fraction` exists
as an optional *additional* rake on top of that and defaults to zero —
don't turn it on without a clear reason, since combined with
already-vigged odds it compounds into a worse price for bettors than
either mechanism alone, which is the kind of thing a regulator reviewing
your product will notice.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Fight,
    Market,
    MarketOutcome,
    MarketStatus,
    MarketType,
    VictoryMethod,
)


def create_moneyline_market(
    db: Session, fight: Fight, odds_fighter_a: Decimal, odds_fighter_b: Decimal
) -> Market:
    market = Market(fight_id=fight.id, market_type=MarketType.MONEYLINE)
    db.add(market)
    db.flush()

    db.add_all(
        [
            MarketOutcome(
                market_id=market.id,
                label=fight.fighter_a.name,
                odds=odds_fighter_a,
                fighter_id=fight.fighter_a_id,
            ),
            MarketOutcome(
                market_id=market.id,
                label=fight.fighter_b.name,
                odds=odds_fighter_b,
                fighter_id=fight.fighter_b_id,
            ),
        ]
    )
    db.commit()
    db.refresh(market)
    return market


def create_method_of_victory_market(
    db: Session, fight: Fight, odds_by_method: dict[VictoryMethod, Decimal]
) -> Market:
    market = Market(fight_id=fight.id, market_type=MarketType.METHOD_OF_VICTORY)
    db.add(market)
    db.flush()

    labels = {
        VictoryMethod.KO_TKO: "KO/TKO",
        VictoryMethod.SUBMISSION: "Submission",
        VictoryMethod.DECISION: "Decision",
    }
    for method, odds in odds_by_method.items():
        db.add(
            MarketOutcome(
                market_id=market.id,
                label=labels.get(method, method.value),
                odds=odds,
                victory_method=method,
            )
        )
    db.commit()
    db.refresh(market)
    return market


def create_round_prop_market(
    db: Session,
    fight: Fight,
    odds_by_round: dict[int, Decimal],
    odds_goes_the_distance: Decimal,
    total_rounds: int,
) -> Market:
    """odds_by_round keys are round numbers the fight could end in
    (e.g. {1: 4.5, 2: 5.0, 3: 3.5} for a 3-round fight); goes-the-distance
    covers the fight reaching a decision."""
    market = Market(fight_id=fight.id, market_type=MarketType.ROUND_PROP)
    db.add(market)
    db.flush()

    for round_number, odds in odds_by_round.items():
        db.add(
            MarketOutcome(
                market_id=market.id,
                label=f"Round {round_number}",
                odds=odds,
                round_number=round_number,
            )
        )
    db.add(
        MarketOutcome(
            market_id=market.id,
            label="Goes the Distance",
            odds=odds_goes_the_distance,
            round_number=None,
        )
    )
    db.commit()
    db.refresh(market)
    return market


class MarketAlreadyFinalizedError(Exception):
    pass


def suspend_market(db: Session, market: Market) -> Market:
    if market.status in (MarketStatus.SETTLED, MarketStatus.VOID):
        raise MarketAlreadyFinalizedError(f"Market {market.id} is already {market.status.value} — cannot suspend it")
    market.status = MarketStatus.SUSPENDED
    db.commit()
    db.refresh(market)
    return market


def reopen_market(db: Session, market: Market) -> Market:
    if market.status in (MarketStatus.SETTLED, MarketStatus.VOID):
        raise MarketAlreadyFinalizedError(
            f"Market {market.id} is already {market.status.value} — cannot reopen it. "
            "Its fight has been settled/voided; bets placed now could never be graded."
        )
    market.status = MarketStatus.OPEN
    db.commit()
    db.refresh(market)
    return market


def update_outcome_odds(db: Session, outcome: MarketOutcome, new_odds: Decimal) -> MarketOutcome:
    outcome.odds = new_odds
    db.commit()
    db.refresh(outcome)
    return outcome
