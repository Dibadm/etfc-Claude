"""
Orchestrates a Telebirr SMS deposit end to end: parse the pasted SMS ->
match it against the currently active deposit account -> reject a reused
transaction reference -> verify online against Ethio Telecom's own
receipt system -> credit the wallet -> rotate deposit accounts if the
active one has hit its deposit limit.

Ported from Habesha Bet's handle_submit_deposit_sms (api_handlers.py) —
same sequence of checks, same rotation behavior — adapted to this
codebase's SQLAlchemy models, Decimal money handling, and
exception-based control flow (the original returns {"ok": False, "error":
...} dicts; here each failure mode is its own exception type, matching
how betting_service/wallet_service already do it, so the API layer's
existing try/except-to-HTTPException pattern extends naturally).
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DepositAccount, DepositReview, DepositReviewStatus, TransactionType, User, Wallet, WalletTransaction
from app.services import telebirr_verify, wallet_service
from app.services.telebirr_sms_parser import (
    extract_receipt_number,
    parse_telebirr_sms,
    validate_deposit_amount,
    verify_recipient,
)


class NoActiveDepositAccountError(Exception):
    pass


class InvalidSmsError(Exception):
    pass


class WrongAccountError(Exception):
    pass


class DuplicateReferenceError(Exception):
    pass


class ReceiptVerificationFailedError(Exception):
    """The online receipt check actively failed (not found, mismatched
    recipient) — as opposed to the receipt site merely being unreachable,
    which falls back to regex-only verification instead of blocking."""
    pass


class AmountMismatchError(Exception):
    pass


class DepositReviewRequiredError(Exception):
    def __init__(self, review_id: str, message: str = "Deposit is under manual review."):
        self.review_id = review_id
        super().__init__(message)


def get_active_deposit_account(db: Session) -> DepositAccount:
    account = db.query(DepositAccount).filter(DepositAccount.is_active == True).one_or_none()  # noqa: E712
    if account is None:
        raise NoActiveDepositAccountError("No active Telebirr deposit account is configured")
    return account


def reference_already_used(db: Session, reference: str) -> bool:
    """Scoped to DEPOSIT transactions specifically — bet ids also land in
    WalletTransaction.reference for other transaction types, and while a
    UUID bet id colliding with a short Telebirr reference is practically
    impossible, scoping the query removes any doubt."""
    return (
        db.query(WalletTransaction)
        .filter(WalletTransaction.reference == reference, WalletTransaction.type == TransactionType.DEPOSIT)
        .first()
        is not None
    )


def _rotate_if_needed(db: Session, account: DepositAccount) -> None:
    settings = get_settings()
    if account.deposit_count < settings.rotate_after_deposits:
        return
    all_accounts = db.query(DepositAccount).order_by(DepositAccount.created_at).all()
    if len(all_accounts) > 1:
        ids = [a.id for a in all_accounts]
        idx = ids.index(account.id)
        next_account = all_accounts[(idx + 1) % len(all_accounts)]
        account.is_active = False
        next_account.is_active = True
        next_account.deposit_count = 0
    else:
        # Only one account configured — just reset its counter.
        account.deposit_count = 0


def submit_deposit_sms(
    db: Session,
    user_id: str,
    sms_text: str,
    expected_amount: Decimal | None = None,
    idempotency_key: str | None = None,
) -> Wallet:
    settings = get_settings()
    if not settings.wagering_enabled:
        raise wallet_service.WageringDisabledError(
            "Real-money deposits are disabled until the Lottery Service license is active."
        )

    if idempotency_key is not None:
        existing = (
            db.query(WalletTransaction)
            .filter(WalletTransaction.idempotency_key == idempotency_key)
            .first()
        )
        if existing is not None:
            wallet = db.query(Wallet).filter(Wallet.id == existing.wallet_id).one()
            return wallet

    account = get_active_deposit_account(db)

    parsed = parse_telebirr_sms(sms_text)
    if parsed is None:
        raise InvalidSmsError("Could not read this SMS — paste the full Telebirr confirmation message.")

    expected_last4 = account.phone[-4:]
    ok, reason = verify_recipient(parsed, account.recipient_name, expected_last4)
    if not ok:
        raise WrongAccountError(f"Payment was not sent to our active deposit account ({reason})")

    if reference_already_used(db, parsed.reference):
        raise DuplicateReferenceError("This transaction has already been credited.")

    receipt_no = extract_receipt_number(sms_text)

    if settings.telebirr_verify_enabled and receipt_no:
        verification = telebirr_verify.verify_receipt_online(receipt_no, timeout=settings.telebirr_verify_timeout)

        if not verification.ok:
            if verification.error not in ("receipt_site_unreachable", "receipt_site_timeout", "receipt_fetch_error"):
                review = DepositReview(
                    user_id=user_id,
                    amount=parsed.amount,
                    reference=parsed.reference,
                    sms_text=sms_text,
                    verification_error=verification.error,
                )
                db.add(review)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                raise DepositReviewRequiredError(
                    review.id,
                    "We couldn't verify this receipt automatically. Your deposit is under review — we'll credit it within a few hours.",
                )
        else:
            if verification.amount is not None and abs(verification.amount - parsed.amount) > Decimal("0.01"):
                raise AmountMismatchError(
                    f"Receipt shows {verification.amount} ETB but the SMS shows {parsed.amount} ETB."
                )
            if verification.recipient_name and parsed.recipient_name:
                if verification.recipient_name.strip().lower() != parsed.recipient_name.strip().lower():
                    raise ReceiptVerificationFailedError("Receipt recipient does not match the deposit details.")
            if verification.recipient_phone_last4 and parsed.recipient_last4:
                if verification.recipient_phone_last4 != parsed.recipient_last4:
                    raise ReceiptVerificationFailedError("Receipt phone number does not match the deposit details.")

    if expected_amount is not None:
        amount_ok, _ = validate_deposit_amount(parsed, expected_amount=expected_amount)
        if not amount_ok:
            raise AmountMismatchError(f"SMS shows {parsed.amount} ETB but {expected_amount} ETB was expected.")

    try:
        wallet = wallet_service.deposit_real_funds(
            db, user_id, parsed.amount, reference=parsed.reference, idempotency_key=idempotency_key
        )
    except IntegrityError:
        db.rollback()
        raise DuplicateReferenceError("This transaction has already been credited.")

    account.deposit_count += 1
    _rotate_if_needed(db, account)
    db.commit()
    db.refresh(wallet)

    return wallet


# --- Admin: managing the pool of rotating deposit accounts -----------------

def list_deposit_accounts(db: Session) -> list[DepositAccount]:
    return db.query(DepositAccount).order_by(DepositAccount.created_at).all()


def add_deposit_account(db: Session, phone: str, recipient_name: str) -> DepositAccount:
    """The first account ever added becomes active automatically —
    otherwise deposits would have nowhere to go with an empty pool."""
    is_first = db.query(DepositAccount).count() == 0
    account = DepositAccount(phone=phone, recipient_name=recipient_name, is_active=is_first)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


class DepositAccountNotFoundError(Exception):
    pass


def remove_deposit_account(db: Session, account_id: str) -> None:
    account = db.query(DepositAccount).filter(DepositAccount.id == account_id).one_or_none()
    if account is None:
        raise DepositAccountNotFoundError(f"No deposit account {account_id}")
    was_active = account.is_active
    db.delete(account)
    db.flush()

    if was_active:
        # Removing the active account promotes the next one so deposits
        # never end up with no active account just because one was deleted.
        next_account = db.query(DepositAccount).order_by(DepositAccount.created_at).first()
        if next_account is not None:
            next_account.is_active = True
    db.commit()


def set_deposit_account_active(db: Session, account_id: str, is_active: bool) -> DepositAccount:
    """Manually activating one account deactivates all others — exactly
    one active account at a time is the invariant the rotation logic
    depends on."""
    account = db.query(DepositAccount).filter(DepositAccount.id == account_id).one_or_none()
    if account is None:
        raise DepositAccountNotFoundError(f"No deposit account {account_id}")

    if is_active:
        db.query(DepositAccount).filter(DepositAccount.id != account_id).update({"is_active": False})
    account.is_active = is_active
    db.commit()
    db.refresh(account)
    return account


# --- Manual review queue for failed online verifications ---------------------


def create_deposit_review(db: Session, user_id: str, amount: Decimal, reference: str, sms_text: str, verification_error: str) -> DepositReview:
    review = DepositReview(
        user_id=user_id,
        amount=amount,
        reference=reference,
        sms_text=sms_text,
        verification_error=verification_error,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def get_deposit_review(db: Session, review_id: str) -> DepositReview | None:
    return db.query(DepositReview).filter(DepositReview.id == review_id).one_or_none()


def list_deposit_reviews(db: Session, status: DepositReviewStatus | None = None) -> list[DepositReview]:
    query = db.query(DepositReview)
    if status is not None:
        query = query.filter(DepositReview.status == status)
    return query.order_by(DepositReview.created_at.desc()).all()


def approve_deposit_review(db: Session, review_id: str, reviewer_token: str | None = None) -> DepositReview:
    review = db.query(DepositReview).filter(DepositReview.id == review_id).one_or_none()
    if review is None:
        raise DepositAccountNotFoundError(f"No deposit review {review_id}")
    if review.status != DepositReviewStatus.PENDING:
        raise ValueError(f"Review is already {review.status}")

    user = db.query(User).filter(User.id == review.user_id).one_or_none()
    if user is None:
        raise ValueError(f"User {review.user_id} not found")

    wallet = wallet_service.deposit_real_funds(db, user.id, review.amount, reference=review.reference)
    review.status = DepositReviewStatus.APPROVED
    review.reviewed_at = datetime.now(timezone.utc)
    review.reviewer_token = reviewer_token
    db.commit()
    db.refresh(review)
    return review


def reject_deposit_review(db: Session, review_id: str, reviewer_token: str | None = None) -> DepositReview:
    review = db.query(DepositReview).filter(DepositReview.id == review_id).one_or_none()
    if review is None:
        raise DepositAccountNotFoundError(f"No deposit review {review_id}")
    if review.status != DepositReviewStatus.PENDING:
        raise ValueError(f"Review is already {review.status}")

    review.status = DepositReviewStatus.REJECTED
    review.reviewed_at = datetime.now(timezone.utc)
    review.reviewer_token = reviewer_token
    db.commit()
    db.refresh(review)
    return review
