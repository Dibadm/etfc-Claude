from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import models
from app.database import SessionLocal
from app.services import betting_service, odds_service, settlement_service, wallet_service
from tests.conftest import make_fighter, make_user


def db():
    return SessionLocal()


def create_fight(client, fighter_a_id, fighter_b_id, event_name="ETFC 11"):
    r = client.post(
        "/fights",
        json={
            "event_name": event_name,
            "weight_class": "Lightweight",
            "fighter_a_id": fighter_a_id,
            "fighter_b_id": fighter_b_id,
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def wallet_balance(client, user_id):
    r = client.get(f"/users/{user_id}/wallet")
    assert r.status_code == 200
    return Decimal(r.json()["balance"])


def ledger_sum_matches_balance(user_id):
    session = db()
    try:
        wallet = session.query(models.Wallet).filter(models.Wallet.user_id == user_id).one()
        total = sum(
            (t.amount for t in session.query(models.WalletTransaction).filter(
                models.WalletTransaction.wallet_id == wallet.id
            )),
            Decimal("0.00"),
        )
        return total == wallet.balance
    finally:
        session.close()


# --------------------------------------------------------------------------
# Signup / demo mode
# --------------------------------------------------------------------------

def test_new_user_gets_demo_balance_while_wagering_disabled(client):
    user = make_user(client, "tg_1")
    assert user["is_demo_account"] is True
    assert Decimal(user["wallet"]["balance"]) == Decimal("1000.00")
    assert ledger_sum_matches_balance(user["id"])


def test_real_deposit_blocked_while_wagering_disabled(client):
    user = make_user(client, "tg_2")
    session = db()
    try:
        with pytest.raises(wallet_service.WageringDisabledError):
            wallet_service.deposit_real_funds(session, user["id"], Decimal("500.00"), reference="telebirr_ref_1")
    finally:
        session.close()


# --------------------------------------------------------------------------
# Moneyline market: full bet -> settle -> payout cycle
# --------------------------------------------------------------------------

def test_moneyline_win_pays_out_and_loss_does_not(client):
    fa = make_fighter(client, "Biniyam Tesfaye")
    fb = make_fighter(client, "Girma Wolde")
    fight = create_fight(client, fa["id"], fb["id"])

    r = client.post(
        "/markets/moneyline",
        json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.10"},
    )
    assert r.status_code == 200, r.text
    market = r.json()
    outcome_a = next(o for o in market["outcomes"] if o["label"] == "Biniyam Tesfaye")
    outcome_b = next(o for o in market["outcomes"] if o["label"] == "Girma Wolde")

    backer_of_a = make_user(client, "tg_backer_a")
    backer_of_b = make_user(client, "tg_backer_b")

    bet_a = client.post(
        "/bets", json={"user_id": backer_of_a["id"], "outcome_id": outcome_a["id"], "stake": "100.00"}
    ).json()
    bet_b = client.post(
        "/bets", json={"user_id": backer_of_b["id"], "outcome_id": outcome_b["id"], "stake": "100.00"}
    ).json()

    assert Decimal(bet_a["potential_payout"]) == Decimal("180.00")
    assert wallet_balance(client, backer_of_a["id"]) == Decimal("900.00")  # 1000 - 100 stake

    # Fighter A wins by decision
    r = client.post(
        f"/fights/{fight['id']}/settle",
        json={"winner_fighter_id": fa["id"], "result_method": "decision"},
    )
    assert r.status_code == 200, r.text

    assert client.get(f"/users/{backer_of_a['id']}/bets").json()[0]["status"] == "won"
    assert client.get(f"/users/{backer_of_b['id']}/bets").json()[0]["status"] == "lost"

    # Winner: 900 (after stake) + 180 payout = 1080. Loser stays at 900 (stake already gone, no payout).
    assert wallet_balance(client, backer_of_a["id"]) == Decimal("1080.00")
    assert wallet_balance(client, backer_of_b["id"]) == Decimal("900.00")
    assert ledger_sum_matches_balance(backer_of_a["id"])
    assert ledger_sum_matches_balance(backer_of_b["id"])


# --------------------------------------------------------------------------
# Method of victory + round prop, settled off the same fight result
# --------------------------------------------------------------------------

def test_method_of_victory_and_round_prop_settle_together(client):
    fa = make_fighter(client, "Abel Kebede")
    fb = make_fighter(client, "Yonas Alemu")
    fight = create_fight(client, fa["id"], fb["id"])

    mov = client.post(
        "/markets/method-of-victory",
        json={"fight_id": fight["id"], "odds_ko_tko": "2.50", "odds_submission": "4.00", "odds_decision": "2.20"},
    ).json()
    rp = client.post(
        "/markets/round-prop",
        json={
            "fight_id": fight["id"],
            "total_rounds": 3,
            "odds_by_round": {"1": "4.50", "2": "5.00", "3": "3.50"},
            "odds_goes_the_distance": "2.00",
        },
    ).json()

    ko_outcome = next(o for o in mov["outcomes"] if o["label"] == "KO/TKO")
    round2_outcome = next(o for o in rp["outcomes"] if o["label"] == "Round 2")
    distance_outcome = next(o for o in rp["outcomes"] if o["label"] == "Goes the Distance")

    ko_bettor = make_user(client, "tg_ko")
    round2_bettor = make_user(client, "tg_round2")
    distance_bettor = make_user(client, "tg_distance")

    client.post("/bets", json={"user_id": ko_bettor["id"], "outcome_id": ko_outcome["id"], "stake": "50.00"})
    client.post("/bets", json={"user_id": round2_bettor["id"], "outcome_id": round2_outcome["id"], "stake": "50.00"})
    client.post("/bets", json={"user_id": distance_bettor["id"], "outcome_id": distance_outcome["id"], "stake": "50.00"})

    # Fight actually ends via KO/TKO in round 2
    r = client.post(
        f"/fights/{fight['id']}/settle",
        json={"winner_fighter_id": fa["id"], "result_method": "ko_tko", "result_round": 2},
    )
    assert r.status_code == 200, r.text

    assert wallet_balance(client, ko_bettor["id"]) == Decimal("1000.00") - Decimal("50.00") + Decimal("125.00")
    assert wallet_balance(client, round2_bettor["id"]) == Decimal("1000.00") - Decimal("50.00") + Decimal("250.00")
    # Distance bettor loses — fight did not go the distance
    assert wallet_balance(client, distance_bettor["id"]) == Decimal("950.00")


# --------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------

def test_insufficient_funds_rejected_and_no_side_effects(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"}
    ).json()
    outcome_a = market["outcomes"][0]

    user = make_user(client, "tg_poor")
    r = client.post("/bets", json={"user_id": user["id"], "outcome_id": outcome_a["id"], "stake": "5000.00"})
    assert r.status_code == 402

    assert wallet_balance(client, user["id"]) == Decimal("1000.00")  # untouched
    assert client.get(f"/users/{user['id']}/bets").json() == []


def test_bet_rejected_when_market_suspended(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market_resp = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"}
    ).json()

    session = db()
    try:
        market_row = session.query(models.Market).filter(models.Market.id == market_resp["id"]).one()
        odds_service.suspend_market(session, market_row)
    finally:
        session.close()

    user = make_user(client, "tg_suspended_market")
    r = client.post(
        "/bets", json={"user_id": user["id"], "outcome_id": market_resp["outcomes"][0]["id"], "stake": "10.00"}
    )
    assert r.status_code == 409


def test_void_fight_refunds_all_pending_stakes(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"}
    ).json()
    user = make_user(client, "tg_void")
    client.post("/bets", json={"user_id": user["id"], "outcome_id": market["outcomes"][0]["id"], "stake": "200.00"})
    assert wallet_balance(client, user["id"]) == Decimal("800.00")

    r = client.post(f"/fights/{fight['id']}/void")
    assert r.status_code == 200, r.text

    assert wallet_balance(client, user["id"]) == Decimal("1000.00")  # fully refunded
    assert client.get(f"/users/{user['id']}/bets").json()[0]["status"] == "void"


def test_cannot_settle_same_fight_twice(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"})

    r1 = client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})
    assert r1.status_code == 200
    r2 = client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})
    assert r2.status_code == 409


