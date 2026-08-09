from decimal import Decimal

from app.services.telebirr_sms_parser import (
    extract_receipt_number,
    parse_telebirr_sms,
    validate_deposit_amount,
    verify_recipient,
)

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


def test_parses_real_telebirr_sms_format():
    parsed = parse_telebirr_sms(REAL_SMS)
    assert parsed is not None
    assert parsed.amount == Decimal("30.00")
    assert parsed.recipient_name == "hanan reda"
    assert parsed.recipient_last4 == "8740"
    assert parsed.reference == "DFE8VVNNIC"


def test_amount_is_transferred_amount_not_fee_or_balance():
    """The regressiony bug this guards against: naively grabbing the first
    'ETB X.XX' in the message would match the 0.87 service fee, not the
    30.00 actually sent."""
    parsed = parse_telebirr_sms(REAL_SMS)
    assert parsed.amount == Decimal("30.00")
    assert parsed.amount != Decimal("0.87")
    assert parsed.amount != Decimal("1429.52")


def test_extract_receipt_number_from_transaction_number_phrase():
    assert extract_receipt_number(REAL_SMS) == "DFE8VVNNIC"


def test_extract_receipt_number_from_url_fallback():
    text = "Some odd variant with only a link: https://transactioninfo.ethiotelecom.et/receipt/ABX99112ZZQ end"
    assert extract_receipt_number(text) == "ABX99112ZZQ"


def test_empty_sms_returns_none():
    assert parse_telebirr_sms("") is None
    assert parse_telebirr_sms("short") is None


def test_random_text_without_amount_returns_none():
    assert parse_telebirr_sms("Hello how are you today, hope all is well with the family") is None


def test_sms_with_amount_but_no_reference_returns_none():
    text = "You transferred ETB 50.00 today to someone but this message has no reference number at all"
    assert parse_telebirr_sms(text) is None


def test_verify_recipient_matches():
    parsed = parse_telebirr_sms(REAL_SMS)
    ok, reason = verify_recipient(parsed, "Hanan Reda", "8740")
    assert ok is True
    assert reason == "ok"


def test_verify_recipient_name_mismatch_rejected():
    parsed = parse_telebirr_sms(REAL_SMS)
    ok, reason = verify_recipient(parsed, "Someone Else", "8740")
    assert ok is False
    assert reason == "name_mismatch"


def test_verify_recipient_phone_mismatch_rejected():
    parsed = parse_telebirr_sms(REAL_SMS)
    ok, reason = verify_recipient(parsed, "Hanan Reda", "1234")
    assert ok is False
    assert reason == "phone_mismatch"


def test_validate_deposit_amount_below_minimum():
    parsed = parse_telebirr_sms(REAL_SMS)
    ok, reason = validate_deposit_amount(parsed, min_amount=Decimal("50"))
    assert ok is False
    assert "below_minimum" in reason


def test_validate_deposit_amount_matches_expected():
    parsed = parse_telebirr_sms(REAL_SMS)
    ok, _ = validate_deposit_amount(parsed, expected_amount=Decimal("30.00"))
    assert ok is True


def test_validate_deposit_amount_mismatch():
    parsed = parse_telebirr_sms(REAL_SMS)
    ok, reason = validate_deposit_amount(parsed, expected_amount=Decimal("50.00"))
    assert ok is False
    assert reason == "amount_mismatch"
