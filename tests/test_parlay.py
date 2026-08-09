from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.conftest import make_fighter, make_user, telegram_auth_headers


def create_fight(client, fa_id, fb_id, event_name="ETFC 11", hours_offset=0):
    r = client.post(
        "/fights",
        json={
            "event_name": event_name,
            "fighter_a_id": fa_id,
            "fighter_b_id": fb_id,
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1, hours=hours_offset)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def moneyline(client, fight, odds_a="1.80", odds_b="2.00"):
    r = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": odds_a, "odds_fighter_b": odds_b}
    )
    assert r.status_code == 200, r.text
    return r.json()


def make_two_fight_setup(client):
    """Two independent fights, each with a moneyline market, ready for a
    2-leg parlay."""
    fa1, fb1 = make_fighter(client, "A1"), make_fighter(client, "B1")
    fight1 = create_fight(client, fa1["id"], fb1["id"], hours_offset=0)
    market1 = moneyline(client, fight1, odds_a="1.80", odds_b="2.00")

    fa2, fb2 = make_fighter(client, "A2"), make_fighter(client, "B2")
    fight2 = create_fight(client, fa2["id"], fb2["id"], hours_offset=2)
    market2 = moneyline(client, fight2, odds_a="1.50", odds_b="2.50")

    return {
        "fight1": fight1, "market1": market1, "fa1": fa1, "fb1": fb1,
        "fight2": fight2, "market2": market2, "fa2": fa2, "fb2": fb2,
    }


# --- Placement validation ---------------------------------------------

def test_place_parlay_computes_combined_odds_and_potential_payout(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]  # 1.80
    outcome_b = setup["market2"]["outcomes"][0]["id"]  # 1.50
    headers = telegram_auth_headers("800000001")

    r = client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "100.00"}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["combined_odds"]) == Decimal("2.7000")  # 1.80 * 1.50
    assert Decimal(body["potential_payout"]) == Decimal("270.00")
    assert body["status"] == "pending"
    assert len(body["legs"]) == 2


def test_parlay_debits_stake_from_wallet(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000002")

    before = client.get("/miniapp/me", headers=headers).json()
    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "100.00"}, headers=headers)
    after = client.get("/miniapp/me", headers=headers).json()

    assert Decimal(before["wallet"]["balance"]) - Decimal(after["wallet"]["balance"]) == Decimal("100.00")


def test_single_selection_rejected_not_a_parlay(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000003")
    r = client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a], "stake": "10.00"}, headers=headers)
    assert r.status_code == 400


def test_duplicate_selection_rejected(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000004")
    r = client.post(
        "/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_a], "stake": "10.00"}, headers=headers
    )
    assert r.status_code == 400


def test_two_selections_from_same_fight_rejected_as_correlated(client):
    """The core risk-management rule: can't combine two markets from the
    same fight into one ticket — they're not independent risk."""
    fa, fb = make_fighter(client, "A"), make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = moneyline(client, fight)
    method_market = client.post(
        "/markets/method-of-victory",
        json={"fight_id": fight["id"], "odds_ko_tko": "2.10", "odds_submission": "3.50", "odds_decision": "2.40"},
    ).json()

    headers = telegram_auth_headers("800000005")
    r = client.post(
        "/miniapp/parlays",
        json={"outcome_ids": [market["outcomes"][0]["id"], method_market["outcomes"][0]["id"]], "stake": "10.00"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "same fight" in r.json()["detail"] or "per fight" in r.json()["detail"]


def test_parlay_against_suspended_market_rejected(client):
    setup = make_two_fight_setup(client)
    client.post(f"/admin/markets/{setup['market2']['id']}/suspend")
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000006")
    r = client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "10.00"}, headers=headers)
    assert r.status_code == 409


def test_parlay_insufficient_funds_rejected(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000007")
    r = client.post(
        "/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "999999.00"}, headers=headers
    )
    assert r.status_code == 402


def test_parlay_too_many_legs_rejected(client):
    headers = telegram_auth_headers("800000008")
    outcome_ids = []
    for i in range(11):  # default max is 10
        fa, fb = make_fighter(client, f"MA{i}"), make_fighter(client, f"MB{i}")
        fight = create_fight(client, fa["id"], fb["id"], hours_offset=i)
        market = moneyline(client, fight)
        outcome_ids.append(market["outcomes"][0]["id"])
    r = client.post("/miniapp/parlays", json={"outcome_ids": outcome_ids, "stake": "10.00"}, headers=headers)
    assert r.status_code == 400


# --- Settlement -----------------------------------------------------------

def test_parlay_wins_when_every_leg_wins(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]  # fa1, 1.80
    outcome_b = setup["market2"]["outcomes"][0]["id"]  # fa2, 1.50
    headers = telegram_auth_headers("800000009")

    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "100.00"}, headers=headers)

    client.post(f"/fights/{setup['fight1']['id']}/settle", json={"winner_fighter_id": setup["fa1"]["id"], "result_method": "decision"})
    # Still pending — fight2 hasn't settled yet
    parlays = client.get("/miniapp/parlays", headers=headers).json()
    assert parlays[0]["status"] == "pending"

    before = client.get("/miniapp/me", headers=headers).json()
    client.post(f"/fights/{setup['fight2']['id']}/settle", json={"winner_fighter_id": setup["fa2"]["id"], "result_method": "decision"})
    after = client.get("/miniapp/me", headers=headers).json()

    parlays = client.get("/miniapp/parlays", headers=headers).json()
    assert parlays[0]["status"] == "won"
    assert all(leg["status"] == "won" for leg in parlays[0]["legs"])
    # 100 * 1.80 * 1.50 = 270 payout
    assert Decimal(after["wallet"]["balance"]) - Decimal(before["wallet"]["balance"]) == Decimal("270.00")


