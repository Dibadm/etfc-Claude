"""
Wallet operations. Every balance change goes through here and writes an
immutable WalletTransaction row — the ledger is the source of truth;
`wallet.balance` is a cached total that must always equal the sum of
its transactions (see tests/test_betting_engine.py for a check of that
invariant).
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TransactionType, User, Wallet, WalletTransaction


class InsufficientFundsError(Exception):
    pass


class WageringDisabledError(Exception):
    """Raised when a real-money operation is attempted while the
    licensing switch (settings.wagering_enabled) is off."""
    pass


class WalletNotFoundError(Exception):
    """Raised when user_id doesn't correspond to any wallet — usually
    a bad/foreign user_id from the caller, not a server bug. Callers
    (e.g. the API layer) should turn this into a 404, not a 500."""
    pass


def _locked_wallet(db: Session, user_id: str) -> Wallet:
    query = db.query(Wallet).filter(Wallet.user_id == user_id)
    # with_for_update() is enforced on Postgres, a no-op on SQLite —
    # see app/database.py docstring.
    wallet = query.with_for_update().one_or_none()
    if wallet is None:
        raise WalletNotFoundError(f"No wallet for user {user_id}")
    return wallet


def create_user_with_wallet(db: Session, telegram_id: str, username: str | None = None) -> User:
    settings = get_settings()
    user = User(telegram_id=telegram_id, username=username, is_demo_account=not settings.wagering_enabled)
    db.add(user)
    db.flush()  # assign user.id

    wallet = Wallet(user_id=user.id, currency=settings.currency, balance=Decimal("0.00"))
    db.add(wallet)
    db.flush()

    if not settings.wagering_enabled:
        # Product is in demo/pitch mode: seed play money so the full
        # flow can be exercised end to end.
        _apply_transaction(
            db,
            wallet,
            TransactionType.DEMO_CREDIT,
            settings.demo_seed_balance,
            reference="signup_demo_seed",
        )

    db.commit()
    db.refresh(user)
    return user


def get_or_create_user_by_telegram_id(db: Session, telegram_id: str, username: str | None = None) -> User:
    """Used by the Telegram-authenticated /miniapp endpoints: a returning
    user's initData is valid every time they open the app, so this must
    not re-create the user or re-seed a demo balance on every request."""
    user = db.query(User).filter(User.telegram_id == telegram_id).one_or_none()
    if user is not None:
        return user
    return create_user_with_wallet(db, telegram_id, username)


def get_user_by_telegram_id(db: Session, telegram_id: str) -> User | None:
    return db.query(User).filter(User.telegram_id == telegram_id).one_or_none()


def _apply_transaction(
    db: Session,
    wallet: Wallet,
    tx_type: TransactionType,
    signed_amount: Decimal,
    reference: str | None = None,
    idempotency_key: str | None = None,
) -> WalletTransaction:
    """Apply a signed amount to a wallet and write the ledger row.
    Caller is responsible for the surrounding commit/rollback."""
    if idempotency_key is not None:
        existing = (
            db.query(WalletTransaction)
            .filter(WalletTransaction.idempotency_key == idempotency_key)
            .first()
        )
        if existing is not None:
            return existing
    new_balance = wallet.balance + signed_amount
    if new_balance < 0:
        raise InsufficientFundsError(
            f"Wallet {wallet.id} balance {wallet.balance} cannot cover {signed_amount}"
        )
    wallet.balance = new_balance
    tx = WalletTransaction(
        wallet_id=wallet.id,
        type=tx_type,
        amount=signed_amount,
        balance_after=new_balance,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    db.add(tx)
    return tx


def deposit_real_funds(db: Session, user_id: str, amount: Decimal, reference: str, idempotency_key: str | None = None) -> Wallet:
    """Real-money deposit (e.g. Telebirr). Blocked until licensed."""
    settings = get_settings()
    if not settings.wagering_enabled:
        raise WageringDisabledError(
            "Real-money deposits are disabled until the Lottery Service license is active "
            "(ETFC_WAGERING_ENABLED=false). Use demo credits for now."
        )
    wallet = _locked_wallet(db, user_id)
    _apply_transaction(db, wallet, TransactionType.DEPOSIT, amount, reference=reference, idempotency_key=idempotency_key)
    db.commit()
    db.refresh(wallet)
    return wallet


def withdraw_real_funds(db: Session, user_id: str, amount: Decimal, reference: str) -> Wallet:
    settings = get_settings()
    if not settings.wagering_enabled:
        raise WageringDisabledError("Withdrawals are disabled until the license is active.")
    wallet = _locked_wallet(db, user_id)
    _apply_transaction(db, wallet, TransactionType.WITHDRAWAL, -amount, reference=reference)
    db.commit()
    db.refresh(wallet)
    return wallet


def hold_for_bet(db: Session, user_id: str, amount: Decimal, bet_id: str) -> Wallet:
    """Debit stake from balance at bet placement time."""
    wallet = _locked_wallet(db, user_id)
    _apply_transaction(db, wallet, TransactionType.BET_HOLD, -amount, reference=bet_id)
    return wallet  # caller (betting_service) controls the commit boundary


def payout_for_bet(db: Session, user_id: str, amount: Decimal, bet_id: str) -> Wallet:
    wallet = _locked_wallet(db, user_id)
    _apply_transaction(db, wallet, TransactionType.BET_PAYOUT, amount, reference=bet_id)
    return wallet


def refund_for_bet(db: Session, user_id: str, amount: Decimal, bet_id: str) -> Wallet:
    wallet = _locked_wallet(db, user_id)
    _apply_transaction(db, wallet, TransactionType.BET_REFUND, amount, reference=bet_id)
    return wallet