def test_cannot_settle_a_voided_fight(client):
    """A voided fight's markets are already refunded and closed. Settling
    it afterward would overwrite CANCELLED with a fake COMPLETED-plus-
    winner record — no money is at risk (there's nothing left to pay out
    or debit), but it corrupts the fight's history."""
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"})

    r1 = client.post(f"/fights/{fight['id']}/void")
    assert r1.status_code == 200
    assert r1.json()["status"] == "cancelled"

    r2 = client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})
    assert r2.status_code == 409

    # The fight's record wasn't corrupted by the rejected attempt
    unchanged = client.get(f"/fights/{fight['id']}").json()
    assert unchanged["status"] == "cancelled"
    assert unchanged["winner_fighter_id"] is None


def test_odds_snapshot_is_immune_to_later_odds_changes(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market_resp = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "2.00", "odds_fighter_b": "2.00"}
    ).json()
    outcome_a_id = market_resp["outcomes"][0]["id"]

    user = make_user(client, "tg_snapshot")
    bet = client.post("/bets", json={"user_id": user["id"], "outcome_id": outcome_a_id, "stake": "100.00"}).json()
    assert Decimal(bet["potential_payout"]) == Decimal("200.00")

    # Admin moves the odds after the bet was placed
    session = db()
    try:
        outcome_row = session.query(models.MarketOutcome).filter(models.MarketOutcome.id == outcome_a_id).one()
        odds_service.update_outcome_odds(session, outcome_row, Decimal("5.00"))
    finally:
        session.close()

    # The already-placed bet is unaffected
    stored_bet = client.get(f"/users/{user['id']}/bets").json()[0]
    assert Decimal(stored_bet["odds_at_placement"]) == Decimal("2.00")
    assert Decimal(stored_bet["potential_payout"]) == Decimal("200.00")


