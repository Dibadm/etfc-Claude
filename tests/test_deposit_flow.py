import os
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from tests.conftest import make_fighter, telegram_auth_headers

REAL_SMS = (
    "Dear Abdi \n"
    "You have transferred ETB 30.00 to hanan reda (2519****8740) on "
    "14/06/2026 20:47:00. Your transaction number is DFE8VVNNIC. The "
    "service fee is  ETB 0.87 and  15% VAT on the service fee is ETB 0.13. "
    "Your current E-Money Account  balance is ETB 1,429.52. To download "
    "your payment information please click this link: "
    "https://transactioninfo.ethiotelecom.et/receipt/DFE8VVNNIC.\n\n"
    "Thank you for using telebirr\n"
    "Ethio telecom"
)


def add_account(client, phone="251912348740", recipient_name="hanan reda"):
    r = client.post("/admin/deposit-accounts", json={"phone": phone, "recipient_name": recipient_name})
    assert r.status_code == 200, r.text
    return r.json()


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


def disable_online_verification(monkeypatch):
    """Most tests here care about the orchestration (matching, duplicate
    detection, rotation) rather than the online-verification branch —
    that branch gets its own dedicated tests below with the HTTP layer
    mocked. Disabling it here keeps those other tests from depending on
    real network access to Ethio Telecom's site."""
    monkeypatch.setenv("ETFC_TELEBIRR_VERIFY_ENABLED", "false")
    get_settings.cache_clear()


# --- Wagering-disabled gate --------------------------------------------

def test_deposit_blocked_when_wagering_disabled(client):
    headers = telegram_auth_headers("700000001")
    client.get("/miniapp/me", headers=headers)  # create the user first
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 403


# --- Admin: deposit account management ----------------------------------

def test_first_added_account_becomes_active_automatically(client):
    account = add_account(client)
    assert account["is_active"] is True


def test_second_account_not_automatically_active(client):
    add_account(client, phone="251911110000", recipient_name="Acc One")
    second = add_account(client, phone="251922220000", recipient_name="Acc Two")
    assert second["is_active"] is False


def test_activating_one_account_deactivates_others(client):
    a = add_account(client, phone="251911110000", recipient_name="Acc One")
    b = add_account(client, phone="251922220000", recipient_name="Acc Two")
    r = client.post(f"/admin/deposit-accounts/{b['id']}/activate")
    assert r.status_code == 200
    assert r.json()["is_active"] is True

    accounts = {acc["id"]: acc for acc in client.get("/admin/deposit-accounts").json()}
    assert accounts[a["id"]]["is_active"] is False
    assert accounts[b["id"]]["is_active"] is True


def test_removing_active_account_promotes_next_one(client):
    a = add_account(client, phone="251911110000", recipient_name="Acc One")
    b = add_account(client, phone="251922220000", recipient_name="Acc Two")
    r = client.delete(f"/admin/deposit-accounts/{a['id']}")
    assert r.status_code == 204

    remaining = client.get("/admin/deposit-accounts").json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == b["id"]
    assert remaining[0]["is_active"] is True


def test_deposit_account_admin_endpoints_require_admin_token():
    from fastapi.testclient import TestClient
    from app.main import app

    bare_client = TestClient(app)
    assert bare_client.get("/admin/deposit-accounts").status_code == 422
    assert bare_client.post("/admin/deposit-accounts", json={"phone": "x", "recipient_name": "y"}).status_code == 422


# --- The deposit flow itself ---------------------------------------------

