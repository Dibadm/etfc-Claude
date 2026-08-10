import enum
import uuid
from datetime import datetime, timezone

from decimal import Decimal
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

class FightStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VictoryMethod(str, enum.Enum):
    KO_TKO = "ko_tko"
    SUBMISSION = "submission"
    DECISION = "decision"
    DRAW = "draw"
    NO_CONTEST = "no_contest"


class MarketType(str, enum.Enum):
    MONEYLINE = "moneyline"
    METHOD_OF_VICTORY = "method_of_victory"
    ROUND_PROP = "round_prop"


class MarketStatus(str, enum.Enum):
    OPEN = "open"
    SUSPENDED = "suspended"
    SETTLED = "settled"
    VOID = "void"


class BetStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"
    REFUNDED = "refunded"


class ParlayStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"


class ParlayLegStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DEMO_CREDIT = "demo_credit"
    BET_HOLD = "bet_hold"
    BET_PAYOUT = "bet_payout"
    BET_REFUND = "bet_refund"
    JACKPOT_ENTRY = "jackpot_entry"


class DepositReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JackpotStatus(str, enum.Enum):
    OPEN = "open"
    LOCKED = "locked"
    SETTLED = "settled"
    CANCELLED = "cancelled"


class WithdrawalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


# --------------------------------------------------------------------------
# Users / wallets
# --------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    telegram_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_demo_account = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    wallet = relationship("Wallet", back_populates="user", uselist=False)
    bets = relationship("Bet", back_populates="user")


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String, nullable=False, default="ETB")
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet")


class WalletTransaction(Base):
    """Immutable ledger entry. Every balance change must write one of these."""
    __tablename__ = "wallet_transactions"

    id = Column(String, primary_key=True, default=_uuid)
    wallet_id = Column(String, ForeignKey("wallets.id"), nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    balance_after = Column(Numeric(14, 2), nullable=False)
    reference = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    wallet = relationship("Wallet", back_populates="transactions")

    __table_args__ = (
        Index(
            "uq_wallet_transactions_deposit_reference",
            "reference",
            unique=True,
            postgresql_where=(type == TransactionType.DEPOSIT),
            sqlite_where=(type == TransactionType.DEPOSIT),
        ),
    )


# --------------------------------------------------------------------------
# Fighters / fights
# --------------------------------------------------------------------------

class Fighter(Base):
    __tablename__ = "fighters"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    nickname = Column(String, nullable=True)
    image_url = Column(String, nullable=True)


class Fight(Base):
    __tablename__ = "fights"

    id = Column(String, primary_key=True, default=_uuid)
    event_name = Column(String, nullable=False)
    weight_class = Column(String, nullable=True)
    fighter_a_id = Column(String, ForeignKey("fighters.id"), nullable=False)
    fighter_b_id = Column(String, ForeignKey("fighters.id"), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(FightStatus), nullable=False, default=FightStatus.SCHEDULED)
    is_main_event = Column(Boolean, nullable=False, default=False)

    winner_fighter_id = Column(String, ForeignKey("fighters.id"), nullable=True)
    result_method = Column(Enum(VictoryMethod), nullable=True)
    result_round = Column(Integer, nullable=True)

    fighter_a = relationship("Fighter", foreign_keys=[fighter_a_id])
    fighter_b = relationship("Fighter", foreign_keys=[fighter_b_id])
    winner = relationship("Fighter", foreign_keys=[winner_fighter_id])
    markets = relationship("Market", back_populates="fight")


# --------------------------------------------------------------------------
# Markets / outcomes
# --------------------------------------------------------------------------

class Market(Base):
    __tablename__ = "markets"

    id = Column(String, primary_key=True, default=_uuid)
    fight_id = Column(String, ForeignKey("fights.id"), nullable=False)
    market_type = Column(Enum(MarketType), nullable=False)
    status = Column(Enum(MarketStatus), nullable=False, default=MarketStatus.OPEN)
    created_at = Column(DateTime(timezone=True), default=_now)

    fight = relationship("Fight", back_populates="markets")
    outcomes = relationship("MarketOutcome", back_populates="market")

    __table_args__ = (
        UniqueConstraint("fight_id", "market_type", name="uq_fight_market_type"),
    )


class MarketOutcome(Base):
    __tablename__ = "market_outcomes"

    id = Column(String, primary_key=True, default=_uuid)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    label = Column(String, nullable=False)
    odds = Column(Numeric(6, 2), nullable=False)

    fighter_id = Column(String, ForeignKey("fighters.id"), nullable=True)
    victory_method = Column(Enum(VictoryMethod), nullable=True)
    round_number = Column(Integer, nullable=True)

    is_winning_outcome = Column(Boolean, nullable=True)

    market = relationship("Market", back_populates="outcomes")


# --------------------------------------------------------------------------
# Bets
# --------------------------------------------------------------------------

class Bet(Base):
    __tablename__ = "bets"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    outcome_id = Column(String, ForeignKey("market_outcomes.id"), nullable=False)

    stake = Column(Numeric(14, 2), nullable=False)
    odds_at_placement = Column(Numeric(6, 2), nullable=False)
    potential_payout = Column(Numeric(14, 2), nullable=False)

    status = Column(Enum(BetStatus), nullable=False, default=BetStatus.PENDING)
    placed_at = Column(DateTime(timezone=True), default=_now)
    settled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="bets")
    market = relationship("Market")
    outcome = relationship("MarketOutcome")