def test_parlay_loses_when_any_leg_loses(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]  # fa1
    outcome_b = setup["market2"]["outcomes"][0]["id"]  # fa2
    headers = telegram_auth_headers("800000010")

    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "100.00"}, headers=headers)

    # fa1 wins (leg 1 wins)...
    client.post(f"/fights/{setup['fight1']['id']}/settle", json={"winner_fighter_id": setup["fa1"]["id"], "result_method": "decision"})
    # ...but fb2 wins fight 2, not fa2 -> leg 2 loses
    before = client.get("/miniapp/me", headers=headers).json()
    client.post(f"/fights/{setup['fight2']['id']}/settle", json={"winner_fighter_id": setup["fb2"]["id"], "result_method": "decision"})
    after = client.get("/miniapp/me", headers=headers).json()

    parlays = client.get("/miniapp/parlays", headers=headers).json()
    assert parlays[0]["status"] == "lost"
    statuses = {leg["status"] for leg in parlays[0]["legs"]}
    assert statuses == {"won", "lost"}
    # No payout — balance only reflects whatever else happened (nothing here)
    assert after["wallet"]["balance"] == before["wallet"]["balance"]


def test_parlay_loses_early_leg_regardless_of_settlement_order(client):
    """A parlay must lose overall even if the LOSING leg settles first —
    order of settlement shouldn't matter to the outcome."""
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000011")

    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "50.00"}, headers=headers)

    # fight1 settles first, and the picked fighter LOSES
    client.post(f"/fights/{setup['fight1']['id']}/settle", json={"winner_fighter_id": setup["fb1"]["id"], "result_method": "decision"})
    client.post(f"/fights/{setup['fight2']['id']}/settle", json={"winner_fighter_id": setup["fa2"]["id"], "result_method": "decision"})

    parlays = client.get("/miniapp/parlays", headers=headers).json()
    assert parlays[0]["status"] == "lost"


def test_parlay_void_leg_excluded_from_payout_not_treated_as_loss(client):
    """The actual rule this guards: a voided leg (its fight got cancelled)
    doesn't sink the ticket and doesn't count at its original odds either
    — it's excluded, as if it were never in the parlay."""
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]  # 1.80
    outcome_b = setup["market2"]["outcomes"][0]["id"]  # 1.50
    headers = telegram_auth_headers("800000012")

    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "100.00"}, headers=headers)

    # fight1's leg wins normally
    client.post(f"/fights/{setup['fight1']['id']}/settle", json={"winner_fighter_id": setup["fa1"]["id"], "result_method": "decision"})
    # fight2 gets cancelled -> that leg voids
    before = client.get("/miniapp/me", headers=headers).json()
    client.post(f"/fights/{setup['fight2']['id']}/void")
    after = client.get("/miniapp/me", headers=headers).json()

    parlays = client.get("/miniapp/parlays", headers=headers).json()
    assert parlays[0]["status"] == "won"
    statuses = {leg["status"] for leg in parlays[0]["legs"]}
    assert statuses == {"won", "void"}
    # Payout uses ONLY the won leg's odds (1.80), not 1.80 * 1.50
    assert Decimal(after["wallet"]["balance"]) - Decimal(before["wallet"]["balance"]) == Decimal("180.00")


def test_parlay_fully_voided_refunds_stake_not_a_win(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]
    headers = telegram_auth_headers("800000013")

    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "100.00"}, headers=headers)

    before = client.get("/miniapp/me", headers=headers).json()
    client.post(f"/fights/{setup['fight1']['id']}/void")
    client.post(f"/fights/{setup['fight2']['id']}/void")
    after = client.get("/miniapp/me", headers=headers).json()

    parlays = client.get("/miniapp/parlays", headers=headers).json()
    assert parlays[0]["status"] == "void"
    # Exactly the stake back — not a "win"
    assert Decimal(after["wallet"]["balance"]) - Decimal(before["wallet"]["balance"]) == Decimal("100.00")


def test_parlay_settlement_does_not_disturb_regular_single_bets_on_same_market(client):
    """Regression check for the settlement_service rewrite: a regular
    single bet on the same outcome as a parlay leg must still settle
    normally, unaffected by the parlay resolution running alongside it."""
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]

    parlay_headers = telegram_auth_headers("800000014")
    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "50.00"}, headers=parlay_headers)

    single_user = make_user(client, "tg_single_alongside_parlay")
    single_bet = client.post(
        "/bets", json={"user_id": single_user["id"], "outcome_id": outcome_a, "stake": "20.00"}
    ).json()

    client.post(f"/fights/{setup['fight1']['id']}/settle", json={"winner_fighter_id": setup["fa1"]["id"], "result_method": "decision"})

    settled_single = client.get(f"/users/{single_user['id']}/bets").json()[0]
    assert settled_single["status"] == "won"
    assert settled_single["potential_payout"] == "36.00"  # 20 * 1.80, untouched by the parlay logic


def test_parlays_are_per_user(client):
    setup = make_two_fight_setup(client)
    outcome_a = setup["market1"]["outcomes"][0]["id"]
    outcome_b = setup["market2"]["outcomes"][0]["id"]
    alice = telegram_auth_headers("800000015")
    bob = telegram_auth_headers("800000016")

    client.post("/miniapp/parlays", json={"outcome_ids": [outcome_a, outcome_b], "stake": "10.00"}, headers=alice)

    assert len(client.get("/miniapp/parlays", headers=alice).json()) == 1
    assert len(client.get("/miniapp/parlays", headers=bob).json()) == 0