def test_deposit_with_no_active_account_returns_503(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    headers = telegram_auth_headers("700000002")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 503


def test_successful_deposit_credits_wallet(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")

    headers = telegram_auth_headers("700000003")
    me_before = client.get("/miniapp/me", headers=headers).json()
    assert me_before["wallet"]["balance"] == "0.00"  # no demo seeding once wagering is live

    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["wallet"]["balance"] == "30.00"


def test_deposit_to_wrong_account_rejected(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251999998888", recipient_name="Someone Else Entirely")

    headers = telegram_auth_headers("700000004")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 400
    assert "active deposit account" in r.json()["detail"]


def test_duplicate_sms_reference_rejected_second_time(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")

    headers = telegram_auth_headers("700000005")
    client.get("/miniapp/me", headers=headers)
    r1 = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r1.status_code == 200

    r2 = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r2.status_code == 409


def test_unparseable_sms_rejected(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")

    headers = telegram_auth_headers("700000006")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": "not a real telebirr message at all"}, headers=headers)
    assert r.status_code == 400


def test_expected_amount_mismatch_rejected(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")

    headers = telegram_auth_headers("700000007")
    client.get("/miniapp/me", headers=headers)
    r = client.post(
        "/miniapp/deposit",
        json={"sms_text": REAL_SMS, "expected_amount": "999.00"},
        headers=headers,
    )
    assert r.status_code == 400


def test_deposit_account_rotates_after_threshold(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    monkeypatch.setenv("ETFC_ROTATE_AFTER_DEPOSITS", "1")
    get_settings.cache_clear()

    acc_a = add_account(client, phone="251912348740", recipient_name="hanan reda")
    acc_b = add_account(client, phone="251900001234", recipient_name="second account")

    headers = telegram_auth_headers("700000008")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 200, r.text

    accounts = {a["id"]: a for a in client.get("/admin/deposit-accounts").json()}
    assert accounts[acc_a["id"]]["is_active"] is False
    assert accounts[acc_b["id"]]["is_active"] is True

    monkeypatch.delenv("ETFC_ROTATE_AFTER_DEPOSITS", raising=False)
    get_settings.cache_clear()


def test_get_active_deposit_account_endpoint(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000009")
    r = client.get("/miniapp/deposit-account", headers=headers)
    assert r.status_code == 200
    assert r.json()["recipient_name"] == "hanan reda"


# --- Rate limiting ---------------------------------------------------------

def _sms_with_reference(reference: str) -> str:
    return (
        "Dear Abdi \n"
        f"You have transferred ETB 30.00 to hanan reda (2519****8740) on "
        f"14/06/2026 20:47:00. Your transaction number is {reference}. The "
        "service fee is  ETB 0.87 and  15% VAT on the service fee is ETB 0.13. "
        "Your current E-Money Account  balance is ETB 1,429.52.\n"
        "Thank you for using telebirr\nEthio telecom"
    )


def test_deposit_endpoint_rate_limited_after_five_attempts(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000020")
    client.get("/miniapp/me", headers=headers)

    for i in range(5):
        r = client.post("/miniapp/deposit", json={"sms_text": _sms_with_reference(f"REF{i:07d}")}, headers=headers)
        assert r.status_code == 200, r.text

    r = client.post("/miniapp/deposit", json={"sms_text": _sms_with_reference("REF9999999")}, headers=headers)
    assert r.status_code == 429


def test_deposit_rate_limit_is_per_user_not_global(client, live_wagering, monkeypatch):
    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")

    alice = telegram_auth_headers("700000021")
    bob = telegram_auth_headers("700000022")
    client.get("/miniapp/me", headers=alice)
    client.get("/miniapp/me", headers=bob)

    for i in range(5):
        r = client.post("/miniapp/deposit", json={"sms_text": _sms_with_reference(f"ALICE{i:06d}")}, headers=alice)
        assert r.status_code == 200

    # Alice is now rate-limited...
    r = client.post("/miniapp/deposit", json={"sms_text": _sms_with_reference("ALICE999999")}, headers=alice)
    assert r.status_code == 429

    # ...but Bob, a different user, still has his own budget
    r = client.post("/miniapp/deposit", json={"sms_text": _sms_with_reference("BOB0000001")}, headers=bob)
    assert r.status_code == 200, r.text


def test_bet_placement_rate_limited_after_twenty_bets(client):
    fa = make_fighter(client, "A")
    fb = make_fighter(client, "B")
    fight = create_fight(client, fa["id"], fb["id"])
    market = client.post(
        "/markets/moneyline", json={"fight_id": fight["id"], "odds_fighter_a": "1.80", "odds_fighter_b": "2.00"}
    ).json()
    outcome_id = market["outcomes"][0]["id"]

    headers = telegram_auth_headers("700000023")
    for _ in range(20):
        r = client.post("/miniapp/bets", json={"outcome_id": outcome_id, "stake": "1.00"}, headers=headers)
        assert r.status_code == 200, r.text

    r = client.post("/miniapp/bets", json={"outcome_id": outcome_id, "stake": "1.00"}, headers=headers)
    assert r.status_code == 429


# --- Online verification branch (HTTP layer mocked) -----------------------

def test_deposit_succeeds_when_online_verification_confirms_match(client, live_wagering, monkeypatch):
    from decimal import Decimal
    from app.services import telebirr_verify

    monkeypatch.setenv("ETFC_TELEBIRR_VERIFY_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        telebirr_verify,
        "verify_receipt_online",
        lambda receipt_no, timeout=10: telebirr_verify.ReceiptVerification(
            ok=True, amount=Decimal("30.00"), recipient_name="hanan reda", recipient_phone_last4="8740"
        ),
    )
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000010")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["wallet"]["balance"] == "30.00"


def test_deposit_rejected_when_online_receipt_amount_disagrees_with_sms(client, live_wagering, monkeypatch):
    from decimal import Decimal
    from app.services import telebirr_verify

    monkeypatch.setenv("ETFC_TELEBIRR_VERIFY_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        telebirr_verify,
        "verify_receipt_online",
        lambda receipt_no, timeout=10: telebirr_verify.ReceiptVerification(
            ok=True, amount=Decimal("999.00"), recipient_name="hanan reda", recipient_phone_last4="8740"
        ),
    )
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000011")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 400


def test_deposit_still_succeeds_when_receipt_site_is_unreachable(client, live_wagering, monkeypatch):
    """The whole point of the site-down fallback: a flaky external site
    shouldn't block a real deposit that already passed SMS-regex checks."""
    from app.services import telebirr_verify

    monkeypatch.setenv("ETFC_TELEBIRR_VERIFY_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        telebirr_verify,
        "verify_receipt_online",
        lambda receipt_no, timeout=10: telebirr_verify.ReceiptVerification(ok=False, error="receipt_site_unreachable"),
    )
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000012")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 200, r.text


def test_deposit_rejected_when_receipt_genuinely_not_found(client, live_wagering, monkeypatch):
    """Unlike 'site unreachable', a clean 404 (receipt doesn't exist) is a
    real rejection — the transaction reference doesn't check out."""
    from app.services import telebirr_verify

    monkeypatch.setenv("ETFC_TELEBIRR_VERIFY_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        telebirr_verify,
        "verify_receipt_online",
        lambda receipt_no, timeout=10: telebirr_verify.ReceiptVerification(ok=False, error="receipt_not_found_http_404"),
    )
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000013")
    client.get("/miniapp/me", headers=headers)
    r = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r.status_code == 422


def test_concurrent_duplicate_deposit_race_is_closed_by_db_constraint(client, live_wagering, monkeypatch):
    """The actual bug: reference_already_used() is a plain SELECT with no
    lock behind it — on its own, two requests racing each other could both
    pass that check before either commits. This simulates exactly that
    window (by patching the pre-check to always say "not used yet", as if
    a second request's check ran before the first request's commit) and
    confirms the database-level unique index (see models.py) still stops
    the double-credit, surfacing as the same clean DuplicateReferenceError
    rather than a raw 500."""
    from app.services import deposit_service

    disable_online_verification(monkeypatch)
    add_account(client, phone="251912348740", recipient_name="hanan reda")
    headers = telegram_auth_headers("700000014")
    client.get("/miniapp/me", headers=headers)

    # First submission goes through normally.
    r1 = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r1.status_code == 200, r1.text
    balance_after_first = r1.json()["wallet"]["balance"]

    # Force the pre-check to report "not used" even though it now is —
    # this is the exact state two truly concurrent requests would both
    # observe before either had committed.
    monkeypatch.setattr(deposit_service, "reference_already_used", lambda db, reference: False)

    r2 = client.post("/miniapp/deposit", json={"sms_text": REAL_SMS}, headers=headers)
    assert r2.status_code == 409, r2.text  # DuplicateReferenceError, not a 500

    # And critically: no double credit happened.
    me = client.get("/miniapp/me", headers=headers).json()
    assert me["wallet"]["balance"] == balance_after_first