# --------------------------------------------------------------------------
# Parlays
# --------------------------------------------------------------------------

class Parlay(Base):
    __tablename__ = "parlays"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    stake = Column(Numeric(14, 2), nullable=False)
    combined_odds = Column(Numeric(12, 4), nullable=False)
    potential_payout = Column(Numeric(14, 2), nullable=False)

    status = Column(Enum(ParlayStatus), nullable=False, default=ParlayStatus.PENDING)
    placed_at = Column(DateTime(timezone=True), default=_now)
    settled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    legs = relationship("ParlayLeg", back_populates="parlay")


class ParlayLeg(Base):
    __tablename__ = "parlay_legs"

    id = Column(String, primary_key=True, default=_uuid)
    parlay_id = Column(String, ForeignKey("parlays.id"), nullable=False)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    outcome_id = Column(String, ForeignKey("market_outcomes.id"), nullable=False)
    fight_id = Column(String, ForeignKey("fights.id"), nullable=False)

    odds_at_placement = Column(Numeric(6, 2), nullable=False)
    status = Column(Enum(ParlayLegStatus), nullable=False, default=ParlayLegStatus.PENDING)

    parlay = relationship("Parlay", back_populates="legs")
    market = relationship("Market")
    outcome = relationship("MarketOutcome")
    fight = relationship("Fight")


# --------------------------------------------------------------------------
# Telebirr deposit accounts
# --------------------------------------------------------------------------

class DepositAccount(Base):
    __tablename__ = "deposit_accounts"

    id = Column(String, primary_key=True, default=_uuid)
    phone = Column(String, nullable=False)
    recipient_name = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    deposit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)


class DepositReview(Base):
    __tablename__ = "deposit_reviews"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    reference = Column(String, nullable=False)
    sms_text = Column(String, nullable=False)
    verification_error = Column(String, nullable=False)
    status = Column(Enum(DepositReviewStatus), nullable=False, default=DepositReviewStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=_now)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_token = Column(String, nullable=True)

    user = relationship("User")


# --------------------------------------------------------------------------
# Jackpot pool
# --------------------------------------------------------------------------

class JackpotRound(Base):
    """A fixed-pool jackpot tied to a card of 10 fights."""
    __tablename__ = "jackpot_rounds"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)  # e.g. "ETFC Aug 27"
    fight_ids = Column(JSON, nullable=False)  # ordered list of 10 fight IDs
    entry_fee = Column(Numeric(14, 2), nullable=False, default=Decimal("30.00"))
    prize_pool = Column(Numeric(14, 2), nullable=False, default=Decimal("1000000.00"))
    min_correct_to_win = Column(Integer, nullable=False, default=9)
    deadline = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(JackpotStatus), nullable=False, default=JackpotStatus.OPEN)
    settled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class JackpotEntry(Base):
    """A user's entry into a jackpot round."""
    __tablename__ = "jackpot_entries"

    id = Column(String, primary_key=True, default=_uuid)
    round_id = Column(String, ForeignKey("jackpot_rounds.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    correct_count = Column(Integer, nullable=False, default=0)
    won = Column(Boolean, nullable=False, default=False)
    payout = Column(Numeric(14, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    round = relationship("JackpotRound")
    user = relationship("User")
    picks = relationship("JackpotPick", back_populates="entry", cascade="all, delete-orphan")


class JackpotPick(Base):
    """One of the 11 picks within an entry."""
    __tablename__ = "jackpot_picks"

    id = Column(String, primary_key=True, default=_uuid)
    entry_id = Column(String, ForeignKey("jackpot_entries.id"), nullable=False)
    fight_id = Column(String, ForeignKey("fights.id"), nullable=False)
    picked_winner_id = Column(String, ForeignKey("fighters.id"), nullable=False)
    is_correct = Column(Boolean, nullable=True)

    entry = relationship("JackpotEntry", back_populates="picks")
    fight = relationship("Fight")
    picked_winner = relationship("Fighter", foreign_keys=[picked_winner_id])


class Withdrawal(Base):
    """A user request to move funds out of the platform to Telebirr."""
    __tablename__ = "withdrawals"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    telebirr_phone = Column(String, nullable=False)
    status = Column(Enum(WithdrawalStatus), nullable=False, default=WithdrawalStatus.PENDING)
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_token = Column(String, nullable=True)

    user = relationship("User")
