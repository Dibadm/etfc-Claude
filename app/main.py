from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.admin_auth import require_admin
from app.config import get_settings
from app.database import Base, engine, get_db
from app.services import betting_service, deposit_service, jackpot_service, odds_service, parlay_service, settlement_service, wallet_service
from app.services.rate_limiter import RateLimiter, get_client_ip
from app.telegram_auth import TelegramUser, get_telegram_user

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ETFC Betting Engine — Phase 1")

# The Mini App is served from a different origin than this API (a static
# host vs. wherever the API is deployed), so the browser needs an explicit
# CORS allow before it'll let the frontend call these endpoints at all —
# without this, every fetch from the Mini App fails silently as a CORS
# error before it even reaches FastAPI's routing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_allow_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting ----------------------------------------------------------
#
# A broad per-IP safety net on every request, plus tighter per-user limits
# on the two endpoints that specifically warrant them: deposit submission
# (each call hits Ethio Telecom's real receipt system — see
# app/services/telebirr_verify.py — so spamming this endpoint doesn't just
# waste our resources, it hammers a third party's server through ours) and
# bet placement (scripted spam risk). See app/services/rate_limiter.py and
# app/admin_auth.py (admin brute-force protection) for the same pattern
# applied elsewhere.

_global_ip_limiter = RateLimiter(max_requests=180, window_seconds=60)
_deposit_limiter = RateLimiter(max_requests=5, window_seconds=3600)
_bet_limiter = RateLimiter(max_requests=20, window_seconds=60)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)
    if not _global_ip_limiter.allow(client_ip):
        retry_after = _global_ip_limiter.retry_after_seconds(client_ip)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    return await call_next(request)


@app.get("/")
def root():
    return {
        "name": "ETFC Betting Engine",
        "status": "/status",
        "docs": "/docs",
        "miniapp_url": get_settings().mini_app_url,
    }


@app.get("/status")
def status():
    settings = get_settings()
    return {
        "wagering_enabled": settings.wagering_enabled,
        "mode": "LIVE — real money" if settings.wagering_enabled else "DEMO — play money only",
        "currency": settings.currency,
        "license_number": settings.license_number or None,
    }


@app.get("/admin/ping")
def admin_ping(_: None = Depends(require_admin)):
    """Cheap admin-auth check that depends on no resource existing —
    unlike hitting a real admin endpoint with a fake id, this can never
    be confused with a 404, so the frontend's login screen can use it to
    mean exactly one thing: is this token valid, yes or no."""
    return {"ok": True}


# --- Fighters -------------------------------------------------------------

