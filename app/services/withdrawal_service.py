"""
Withdrawal service.

Flow:
1. User requests withdrawal from the Mini App.
2. A Withdrawal row is created with status PENDING and the amount is
   debited from the wallet using an idempotency key so duplicate
   requests can't double-debit.
3. Admin reviews and either approves or rejects.
4. If approved, the withdrawal stays approved/paid in the ledger.
   Actual Telebirr payout is out of scope for now — this is the
   platform-side accounting only.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TransactionType, User, Wallet, Withdrawal, WithdrawalStatus
from app.services import wallet_service


class WageringDisabledError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


class WithdrawalNotFoundError(Exception):
    pass


class InvalidStatusError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def request_withdrawal(
    db: Session,
    user_id: str,
    amount: float,
    telebirr_phone: str,
    idempotency_key: str | None = None,
) -> Withdrawal:
    settings = get_settings()
    if not settings.wagering_enabled:
        raise WageringDisabledError("Withdrawals are disabled until the license is active.")

    if amount <= 0:
        raise ValueError("Amount must be positive")

    if idempotency_key is not None:
        existing = db.query(Withdrawal).filter(Withdrawal.idempotency_key == idempotency_key).first()
        if existing is not None:
            return existing

    wallet = wallet_service._locked_wallet(db, user_id)
    wallet_service._apply_transaction(
        db,
        wallet,
        TransactionType.WITHDRAWAL,
        -amount,
        reference=f"withdrawal_{user_id}",
        idempotency_key=idempotency_key,
    )

    withdrawal = Withdrawal(
        user_id=user_id,
        amount=amount,
        telebirr_phone=telebirr_phone,
        status=WithdrawalStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    db.add(withdrawal)
    db.commit()
    db.refresh(withdrawal)
    return withdrawal


def approve_withdrawal(db: Session, withdrawal_id: str, reviewer_token: str | None = None) -> Withdrawal:
    withdrawal = db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).one_or_none()
    if withdrawal is None:
        raise WithdrawalNotFoundError(f"No withdrawal {withdrawal_id}")
    if withdrawal.status != WithdrawalStatus.PENDING:
        raise InvalidStatusError(f"Withdrawal is already {withdrawal.status.value}")

    withdrawal.status = WithdrawalStatus.APPROVED
    withdrawal.reviewed_at = _now()
    withdrawal.reviewer_token = reviewer_token
    db.commit()
    db.refresh(withdrawal)
    return withdrawal


def reject_withdrawal(db: Session, withdrawal_id: str, reviewer_token: str | None = None) -> Withdrawal:
    withdrawal = db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).one_or_none()
    if withdrawal is None:
        raise WithdrawalNotFoundError(f"No withdrawal {withdrawal_id}")
    if withdrawal.status != WithdrawalStatus.PENDING:
        raise InvalidStatusError(f"Withdrawal is already {withdrawal.status.value}")

    wallet = wallet_service._locked_wallet(db, withdrawal.user_id)
    wallet_service._apply_transaction(
        db,
        wallet,
        TransactionType.BET_PAYOUT,
        withdrawal.amount,
        reference=f"withdrawal_refund_{withdrawal.id}",
    )

    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.reviewed_at = _now()
    withdrawal.reviewer_token = reviewer_token
    db.commit()
    db.refresh(withdrawal)
    return withdrawal


def get_withdrawal(db: Session, withdrawal_id: str) -> Withdrawal | None:
    return db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).one_or_none()


def list_withdrawals(db: Session, user_id: str | None = None) -> list[Withdrawal]:
    query = db.query(Withdrawal)
    if user_id is not None:
        query = query.filter(Withdrawal.user_id == user_id)
    return query.order_by(Withdrawal.created_at.desc()).all()