def test_bet_on_nonexistent_outcome_returns_404_not_500(client):
    user = make_user(client, "tg_bad_outcome")
    r = client.post("/bets", json={"user_id": user["id"], "outcome_id": "nonexistent-outcome", "stake": "10.00"})
    assert r.status_code == 404


def test_bet_from_nonexistent_user_returns_404_not_500(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"}
    ).json()
    r = client.post(
        "/bets", json={"user_id": "nonexistent-user", "outcome_id": market["outcomes"][0]["id"], "stake": "10.00"}
    )
    assert r.status_code == 404


def test_fight_rejects_nonexistent_fighter_id(client):
    fb = make_fighter(client, "B")
    r = client.post(
        "/fights",
        json={
            "event_name": "Bogus",
            "fighter_a_id": "no-such-fighter",
            "fighter_b_id": fb["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 404


def test_fight_rejects_same_fighter_on_both_sides(client):
    fa = make_fighter(client, "Solo Fighter")
    r = client.post(
        "/fights",
        json={
            "event_name": "Bogus",
            "fighter_a_id": fa["id"],
            "fighter_b_id": fa["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 400


def test_odds_at_or_below_one_are_rejected(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    r = client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.00", "odds_fighter_b": "2.00"})
    assert r.status_code == 422
    r = client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "-1.50", "odds_fighter_b": "2.00"})
    assert r.status_code == 422


def test_house_cut_reduces_payout_when_enabled(client, monkeypatch):
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("ETFC_HOUSE_CUT_FRACTION", "0.10")
    get_settings.cache_clear()
    try:
        fa = make_fighter(client, "A")
        fb = make_fighter(client, "B")
        fight = create_fight(client, fa["id"], fb["id"])
        market = client.post(
            "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "2.00", "odds_fighter_b": "2.00"}
        ).json()
        user = make_user(client, "tg_house_cut")
        client.post("/bets", json={"user_id": user["id"], "outcome_id": market["outcomes"][0]["id"], "stake": "100.00"})
        r = client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})
        assert r.status_code == 200, r.text
        # stake 100 @ 2.00 odds -> profit 100, minus 10% house cut = 90 net profit + 100 stake back = 190
        assert wallet_balance(client, user["id"]) == Decimal("1000.00") - Decimal("100.00") + Decimal("190.00")
    finally:
        get_settings.cache_clear()


def test_void_market_type_prevents_duplicate_market_per_fight(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    r1 = client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.50", "odds_fighter_b": "2.50"})
    assert r1.status_code == 200
    r2 = client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.60", "odds_fighter_b": "2.40"})
    assert r2.status_code == 409  # uq_fight_market_type constraint -> caught and surfaced cleanly
