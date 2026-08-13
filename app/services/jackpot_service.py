"""
Jackpot pool service.

Rules:
- One round is tied to exactly 11 matches.
- Users pay an entry fee (default 30 ETB) and pick one winner per match.
- After all 11 matches are settled, every entry is scored.
- Anyone with >= min_correct_to_win (default 10) correct wins a share of the prize pool.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Fighter,
    Fight,
    JackpotEntry,
    JackpotPick,
    JackpotRound,
    JackpotStatus,
    TransactionType,
    Wallet,
    WalletTransaction,
)
from app.services import wallet_service


class RoundNotFoundError(Exception):
    pass


class RoundNotOpenError(Exception):
    pass


class RoundAlreadySettledError(Exception):
    pass


class MissingPicksError(Exception):
    pass


class DuplicateEntryError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_round(
    db: Session,
    name: str,
    fight_ids: list[str],
    entry_fee: Decimal = Decimal("30.00"),
    prize_pool: Decimal = Decimal("1000000.00"),
    min_correct_to_win: int = 10,
    deadline: datetime | None = None,
) -> JackpotRound:
    if len(fight_ids) != 11:
        raise ValueError("Jackpot round must have exactly 11 matches")

    fights = db.query(Fight).filter(Fight.id.in_(fight_ids)).all()
    if len(fights) != 11:
        raise ValueError("One or more match IDs are invalid")

    if deadline is None:
        deadline = min(f.scheduled_at for f in fights)

    round_ = JackpotRound(
        name=name,
        fight_ids=fight_ids,
        entry_fee=entry_fee,
        prize_pool=prize_pool,
        min_correct_to_win=min_correct_to_win,
        deadline=deadline,
        status=JackpotStatus.OPEN,
    )
    db.add(round_)
    db.commit()
    db.refresh(round_)
    return round_


def list_rounds(db: Session, status: JackpotStatus | None = None) -> list[JackpotRound]:
    query = db.query(JackpotRound)
    if status is not None:
        query = query.filter(JackpotRound.status == status)
    return query.order_by(JackpotRound.created_at.desc()).all()


def get_round(db: Session, round_id: str) -> JackpotRound:
    round_ = db.query(JackpotRound).filter(JackpotRound.id == round_id).one_or_none()
    if round_ is None:
        raise RoundNotFoundError(f"No jackpot round {round_id}")
    return round_


def submit_entry(
    db: Session,
    user_id: str,
    round_id: str,
    picks: dict[str, str],
    idempotency_key: str | None = None,
) -> JackpotEntry:
    round_ = get_round(db, round_id)

    if round_.status != JackpotStatus.OPEN:
        raise RoundNotOpenError(f"Round {round_id} is {round_.status.value}, not open")

    if _now() >= round_.deadline:
        round_.status = JackpotStatus.LOCKED
        db.commit()
        raise RoundNotOpenError("Entry deadline has passed")

    if len(picks) != 11:
        raise MissingPicksError("You must pick a winner for all 11 matches")

    for fight_id in round_.fight_ids:
        if fight_id not in picks:
            raise MissingPicksError(f"Missing pick for fight {fight_id}")

    existing = db.query(JackpotEntry).filter(
        JackpotEntry.round_id == round_id,
        JackpotEntry.user_id == user_id,
    ).one_or_none()
    if existing is not None:
        raise DuplicateEntryError("You already entered this round")

    if idempotency_key is not None:
        existing_tx = db.query(WalletTransaction).filter(
            WalletTransaction.idempotency_key == idempotency_key
        ).first()
        if existing_tx is not None:
            wallet = db.query(Wallet).filter(Wallet.id == existing_tx.wallet_id).one()
            entry = db.query(JackpotEntry).filter(
                JackpotEntry.user_id == user_id,
                JackpotEntry.round_id == round_id,
            ).one_or_none()
            if entry is not None:
                return entry

    wallet = wallet_service._locked_wallet(db, user_id)
    wallet_service._apply_transaction(
        db,
        wallet,
        TransactionType.JACKPOT_ENTRY,
        -round_.entry_fee,
        reference=f"jackpot_{round_id}",
        idempotency_key=idempotency_key,
    )

    entry = JackpotEntry(
        round_id=round_id,
        user_id=user_id,
    )
    db.add(entry)
    db.flush()

    for fight_id, winner_id in picks.items():
        pick = JackpotPick(
            entry_id=entry.id,
            fight_id=fight_id,
            picked_winner_id=winner_id,
        )
        db.add(pick)

    db.commit()
    db.refresh(entry)
    return entry


def _score_entry(db: Session, entry: JackpotEntry) -> int:
    correct = 0
    for pick in entry.picks:
        fight = db.query(Fight).filter(Fight.id == pick.fight_id).one_or_none()
        if fight is None or fight.winner_fighter_id is None:
            pick.is_correct = None
            continue
        pick.is_correct = fight.winner_fighter_id == pick.picked_winner_id
        if pick.is_correct:
            correct += 1
    entry.correct_count = correct
    return correct


def settle_round(db: Session, round_id: str) -> JackpotRound:
    round_ = get_round(db, round_id)
    if round_.status == JackpotStatus.SETTLED:
        raise RoundAlreadySettledError(f"Round {round_id} is already settled")
    if round_.status == JackpotStatus.CANCELLED:
        raise RoundNotOpenError(f"Round {round_id} is cancelled")

    entries = db.query(JackpotEntry).filter(JackpotEntry.round_id == round_id).all()
    winners = []
    for entry in entries:
        correct = _score_entry(db, entry)
        if correct >= round_.min_correct_to_win:
            entry.won = True
            winners.append(entry)
        else:
            entry.won = False

    if winners:
        payout_per_winner = (round_.prize_pool / len(winners)).quantize(Decimal("0.01"))
        for entry in winners:
            wallet = wallet_service._locked_wallet(db, entry.user_id)
            wallet_service._apply_transaction(
                db,
                wallet,
                TransactionType.BET_PAYOUT,
                payout_per_winner,
                reference=f"jackpot_{round_id}",
            )
            entry.payout = payout_per_winner

    round_.status = JackpotStatus.SETTLED
    round_.settled_at = _now()
    db.commit()
    db.refresh(round_)
    return round_


def get_entry(db: Session, entry_id: str) -> JackpotEntry:
    entry = db.query(JackpotEntry).filter(JackpotEntry.id == entry_id).one_or_none()
    if entry is None:
        raise ValueError(f"No jackpot entry {entry_id}")
    return entry


def get_user_entry(db: Session, round_id: str, user_id: str) -> JackpotEntry | None:
    return db.query(JackpotEntry).filter(
        JackpotEntry.round_id == round_id,
        JackpotEntry.user_id == user_id,
    ).one_or_none()


def list_entries(db: Session, round_id: str) -> list[JackpotEntry]:
    return db.query(JackpotEntry).filter(JackpotEntry.round_id == round_id).all()
