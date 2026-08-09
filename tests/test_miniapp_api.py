from datetime import datetime, timedelta, timezone

from tests.conftest import make_fighter, telegram_auth_headers


def create_fight(client, fa_id, fb_id, event_name="ETFC 11"):
    r = client.post(
        "/fights",
        json={
            "event_name": event_name,
            "fighter_a_id": fa_id,
            "fighter_b_id": fb_id,
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_miniapp_me_creates_user_on_first_call_and_seeds_demo_balance(client):
    r = client.get("/miniapp/me", headers=telegram_auth_headers("555000111"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["telegram_id"] == "555000111"
    assert body["is_demo_account"] is True
    assert float(body["wallet"]["balance"]) == 1000.00  # default demo_seed_balance


def test_miniapp_me_is_idempotent_no_duplicate_users_or_reseeding(client):
    r1 = client.get("/miniapp/me", headers=telegram_auth_headers("555000222")).json()
    r2 = client.get("/miniapp/me", headers=telegram_auth_headers("555000222")).json()
    assert r1["id"] == r2["id"]
    assert r1["wallet"]["balance"] == r2["wallet"]["balance"]


def test_miniapp_rejects_request_with_no_init_data_header(client):
    r = client.get("/miniapp/me")
    assert r.status_code == 422  # missing required header


def test_miniapp_rejects_forged_init_data(client):
    r = client.get("/miniapp/me", headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&auth_date=1&hash=deadbeef"})
    assert r.status_code == 401


def test_miniapp_user_cannot_bet_as_someone_else(client):
    """The whole point of Telegram auth: there's no user_id field to spoof
    in the request body anymore — the bettor is derived from the signed
    initData header, full stop."""
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()

    alice_headers = telegram_auth_headers("555000333", username="alice")
    r = client.post(
        "/miniapp/bets",
        json={"outcome_id": market["outcomes"][0]["id"], "stake": "50.00"},
        headers=alice_headers,
    )
    assert r.status_code == 200, r.text
    bet = r.json()

    alice_me = client.get("/miniapp/me", headers=alice_headers).json()
    assert bet["user_id"] == alice_me["id"]  # bet was placed as Alice, whoever she is server-side


def test_miniapp_list_my_bets_only_returns_own_bets(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()

    alice = telegram_auth_headers("555000444", username="alice")
    bob = telegram_auth_headers("555000555", username="bob")

    client.post("/miniapp/bets", json={"outcome_id": market["outcomes"][0]["id"], "stake": "10.00"}, headers=alice)
    client.post("/miniapp/bets", json={"outcome_id": market["outcomes"][1]["id"], "stake": "20.00"}, headers=bob)
    client.post("/miniapp/bets", json={"outcome_id": market["outcomes"][0]["id"], "stake": "30.00"}, headers=alice)

    alice_bets = client.get("/miniapp/bets", headers=alice).json()
    bob_bets = client.get("/miniapp/bets", headers=bob).json()

    assert len(alice_bets) == 2
    assert len(bob_bets) == 1
    assert {b["stake"] for b in alice_bets} == {"10.00", "30.00"}


def test_list_fights_includes_fighter_names(client):
    fa = make_fighter(client, "Kebede Alemu")
    fb = make_fighter(client, "Yonas Tesfaye")
    create_fight(client, fa["id"], fb["id"], event_name="ETFC 11")

    r = client.get("/fights")
    assert r.status_code == 200
    fights = r.json()
    assert len(fights) == 1
    assert fights[0]["event_name"] == "ETFC 11"
    assert fights[0]["fighter_a"]["name"] == "Kebede Alemu"
    assert fights[0]["fighter_b"]["name"] == "Yonas Tesfaye"


def test_list_fights_includes_moneyline_preview_odds(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.75", "odds_fighter_b": "2.10"})

    fights = client.get("/fights").json()
    assert fights[0]["moneyline_odds_a"] == "1.75"
    assert fights[0]["moneyline_odds_b"] == "2.10"


def test_list_fights_moneyline_preview_null_when_no_market_yet(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    create_fight(client, fa["id"], fb["id"])

    fights = client.get("/fights").json()
    assert fights[0]["moneyline_odds_a"] is None
    assert fights[0]["moneyline_odds_b"] is None


def test_fight_markets_always_list_moneyline_first(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    # Create in a deliberately different order than the display should use.
    client.post("/markets/round-prop", json={"fight_id": fight["id"], "total_rounds": 3,
                "odds_by_round": {"1": "4.50", "2": "5.00", "3": "4.00"}, "odds_goes_the_distance": "2.20"})
    client.post("/markets/method-of-victory", json={"fight_id": fight["id"], "odds_ko_tko": "2.10",
                "odds_submission": "3.50", "odds_decision": "2.40"})
    client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.65", "odds_fighter_b": "2.20"})

    markets = client.get(f"/fights/{fight['id']}/markets").json()
    assert [m["market_type"] for m in markets] == ["moneyline", "method_of_victory", "round_prop"]


def test_list_fights_filters_by_status(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    client.post("/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"})
    client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})

    scheduled = client.get("/fights", params={"status": "scheduled"}).json()
    completed = client.get("/fights", params={"status": "completed"}).json()
    assert len(scheduled) == 0
    assert len(completed) == 1