@app.post("/fighters", response_model=schemas.FighterOut)
def create_fighter(payload: schemas.FighterCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    fighter = models.Fighter(name=payload.name, nickname=payload.nickname, image_url=payload.image_url)
    db.add(fighter)
    db.commit()
    db.refresh(fighter)
    return fighter


@app.get("/fighters", response_model=list[schemas.FighterOut])
def list_fighters(db: Session = Depends(get_db)):
    return db.query(models.Fighter).order_by(models.Fighter.name).all()


@app.patch("/fighters/{fighter_id}", response_model=schemas.FighterOut)
def update_fighter(
    fighter_id: str,
    payload: schemas.FighterUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    fighter = db.query(models.Fighter).filter(models.Fighter.id == fighter_id).one_or_none()
    if fighter is None:
        raise HTTPException(404, "Fighter not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(fighter, field, value)
    db.commit()
    db.refresh(fighter)
    return fighter


# --- Fights -----------------------------------------------------------------

@app.post("/fights", response_model=schemas.FightOut)
def create_fight(payload: schemas.FightCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    if payload.fighter_a_id == payload.fighter_b_id:
        raise HTTPException(400, "fighter_a_id and fighter_b_id must be different fighters")
    for label, fid in (("fighter_a_id", payload.fighter_a_id), ("fighter_b_id", payload.fighter_b_id)):
        if db.query(models.Fighter).filter(models.Fighter.id == fid).one_or_none() is None:
            raise HTTPException(404, f"No fighter with id {fid} ({label})")
    fight = models.Fight(**payload.model_dump())
    db.add(fight)
    db.commit()
    db.refresh(fight)
    return fight


@app.post("/admin/fights/{fight_id}/set-main-event", response_model=schemas.FightOut)
def set_main_event(
    fight_id: str,
    is_main_event: bool,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """No exclusivity enforced — marking a fight as the main event doesn't
    automatically unmark any other fight on the same card. An admin who
    wants exactly one main event per card is responsible for unmarking
    the old one themselves."""
    fight = db.query(models.Fight).filter(models.Fight.id == fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    fight.is_main_event = is_main_event
    db.commit()
    db.refresh(fight)
    return fight


@app.get("/fights/{fight_id}", response_model=schemas.FightOut)
def get_fight(fight_id: str, db: Session = Depends(get_db)):
    fight = db.query(models.Fight).filter(models.Fight.id == fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    return fight


@app.get("/fights", response_model=list[schemas.FightWithFightersOut])
def list_fights(status: models.FightStatus | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Fight)
    if status is not None:
        query = query.filter(models.Fight.status == status)
    fights = query.order_by(models.Fight.scheduled_at).all()

    results = []
    for fight in fights:
        moneyline = (
            db.query(models.Market)
            .filter(models.Market.fight_id == fight.id, models.Market.market_type == models.MarketType.MONEYLINE)
            .one_or_none()
        )
        odds_a = odds_b = None
        if moneyline is not None:
            for outcome in moneyline.outcomes:
                if outcome.fighter_id == fight.fighter_a_id:
                    odds_a = outcome.odds
                elif outcome.fighter_id == fight.fighter_b_id:
                    odds_b = outcome.odds
        item = schemas.FightWithFightersOut.model_validate(fight)
        item.moneyline_odds_a = odds_a
        item.moneyline_odds_b = odds_b
        results.append(item)
    return results


@app.post("/fights/{fight_id}/settle", response_model=schemas.FightOut)
def settle_fight(
    fight_id: str,
    payload: schemas.SettleFightRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    fight = db.query(models.Fight).filter(models.Fight.id == fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    try:
        return settlement_service.settle_fight(
            db, fight, payload.winner_fighter_id, payload.result_method, payload.result_round
        )
    except settlement_service.AlreadySettledError as e:
        raise HTTPException(409, str(e))


@app.post("/fights/{fight_id}/void", response_model=schemas.FightOut)
def void_fight(fight_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    fight = db.query(models.Fight).filter(models.Fight.id == fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    try:
        return settlement_service.void_fight(db, fight)
    except settlement_service.AlreadySettledError as e:
        raise HTTPException(409, str(e))


# --- Markets ----------------------------------------------------------------

@app.post("/markets/moneyline", response_model=schemas.MarketOut)
def create_moneyline_market(
    payload: schemas.MoneylineMarketCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    fight = db.query(models.Fight).filter(models.Fight.id == payload.fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    try:
        return odds_service.create_moneyline_market(db, fight, payload.odds_fighter_a, payload.odds_fighter_b)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A moneyline market already exists for this fight")


@app.post("/markets/method-of-victory", response_model=schemas.MarketOut)
def create_method_of_victory_market(
    payload: schemas.MethodOfVictoryMarketCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    fight = db.query(models.Fight).filter(models.Fight.id == payload.fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    odds_by_method = {
        models.VictoryMethod.KO_TKO: payload.odds_ko_tko,
        models.VictoryMethod.SUBMISSION: payload.odds_submission,
        models.VictoryMethod.DECISION: payload.odds_decision,
    }
    try:
        return odds_service.create_method_of_victory_market(db, fight, odds_by_method)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A method-of-victory market already exists for this fight")


@app.post("/markets/round-prop", response_model=schemas.MarketOut)
def create_round_prop_market(
    payload: schemas.RoundPropMarketCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    fight = db.query(models.Fight).filter(models.Fight.id == payload.fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")
    try:
        return odds_service.create_round_prop_market(
            db, fight, payload.odds_by_round, payload.odds_goes_the_distance, payload.total_rounds
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A round-prop market already exists for this fight")


_MARKET_TYPE_DISPLAY_ORDER = {
    models.MarketType.MONEYLINE: 0,
    models.MarketType.METHOD_OF_VICTORY: 1,
    models.MarketType.ROUND_PROP: 2,
}


@app.get("/fights/{fight_id}/markets", response_model=list[schemas.MarketOut])
def list_markets_for_fight(fight_id: str, db: Session = Depends(get_db)):
    markets = db.query(models.Market).filter(models.Market.fight_id == fight_id).all()
    # Moneyline (who wins — the primary decision) always leads, regardless
    # of the order markets happened to be created in.
    return sorted(markets, key=lambda m: _MARKET_TYPE_DISPLAY_ORDER.get(m.market_type, 99))


@app.post("/admin/markets/{market_id}/suspend", response_model=schemas.MarketOut)
def suspend_market(market_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    market = db.query(models.Market).filter(models.Market.id == market_id).one_or_none()
    if market is None:
        raise HTTPException(404, "Market not found")
    try:
        return odds_service.suspend_market(db, market)
    except odds_service.MarketAlreadyFinalizedError as e:
        raise HTTPException(409, str(e))


@app.post("/admin/markets/{market_id}/reopen", response_model=schemas.MarketOut)
def reopen_market(market_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    market = db.query(models.Market).filter(models.Market.id == market_id).one_or_none()
    if market is None:
        raise HTTPException(404, "Market not found")
    try:
        return odds_service.reopen_market(db, market)
    except odds_service.MarketAlreadyFinalizedError as e:
        raise HTTPException(409, str(e))


@app.post("/admin/outcomes/{outcome_id}/odds", response_model=schemas.MarketOutcomeOut)
def update_outcome_odds(
    outcome_id: str,
    payload: schemas.OddsUpdateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    outcome = db.query(models.MarketOutcome).filter(models.MarketOutcome.id == outcome_id).one_or_none()
    if outcome is None:
        raise HTTPException(404, "Outcome not found")
    return odds_service.update_outcome_odds(db, outcome, payload.new_odds)


@app.get("/admin/fights/{fight_id}/liability", response_model=list[schemas.LiabilityMarket])
def fight_liability(fight_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Per-outcome exposure: if this outcome wins, how much does the house
    owe across every currently-pending bet on it? Settled/void bets don't
    carry forward exposure, so only PENDING bets are counted."""
    fight = db.query(models.Fight).filter(models.Fight.id == fight_id).one_or_none()
    if fight is None:
        raise HTTPException(404, "Fight not found")

    markets = db.query(models.Market).filter(models.Market.fight_id == fight_id).all()
    result = []
    for market in sorted(markets, key=lambda m: _MARKET_TYPE_DISPLAY_ORDER.get(m.market_type, 99)):
        outcomes_out = []
        for outcome in market.outcomes:
            pending_bets = (
                db.query(models.Bet)
                .filter(models.Bet.outcome_id == outcome.id, models.Bet.status == models.BetStatus.PENDING)
                .all()
            )
            outcomes_out.append(
                schemas.LiabilityOutcome(
                    outcome_id=outcome.id,
                    label=outcome.label,
                    odds=outcome.odds,
                    pending_bet_count=len(pending_bets),
                    total_stake=sum((b.stake for b in pending_bets), Decimal("0.00")),
                    total_potential_payout=sum((b.potential_payout for b in pending_bets), Decimal("0.00")),
                )
            )
        result.append(
            schemas.LiabilityMarket(
                market_id=market.id,
                market_type=market.market_type,
                market_status=market.status,
                outcomes=outcomes_out,
            )
        )
    return result


# --- Users / wallets ----------------------------------------------------

@app.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    user = wallet_service.create_user_with_wallet(db, payload.telegram_id, payload.username)
    return user


@app.get("/users/{user_id}/wallet", response_model=schemas.WalletOut)
def get_wallet(user_id: str, db: Session = Depends(get_db)):
    wallet = db.query(models.Wallet).filter(models.Wallet.user_id == user_id).one_or_none()
    if wallet is None:
        raise HTTPException(404, "Wallet not found")
    return wallet


# --- Betting ------------------------------------------------------------

@app.post("/bets", response_model=schemas.BetOut)
def place_bet(payload: schemas.BetCreate, db: Session = Depends(get_db)):
    try:
        return betting_service.place_bet(db, payload.user_id, payload.outcome_id, payload.stake)
    except betting_service.MarketNotOpenError as e:
        raise HTTPException(409, str(e))
    except wallet_service.InsufficientFundsError as e:
        raise HTTPException(402, str(e))
    except betting_service.InvalidStakeError as e:
        raise HTTPException(400, str(e))
    except betting_service.OutcomeNotFoundError as e:
        raise HTTPException(404, str(e))
    except betting_service.UserNotFoundError as e:
        raise HTTPException(404, str(e))
    except wallet_service.WalletNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/users/{user_id}/bets", response_model=list[schemas.BetOut])
def list_bets_for_user(user_id: str, db: Session = Depends(get_db)):
    return db.query(models.Bet).filter(models.Bet.user_id == user_id).all()


# --- Mini App (Telegram-authenticated) -----------------------------------
#
# Everything below identifies "the current user" from validated Telegram
# initData (see app/telegram_auth.py) rather than trusting a client-supplied
# user_id. This is what the React Mini App actually talks to. The endpoints
# above stay as-is for internal testing/tooling — nothing about them changed.

@app.get("/miniapp/me", response_model=schemas.UserOut)
def miniapp_me(
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    return user


@app.post("/miniapp/bets", response_model=schemas.BetOut)
def miniapp_place_bet(
    payload: schemas.MiniAppBetCreate,
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    if not _bet_limiter.allow(user.id):
        raise HTTPException(
            429,
            "Too many bets placed too quickly. Please slow down.",
            headers={"Retry-After": str(int(_bet_limiter.retry_after_seconds(user.id)) + 1)},
        )
    try:
        return betting_service.place_bet(db, user.id, payload.outcome_id, payload.stake)
    except betting_service.MarketNotOpenError as e:
        raise HTTPException(409, str(e))
    except wallet_service.InsufficientFundsError as e:
        raise HTTPException(402, str(e))
    except betting_service.InvalidStakeError as e:
        raise HTTPException(400, str(e))
    except betting_service.OutcomeNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/miniapp/bets", response_model=list[schemas.BetOut])
def miniapp_list_my_bets(
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    return db.query(models.Bet).filter(models.Bet.user_id == user.id).order_by(models.Bet.placed_at.desc()).all()


@app.post("/miniapp/parlays", response_model=schemas.ParlayOut)
def miniapp_place_parlay(
    payload: schemas.ParlayCreate,
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    # Same abuse shape as single-bet placement — counts against the same budget.
    if not _bet_limiter.allow(user.id):
        raise HTTPException(
            429,
            "Too many bets placed too quickly. Please slow down.",
            headers={"Retry-After": str(int(_bet_limiter.retry_after_seconds(user.id)) + 1)},
        )
    try:
        return parlay_service.place_parlay(db, user.id, payload.outcome_ids, payload.stake)
    except parlay_service.TooFewLegsError as e:
        raise HTTPException(400, str(e))
    except parlay_service.TooManyLegsError as e:
        raise HTTPException(400, str(e))
    except parlay_service.DuplicateLegError as e:
        raise HTTPException(400, str(e))
    except parlay_service.CorrelatedLegsError as e:
        raise HTTPException(400, str(e))
    except betting_service.MarketNotOpenError as e:
        raise HTTPException(409, str(e))
    except wallet_service.InsufficientFundsError as e:
        raise HTTPException(402, str(e))
    except betting_service.InvalidStakeError as e:
        raise HTTPException(400, str(e))
    except betting_service.OutcomeNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/miniapp/parlays", response_model=list[schemas.ParlayOut])
def miniapp_list_my_parlays(
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    return (
        db.query(models.Parlay)
        .filter(models.Parlay.user_id == user.id)
        .order_by(models.Parlay.placed_at.desc())
        .all()
    )


@app.get("/miniapp/deposit-account", response_model=schemas.DepositAccountOut)
def miniapp_get_deposit_account(
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    """Which Telebirr number to send money to right now — this rotates
    (see deposit_service._rotate_if_needed), so the frontend should call
    this fresh each time the deposit screen opens rather than caching it."""
    try:
        return deposit_service.get_active_deposit_account(db)
    except deposit_service.NoActiveDepositAccountError as e:
        raise HTTPException(503, str(e))


@app.post("/miniapp/deposit", response_model=schemas.UserOut)
def miniapp_submit_deposit(
    payload: schemas.DepositSmsSubmit,
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    if not user.phone:
        raise HTTPException(403, "Please verify your phone number in the bot before depositing.")
    if not _deposit_limiter.allow(user.id):
        raise HTTPException(
            429,
            "Too many deposit attempts. Please wait a while before trying again, or contact support.",
            headers={"Retry-After": str(int(_deposit_limiter.retry_after_seconds(user.id)) + 1)},
        )
    try:
        deposit_service.submit_deposit_sms(
            db, user.id, payload.sms_text, payload.expected_amount, payload.idempotency_key
        )
    except deposit_service.DepositReviewRequiredError as e:
        db.rollback()
        return JSONResponse(status_code=200, content={"status": "under_review", "review_id": e.review_id, "message": str(e)})
    except wallet_service.WageringDisabledError as e:
        raise HTTPException(403, str(e))
    except deposit_service.NoActiveDepositAccountError as e:
        raise HTTPException(503, str(e))
    except deposit_service.InvalidSmsError as e:
        raise HTTPException(400, str(e))
    except deposit_service.WrongAccountError as e:
        raise HTTPException(400, str(e))
    except deposit_service.DuplicateReferenceError as e:
        raise HTTPException(409, str(e))
    except deposit_service.ReceiptVerificationFailedError as e:
        raise HTTPException(422, str(e))
    except deposit_service.AmountMismatchError as e:
        raise HTTPException(400, str(e))
    db.refresh(user)
    return user


# --- Admin: rotating Telebirr deposit accounts ------------------------------

@app.get("/admin/deposit-accounts", response_model=list[schemas.DepositAccountOut])
def admin_list_deposit_accounts(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return deposit_service.list_deposit_accounts(db)


@app.post("/admin/deposit-accounts", response_model=schemas.DepositAccountOut)
def admin_add_deposit_account(
    payload: schemas.DepositAccountCreate, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    return deposit_service.add_deposit_account(db, payload.phone, payload.recipient_name)


@app.delete("/admin/deposit-accounts/{account_id}", status_code=204)
def admin_remove_deposit_account(account_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    try:
        deposit_service.remove_deposit_account(db, account_id)
    except deposit_service.DepositAccountNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/admin/deposit-accounts/{account_id}/activate", response_model=schemas.DepositAccountOut)
def admin_activate_deposit_account(account_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    try:
        return deposit_service.set_deposit_account_active(db, account_id, True)
    except deposit_service.DepositAccountNotFoundError as e:
        raise HTTPException(404, str(e))


# --- Admin: deposit review queue -------------------------------------------

@app.get("/admin/deposit-reviews", response_model=list[schemas.DepositReviewOut])
def admin_list_deposit_reviews(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    review_status = None
    if status is not None:
        try:
            from app.models import DepositReviewStatus
            review_status = DepositReviewStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    return [
        schemas.DepositReviewOut(
            id=r.id,
            user_id=r.user_id,
            amount=r.amount,
            reference=r.reference,
            sms_text=r.sms_text,
            verification_error=r.verification_error,
            status=r.status.value,
            created_at=r.created_at,
            reviewed_at=r.reviewed_at,
            reviewer_token=r.reviewer_token,
        )
        for r in deposit_service.list_deposit_reviews(db, review_status)
    ]


@app.post("/admin/deposit-reviews/{review_id}/approve", response_model=schemas.DepositReviewOut)
def admin_approve_deposit_review(
    review_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        review = deposit_service.approve_deposit_review(db, review_id)
    except deposit_service.DepositAccountNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return schemas.DepositReviewOut(
        id=review.id,
        user_id=review.user_id,
        amount=review.amount,
        reference=review.reference,
        sms_text=review.sms_text,
        verification_error=review.verification_error,
        status=review.status.value,
        created_at=review.created_at,
        reviewed_at=review.reviewed_at,
        reviewer_token=review.reviewer_token,
    )


@app.post("/admin/deposit-reviews/{review_id}/reject", response_model=schemas.DepositReviewOut)
def admin_reject_deposit_review(
    review_id: str,
    payload: schemas.DepositReviewReject,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        review = deposit_service.reject_deposit_review(db, review_id)
    except deposit_service.DepositAccountNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return schemas.DepositReviewOut(
        id=review.id,
        user_id=review.user_id,
        amount=review.amount,
        reference=review.reference,
        sms_text=review.sms_text,
        verification_error=review.verification_error,
        status=review.status.value,
        created_at=review.created_at,
        reviewed_at=review.reviewed_at,
        reviewer_token=review.reviewer_token,
    )


# --- Jackpot pool -----------------------------------------------------------
#
# A fixed-pool game tied to a card of 10 fights. Users pay an entry fee
# (default 30 ETB), pick one winner per fight, and anyone with 9+ correct
# shares the prize pool (default 1M ETB). Picks lock at the deadline
# (default: earliest fight scheduled_at). Settlement runs once after all
# 10 fights are marked completed.

@app.get("/jackpot/rounds", response_model=list[schemas.JackpotRoundOut])
def list_jackpot_rounds(db: Session = Depends(get_db)):
    rounds = jackpot_service.list_rounds(db)
    result = []
    for r in rounds:
        fights = db.query(models.Fight).filter(models.Fight.id.in_(r.fight_ids)).all() if r.fight_ids else []
        fight_map = {f.id: f for f in fights}
        ordered_fights = [fight_map[fid] for fid in r.fight_ids if fid in fight_map]
        result.append(
            schemas.JackpotRoundOut(
                id=r.id,
                name=r.name,
                fight_ids=r.fight_ids,
                entry_fee=r.entry_fee,
                prize_pool=r.prize_pool,
                min_correct_to_win=r.min_correct_to_win,
                deadline=r.deadline,
                status=r.status.value,
                settled_at=r.settled_at,
                created_at=r.created_at,
                fights=[
                    {
                        "id": f.id,
                        "event_name": f.event_name,
                        "fighter_a": {"name": f.fighter_a.name, "nickname": f.fighter_a.nickname},
                        "fighter_b": {"name": f.fighter_b.name, "nickname": f.fighter_b.nickname},
                    }
                    for f in ordered_fights
                ],
            )
        )
    return result


@app.get("/jackpot/rounds/{round_id}", response_model=schemas.JackpotRoundOut)
def get_jackpot_round(round_id: str, db: Session = Depends(get_db)):
    r = jackpot_service.get_round(db, round_id)
    fights = db.query(models.Fight).filter(models.Fight.id.in_(r.fight_ids)).all() if r.fight_ids else []
    fight_map = {f.id: f for f in fights}
    ordered_fights = [fight_map[fid] for fid in r.fight_ids if fid in fight_map]
    return schemas.JackpotRoundOut(
        id=r.id,
        name=r.name,
        fight_ids=r.fight_ids,
        entry_fee=r.entry_fee,
        prize_pool=r.prize_pool,
        min_correct_to_win=r.min_correct_to_win,
        deadline=r.deadline,
        status=r.status.value,
        settled_at=r.settled_at,
        created_at=r.created_at,
        fights=[
            {
                "id": f.id,
                "event_name": f.event_name,
                "fighter_a": {"name": f.fighter_a.name, "nickname": f.fighter_a.nickname},
                "fighter_b": {"name": f.fighter_b.name, "nickname": f.fighter_b.nickname},
            }
            for f in ordered_fights
        ],
    )


@app.post("/miniapp/jackpot/entries", response_model=schemas.JackpotEntryOut)
def miniapp_create_jackpot_entry(
    payload: schemas.JackpotEntrySubmit,
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    try:
        entry = jackpot_service.submit_entry(db, user.id, payload.round_id, payload.picks)
    except jackpot_service.RoundNotFoundError as e:
        raise HTTPException(404, str(e))
    except jackpot_service.RoundNotOpenError as e:
        raise HTTPException(409, str(e))
    except jackpot_service.MissingPicksError as e:
        raise HTTPException(400, str(e))
    except jackpot_service.DuplicateEntryError as e:
        raise HTTPException(409, str(e))
    except wallet_service.InsufficientFundsError:
        raise HTTPException(402, "Insufficient balance for jackpot entry fee.")

    picks_out = [
        schemas.JackpotPickOut(
            id=p.id,
            fight_id=p.fight_id,
            picked_winner_id=p.picked_winner_id,
            is_correct=p.is_correct,
        )
        for p in entry.picks
    ]
    return schemas.JackpotEntryOut(
        id=entry.id,
        round_id=entry.round_id,
        user_id=entry.user_id,
        correct_count=entry.correct_count,
        won=entry.won,
        payout=entry.payout,
        created_at=entry.created_at,
        picks=picks_out,
    )


@app.get("/miniapp/jackpot/entries/me", response_model=list[schemas.JackpotEntryOut])
def miniapp_list_my_jackpot_entries(
    tg_user: TelegramUser = Depends(get_telegram_user),
    db: Session = Depends(get_db),
):
    user = wallet_service.get_or_create_user_by_telegram_id(db, tg_user.telegram_id, tg_user.username)
    entries = db.query(JackpotEntry).filter(JackpotEntry.user_id == user.id).all()
    result = []
    for entry in entries:
        picks_out = [
            schemas.JackpotPickOut(
                id=p.id,
                fight_id=p.fight_id,
                picked_winner_id=p.picked_winner_id,
                is_correct=p.is_correct,
            )
            for p in entry.picks
        ]
        result.append(
            schemas.JackpotEntryOut(
                id=entry.id,
                round_id=entry.round_id,
                user_id=entry.user_id,
                correct_count=entry.correct_count,
                won=entry.won,
                payout=entry.payout,
                created_at=entry.created_at,
                picks=picks_out,
            )
        )
    return result


# --- Admin: jackpot management ----------------------------------------------

@app.post("/admin/jackpot/rounds", response_model=schemas.JackpotRoundOut)
def admin_create_jackpot_round(
    payload: schemas.JackpotRoundCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        round_ = jackpot_service.create_round(
            db,
            name=payload.name,
            fight_ids=payload.fight_ids,
            entry_fee=payload.entry_fee,
            prize_pool=payload.prize_pool,
            min_correct_to_win=payload.min_correct_to_win,
            deadline=payload.deadline,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return schemas.JackpotRoundOut(
        id=round_.id,
        name=round_.name,
        fight_ids=round_.fight_ids,
        entry_fee=round_.entry_fee,
        prize_pool=round_.prize_pool,
        min_correct_to_win=round_.min_correct_to_win,
        deadline=round_.deadline,
        status=round_.status.value,
        settled_at=round_.settled_at,
        created_at=round_.created_at,
    )


@app.post("/admin/jackpot/rounds/{round_id}/settle", response_model=schemas.JackpotRoundOut)
def admin_settle_jackpot_round(
    round_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        round_ = jackpot_service.settle_round(db, round_id)
    except (jackpot_service.RoundNotFoundError, jackpot_service.RoundAlreadySettledError, jackpot_service.RoundNotOpenError) as e:
        raise HTTPException(400, str(e))
    return schemas.JackpotRoundOut(
        id=round_.id,
        name=round_.name,
        fight_ids=round_.fight_ids,
        entry_fee=round_.entry_fee,
        prize_pool=round_.prize_pool,
        min_correct_to_win=round_.min_correct_to_win,
        deadline=round_.deadline,
        status=round_.status.value,
        settled_at=round_.settled_at,
        created_at=round_.created_at,
    )


@app.get("/admin/jackpot/rounds/{round_id}/entries", response_model=list[schemas.JackpotEntryOut])
def admin_list_jackpot_entries(round_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    try:
        jackpot_service.get_round(db, round_id)
    except jackpot_service.RoundNotFoundError as e:
        raise HTTPException(404, str(e))
    entries = jackpot_service.list_entries(db, round_id)
    result = []
    for entry in entries:
        picks_out = [
            schemas.JackpotPickOut(
                id=p.id,
                fight_id=p.fight_id,
                picked_winner_id=p.picked_winner_id,
                is_correct=p.is_correct,
            )
            for p in entry.picks
        ]
        result.append(
            schemas.JackpotEntryOut(
                id=entry.id,
                round_id=entry.round_id,
                user_id=entry.user_id,
                correct_count=entry.correct_count,
                won=entry.won,
                payout=entry.payout,
                created_at=entry.created_at,
                picks=picks_out,
            )
        )
    return result


# --- Frontend SPA serving ---------------------------------------------------
#
# Both the Mini App and Admin panel are built as static SPAs during the
# Render build step and served from this same process so a single service
# handles API, bot, and frontends. Assets are mounted statically; all
# non-file routes fall back to index.html for client-side routing.

_miniapp_dist = Path("miniapp/dist")
_admin_dist = Path("admin/dist")

if _miniapp_dist.exists():
    app.mount("/app/assets", StaticFiles(directory=_miniapp_dist / "assets"), name="miniapp-static")

    @app.get("/app")
    @app.get("/app/{full_path:path}")
    async def serve_miniapp(request: Request, full_path: str = ""):
        file_path = _miniapp_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_miniapp_dist / "index.html")

if _admin_dist.exists():
    app.mount("/panel/assets", StaticFiles(directory=_admin_dist / "assets"), name="admin-static")

    @app.get("/panel")
    @app.get("/panel/{full_path:path}")
    async def serve_admin(request: Request, full_path: str = ""):
        file_path = _admin_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_admin_dist / "index.html")
