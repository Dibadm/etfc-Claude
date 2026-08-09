import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import make_fighter


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


# --- Admin auth itself ----------------------------------------------------

def test_admin_endpoint_rejects_missing_authorization_header():
    bare_client = TestClient(app)  # no default Authorization header
    r = bare_client.post("/fighters", json={"name": "A"})
    assert r.status_code == 422  # missing required header


def test_admin_endpoint_rejects_malformed_authorization_header():
    bare_client = TestClient(app)
    r = bare_client.post("/fighters", json={"name": "A"}, headers={"Authorization": "not-a-bearer-token"})
    assert r.status_code == 401


def test_admin_endpoint_rejects_wrong_token():
    bare_client = TestClient(app)
    r = bare_client.post("/fighters", json={"name": "A"}, headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401


def test_admin_endpoint_accepts_correct_token(client):
    # `client` fixture already carries the correct token by default
    r = client.post("/fighters", json={"name": "A"})
    assert r.status_code == 200


def test_admin_brute_force_blocked_after_repeated_wrong_tokens():
    bare_client = TestClient(app)
    for _ in range(10):
        r = bare_client.post("/fighters", json={"name": "A"}, headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401
    # 11th failed attempt from the same IP within the window is blocked outright
    r = bare_client.post("/fighters", json={"name": "A"}, headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 429


def test_admin_brute_force_limit_is_per_ip_not_global():
    from fastapi.testclient import TestClient as TC

    bare_client = TC(app)
    for _ in range(10):
        bare_client.post(
            "/fighters", json={"name": "A"},
            headers={"Authorization": "Bearer wrong-token", "X-Forwarded-For": "10.0.0.1"},
        )
    blocked = bare_client.post(
        "/fighters", json={"name": "A"},
        headers={"Authorization": "Bearer wrong-token", "X-Forwarded-For": "10.0.0.1"},
    )
    assert blocked.status_code == 429

    # A different source IP is unaffected by 10.0.0.1's failures
    still_ok = bare_client.post(
        "/fighters", json={"name": "A"},
        headers={"Authorization": "Bearer wrong-token", "X-Forwarded-For": "10.0.0.2"},
    )
    assert still_ok.status_code == 401  # wrong token, but not yet rate-limited


def test_admin_brute_force_counter_does_not_penalize_correct_token(client):
    """A handful of past typos from this IP shouldn't throttle a
    legitimate admin who then gets the token right."""
    bare_client = TestClient(app)
    for _ in range(5):
        bare_client.post("/fighters", json={"name": "A"}, headers={"Authorization": "Bearer wrong-token"})
    r = bare_client.post(
        "/fighters", json={"name": "A"}, headers={"Authorization": f"Bearer {os.environ['ETFC_ADMIN_TOKEN']}"}
    )
    assert r.status_code == 200


def test_admin_ping_distinguishes_auth_failure_from_resource_not_found():
    """This is the exact bug the admin frontend's login screen hit: a 404
    from a real resource endpoint looks identical to a 401 unless there's
    a dedicated auth-check endpoint that can never 404."""
    bare_client = TestClient(app)
    r = bare_client.get("/admin/ping", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401

    r = bare_client.get("/admin/ping", headers={"Authorization": f"Bearer {os.environ['ETFC_ADMIN_TOKEN']}"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_public_read_endpoints_need_no_admin_token():
    bare_client = TestClient(app)
    assert bare_client.get("/status").status_code == 200
    assert bare_client.get("/fights").status_code == 200


def test_list_fighters(client):
    make_fighter(client, "Kebede Alemu")
    make_fighter(client, "Yonas Tesfaye")
    r = client.get("/fighters")
    assert r.status_code == 200
    names = {f["name"] for f in r.json()}
    assert names == {"Kebede Alemu", "Yonas Tesfaye"}


# --- Fighter photos & main event -------------------------------------------

def test_create_fighter_with_image_url(client):
    r = client.post("/fighters", json={"name": "Kebede Alemu", "image_url": "https://example.com/kebede.jpg"})
    assert r.status_code == 200
    assert r.json()["image_url"] == "https://example.com/kebede.jpg"


def test_create_fighter_without_image_url_defaults_null(client):
    r = client.post("/fighters", json={"name": "Yonas Tesfaye"})
    assert r.status_code == 200
    assert r.json()["image_url"] is None


def test_patch_fighter_sets_image_url_after_creation(client):
    fighter = make_fighter(client, "Selam Girma")
    assert fighter["image_url"] is None
    r = client.patch(f"/fighters/{fighter['id']}", json={"image_url": "https://example.com/selam.jpg"})
    assert r.status_code == 200
    assert r.json()["image_url"] == "https://example.com/selam.jpg"
    assert r.json()["name"] == "Selam Girma"  # untouched fields preserved


def test_patch_fighter_partial_update_leaves_other_fields_alone(client):
    fighter = client.post("/fighters", json={"name": "Dawit Mekonnen", "nickname": "The Hammer"}).json()
    r = client.patch(f"/fighters/{fighter['id']}", json={"nickname": "The Anvil"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "The Anvil"
    assert r.json()["name"] == "Dawit Mekonnen"


def test_patch_nonexistent_fighter_404s(client):
    r = client.patch("/fighters/no-such-id", json={"nickname": "Ghost"})
    assert r.status_code == 404


def test_patch_fighter_requires_admin_token():
    bare_client = TestClient(app)
    r = bare_client.patch("/fighters/whatever", json={"nickname": "X"})
    assert r.status_code == 422  # missing header


def test_create_fight_defaults_not_main_event(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    assert fight["is_main_event"] is False


def test_create_fight_can_be_flagged_main_event_at_creation(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    r = client.post(
        "/fights",
        json={
            "event_name": "ETFC 11",
            "fighter_a_id": fa["id"],
            "fighter_b_id": fb["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "is_main_event": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["is_main_event"] is True


def test_set_main_event_toggle(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    r = client.post(f"/admin/fights/{fight['id']}/set-main-event", params={"is_main_event": True})
    assert r.status_code == 200
    assert r.json()["is_main_event"] is True

    r = client.post(f"/admin/fights/{fight['id']}/set-main-event", params={"is_main_event": False})
    assert r.status_code == 200
    assert r.json()["is_main_event"] is False


def test_set_main_event_requires_admin_token():
    bare_client = TestClient(app)
    r = bare_client.post("/admin/fights/whatever/set-main-event", params={"is_main_event": True})
    assert r.status_code == 422


def test_list_fights_includes_fighter_photos_and_main_event_flag(client):
    fa = client.post("/fighters", json={"name": "Kebede Alemu", "image_url": "https://example.com/k.jpg"}).json()
    fb = make_fighter(client, "Yonas Tesfaye")
    create_fight(client, fa["id"], fb["id"])
    r = client.post(
        "/fights",
        json={
            "event_name": "ETFC 11",
            "fighter_a_id": fa["id"],
            "fighter_b_id": fb["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "is_main_event": True,
        },
    )
    fights = client.get("/fights").json()
    main_events = [f for f in fights if f["is_main_event"]]
    assert len(main_events) == 1
    assert main_events[0]["fighter_a"]["image_url"] == "https://example.com/k.jpg"


# --- New endpoints: suspend / reopen / odds update -------------------------

def test_suspend_then_reopen_market(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()

    r = client.post(f"/admin/markets/{market['id']}/suspend")
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"

    # Betting against a suspended market is rejected
    user = client.post("/users", json={"telegram_id": "susp1"}).json()
    bet = client.post("/bets", json={"user_id": user["id"], "outcome_id": market["outcomes"][0]["id"], "stake": "10.00"})
    assert bet.status_code == 409

    r = client.post(f"/admin/markets/{market['id']}/reopen")
    assert r.status_code == 200
    assert r.json()["status"] == "open"

    # Now betting works again
    bet = client.post("/bets", json={"user_id": user["id"], "outcome_id": market["outcomes"][0]["id"], "stake": "10.00"})
    assert bet.status_code == 200


def test_cannot_reopen_a_settled_market(client):
    """The actual bug this guards: reopening a settled market would let
    new bets get placed against it that can never be graded — the fight
    is already COMPLETED, so settlement can't run on it again. Stake
    would be debited from the bettor with no way to ever resolve it."""
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})

    r = client.post(f"/admin/markets/{market['id']}/reopen")
    assert r.status_code == 409

    # Confirm it's still genuinely closed to betting
    user = client.post("/users", json={"telegram_id": "settled_reopen_attempt"}).json()
    bet = client.post("/bets", json={"user_id": user["id"], "outcome_id": market["outcomes"][0]["id"], "stake": "10.00"})
    assert bet.status_code == 409


def test_cannot_suspend_a_settled_market(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})

    r = client.post(f"/admin/markets/{market['id']}/suspend")
    assert r.status_code == 409


def test_cannot_reopen_a_voided_market(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    client.post(f"/fights/{fight['id']}/void")

    r = client.post(f"/admin/markets/{market['id']}/reopen")
    assert r.status_code == 409


def test_update_outcome_odds(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    outcome_id = market["outcomes"][0]["id"]

    r = client.post(f"/admin/outcomes/{outcome_id}/odds", json={"new_odds": "1.95"})
    assert r.status_code == 200
    assert r.json()["odds"] == "1.95"

    refreshed = client.get(f"/fights/{fight['id']}/markets").json()
    updated_outcome = next(o for m in refreshed for o in m["outcomes"] if o["id"] == outcome_id)
    assert updated_outcome["odds"] == "1.95"


def test_update_outcome_odds_rejects_invalid_value(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    r = client.post(f"/admin/outcomes/{market['outcomes'][0]['id']}/odds", json={"new_odds": "0.50"})
    assert r.status_code == 422


def test_odds_change_does_not_affect_already_placed_bets(client):
    """The whole point of odds snapshotting — re-verified here from the
    admin-endpoint side, not just the service layer."""
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    outcome_id = market["outcomes"][0]["id"]

    user = client.post("/users", json={"telegram_id": "oddschange1"}).json()
    bet = client.post("/bets", json={"user_id": user["id"], "outcome_id": outcome_id, "stake": "100.00"}).json()
    assert bet["odds_at_placement"] == "1.80"

    client.post(f"/admin/outcomes/{outcome_id}/odds", json={"new_odds": "3.00"})

    r = client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})
    assert r.status_code == 200
    settled_bet = client.get(f"/users/{user['id']}/bets").json()[0]
    assert settled_bet["potential_payout"] == "180.00"  # 100 * 1.80, NOT 100 * 3.00


# --- Liability view ---------------------------------------------------------

def test_liability_view_sums_pending_bets_per_outcome(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    outcome_a, outcome_b = market["outcomes"][0]["id"], market["outcomes"][1]["id"]

    alice = client.post("/users", json={"telegram_id": "liab_alice"}).json()
    bob = client.post("/users", json={"telegram_id": "liab_bob"}).json()
    carol = client.post("/users", json={"telegram_id": "liab_carol"}).json()

    client.post("/bets", json={"user_id": alice["id"], "outcome_id": outcome_a, "stake": "100.00"})
    client.post("/bets", json={"user_id": bob["id"], "outcome_id": outcome_a, "stake": "50.00"})
    client.post("/bets", json={"user_id": carol["id"], "outcome_id": outcome_b, "stake": "30.00"})

    r = client.get(f"/admin/fights/{fight['id']}/liability")
    assert r.status_code == 200
    liability = r.json()
    moneyline = next(m for m in liability if m["market_type"] == "moneyline")
    by_outcome = {o["outcome_id"]: o for o in moneyline["outcomes"]}

    assert by_outcome[outcome_a]["pending_bet_count"] == 2
    assert Decimal(by_outcome[outcome_a]["total_stake"]) == Decimal("150.00")
    assert Decimal(by_outcome[outcome_a]["total_potential_payout"]) == Decimal("270.00")  # 100*1.8 + 50*1.8

    assert by_outcome[outcome_b]["pending_bet_count"] == 1
    assert Decimal(by_outcome[outcome_b]["total_stake"]) == Decimal("30.00")
    assert Decimal(by_outcome[outcome_b]["total_potential_payout"]) == Decimal("60.00")  # 30*2.0


def test_liability_view_excludes_settled_bets(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    outcome_a = market["outcomes"][0]["id"]
    user = client.post("/users", json={"telegram_id": "liab_settled"}).json()
    client.post("/bets", json={"user_id": user["id"], "outcome_id": outcome_a, "stake": "100.00"})

    client.post(f"/fights/{fight['id']}/settle", json={"winner_fighter_id": fa["id"], "result_method": "decision"})

    liability = client.get(f"/admin/fights/{fight['id']}/liability").json()
    moneyline = next(m for m in liability if m["market_type"] == "moneyline")
    outcome_liability = next(o for o in moneyline["outcomes"] if o["outcome_id"] == outcome_a)
    assert outcome_liability["pending_bet_count"] == 0
    assert Decimal(outcome_liability["total_stake"]) == Decimal("0.00")


def test_liability_view_requires_admin_token():
    bare_client = TestClient(app)
    r = bare_client.get("/admin/fights/nonexistent/liability")
    assert r.status_code == 422  # missing header — never even gets to the 404 check
