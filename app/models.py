import enum
import uuid
from datetime import datetime, timezone

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
    MONEYLINE = "moneyline"                 # who wins the fight
    METHOD_OF_VICTORY = "method_of_victory"  # KO/TKO, submission, decision
    ROUND_PROP = "round_prop"                # which round it ends in / distance


class MarketStatus(str, enum.Enum):
    OPEN = "open"
    SUSPENDED = "suspended"   # temporarily not accepting bets, e.g. news breaks
    SETTLED = "settled"
    VOID = "void"             # fight cancelled etc. — all bets refunded


class BetStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"       # market voided -> stake refunded
    REFUNDED = "refunded"


class ParlayStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"        # every leg voided -> stake refunded, not a win


class ParlayLegStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"         # that leg's fight was cancelled — excluded from payout math, doesn't sink the ticket


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DEMO_CREDIT = "demo_credit"
    BET_HOLD = "bet_hold"
    BET_PAYOUT = "bet_payout"
    BET_REFUND = "bet_refund"


# --------------------------------------------------------------------------
# Users / wallets
# --------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    telegram_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
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
    amount = Column(Numeric(14, 2), nullable=False)          # signed: + credit, - debit
    balance_after = Column(Numeric(14, 2), nullable=False)
    reference = Column(String, nullable=True)                 # e.g. bet id, deposit ref
    created_at = Column(DateTime(timezone=True), default=_now)

    wallet = relationship("Wallet", back_populates="transactions")

    __table_args__ = (
        # Guards the exact race deposit_service.reference_already_used()'s
        # plain SELECT check can't close on its own: two concurrent
        # submissions of the same Telebirr SMS could both pass that check
        # before either commits, on Postgres. This is the actual backstop;
        # the application-level check just gives a friendlier error first.
        # Scoped to deposits only — `reference` isn't meant to be globally
        # unique (every user's demo-credit row shares the literal string
        # "signup_demo_seed"; a single bet's hold/payout/refund rows all
        # share that bet's id as their reference, across three DIFFERENT
        # types).
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
    event_name = Column(String, nullable=False)      # e.g. "ETFC 11"
    weight_class = Column(String, nullable=True)
    fighter_a_id = Column(String, ForeignKey("fighters.id"), nullable=False)
    fighter_b_id = Column(String, ForeignKey("fighters.id"), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(FightStatus), nullable=False, default=FightStatus.SCHEDULED)
    is_main_event = Column(Boolean, nullable=False, default=False)

    # Result fields — populated only at settlement time.
    winner_fighter_id = Column(String, ForeignKey("fighters.id"), nullable=True)
    result_method = Column(Enum(VictoryMethod), nullable=True)
    result_round = Column(Integer, nullable=True)   # 1, 2, 3... null if decision

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
    """
    A single selectable outcome within a market, with its current price.

    Odds are stored in DECIMAL format (e.g. 2.50 means a 10 ETB stake
    returns 25 ETB total if it wins, i.e. potential_payout = stake * odds).
    Decimal odds are used because the payout math is a single
    multiplication — simplest to get right for a from-scratch engine,
    and it's the format most bettors outside the US already read.
    """
    __tablename__ = "market_outcomes"

    id = Column(String, primary_key=True, default=_uuid)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    label = Column(String, nullable=False)   # "Fighter A", "KO/TKO", "Round 2", "Goes the Distance"
    odds = Column(Numeric(6, 2), nullable=False)

    # Settlement-matching keys — how we figure out which outcome(s) won
    # without parsing free-text labels. Exactly the relevant one(s) are
    # set per market_type; the rest stay null.
    fighter_id = Column(String, ForeignKey("fighters.id"), nullable=True)       # moneyline
    victory_method = Column(Enum(VictoryMethod), nullable=True)                  # method_of_victory
    round_number = Column(Integer, nullable=True)                                # round_prop (null = "goes the distance")

    is_winning_outcome = Column(Boolean, nullable=True)  # set at settlement

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
    odds_at_placement = Column(Numeric(6, 2), nullable=False)   # snapshot, immune to later odds moves
    potential_payout = Column(Numeric(14, 2), nullable=False)   # stake * odds_at_placement

    status = Column(Enum(BetStatus), nullable=False, default=BetStatus.PENDING)
    placed_at = Column(DateTime(timezone=True), default=_now)
    settled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="bets")
    market = relationship("Market")
    outcome = relationship("MarketOutcome")


# --------------------------------------------------------------------------
# Parlays (multi-fight tickets) — a single wager combining selections from
# several DIFFERENT fights. All legs must win for the ticket to pay out;
# combined odds are the product of each leg's odds. See
# app/services/parlay_service.py for placement and settlement_service.py
# for how legs resolve as their individual fights get settled.
# --------------------------------------------------------------------------

class Parlay(Base):
    __tablename__ = "parlays"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    stake = Column(Numeric(14, 2), nullable=False)
    # Product of every leg's odds at placement — the full potential payout
    # multiplier if every leg wins. Used for display/liability; the actual
    # settlement payout is recomputed from won legs only if any leg voids
    # (a voided leg is excluded, not treated as a loss — see settlement_service).
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
    # Denormalized from market.fight_id — settlement needs to find "every
    # pending leg touching this fight" by fight id, on every fight
    # settlement, so storing it directly avoids a join for that lookup.
    fight_id = Column(String, ForeignKey("fights.id"), nullable=False)

    odds_at_placement = Column(Numeric(6, 2), nullable=False)
    status = Column(Enum(ParlayLegStatus), nullable=False, default=ParlayLegStatus.PENDING)

    parlay = relationship("Parlay", back_populates="legs")
    market = relationship("Market")
    outcome = relationship("MarketOutcome")
    fight = relationship("Fight")


# --------------------------------------------------------------------------
# Telebirr deposit accounts (rotating receiving numbers)
# --------------------------------------------------------------------------

class DepositAccount(Base):
    """A Telebirr phone number that can receive user deposits. Only one is
    `active` at a time — that's the number shown to users. Deposits rotate
    round-robin to the next account after `ETFC_ROTATE_AFTER_DEPOSITS`
    successful deposits on the current one (ported from Habesha Bet's
    same pattern — see app/services/telebirr_verify.py)."""
    __tablename__ = "deposit_accounts"

    id = Column(String, primary_key=True, default=_uuid)
    phone = Column(String, nullable=False)
    recipient_name = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    deposit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
