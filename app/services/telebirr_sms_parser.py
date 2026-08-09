"""
Parses a pasted Telebirr payment confirmation SMS.

Ported from Habesha Bet's sms_parser.py (github.com/Dibadm/mosses-,
backend/sms_parser.py) — same regex patterns, tested against the same real
Telebirr SMS format. The one deliberate change: amounts are Decimal here,
not float, to match how the rest of this codebase handles money (see
app/services/wallet_service.py) — float has no place in anything that
touches a balance.

Real Telebirr SMS format this is tested against:

  "Dear Abdi
   You have transferred ETB 30.00 to hanan reda (2519****8740) on
   14/06/2026 20:47:00. Your transaction number is DFE8VVNNIC. The
   service fee is ETB 0.87 and 15% VAT on the service fee is ETB 0.13.
   Your current E-Money Account balance is ETB 1,429.52. To download
   your payment information please click this link:
   https://transactioninfo.ethiotelecom.et/receipt/DFE8VVNNIC.

   Thank you for using telebirr
   Ethio telecom"

Fields extracted:
  amount           -> Decimal("30.00")  (the transferred amount, NOT fee or balance)
  recipient_name   -> "hanan reda"
  recipient_last4  -> "8740"
  reference        -> "DFE8VVNNIC"
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass
class ParsedDeposit:
    amount: Decimal
    recipient_name: str | None
    recipient_last4: str | None
    reference: str
    raw_text: str


def parse_telebirr_sms(sms_text: str) -> ParsedDeposit | None:
    """Returns None if the SMS can't be parsed (missing amount or
    reference) — callers should treat that as "reject this deposit
    attempt", not raise."""
    if not sms_text or len(sms_text.strip()) < 20:
        return None

    text = sms_text.strip()

    # ---- 1. Amount ----
    # Primary: "transferred ETB 30.00" — the actual sent amount. Using the
    # "transferred" keyword avoids matching the service fee / current
    # balance, which also appear as "ETB X.XX" later in the message.
    amount_match = re.search(r"transferred\s+ETB\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if not amount_match:
        # Fallback: first "ETB X.XX" found (works for some Telebirr variants)
        amount_match = re.search(r"ETB\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if not amount_match:
        return None

    try:
        amount = Decimal(amount_match.group(1).replace(",", ""))
    except InvalidOperation:
        return None

    # ---- 2. Recipient name ----
    # Pattern: "to hanan reda (" — text between "to " and " ("
    name_match = re.search(r"\btransferred\s+ETB[^t]+to\s+([A-Za-z\s]+?)\s*\(", text, re.IGNORECASE)
    if not name_match:
        name_match = re.search(r"\bto\s+([A-Za-z\s]{2,40}?)\s*\(", text, re.IGNORECASE)
    recipient_name = name_match.group(1).strip() if name_match else None

    # ---- 3. Recipient phone last 4 digits ----
    # Pattern: "(2519****8740)" or "(09****1234)"
    phone_match = re.search(r"\((?:2519|09)?\d*\*+(\d{4})\)", text)
    recipient_last4 = phone_match.group(1) if phone_match else None

    # ---- 4. Transaction reference ----
    # Primary: "Your transaction number is DFE8VVNNIC"
    ref_match = re.search(r"transaction number is\s+([A-Za-z0-9]+)", text, re.IGNORECASE)
    if ref_match:
        reference = ref_match.group(1).upper()
    else:
        # Fallback: any uppercase alphanumeric token of 8+ chars (avoids
        # matching common words)
        fallback = re.search(r"\b([A-Z0-9]{8,})\b", text)
        reference = fallback.group(1) if fallback else None

    if reference is None:
        return None

    return ParsedDeposit(
        amount=amount,
        recipient_name=recipient_name,
        recipient_last4=recipient_last4,
        reference=reference,
        raw_text=text,
    )


def extract_receipt_number(sms_text: str) -> str | None:
    """Extract the receipt/transaction number used to look the transaction
    up on Ethio Telecom's own online receipt system (see telebirr_verify.py).
    Matches:
      - "Your transaction number is DFE8VVNNIC"
      - ".../receipt/DFE8VVNNIC"
      - Fallback: any 8-12 char alphanumeric token
    """
    if not sms_text:
        return None
    text = sms_text.strip()

    m = re.search(r"transaction number is\s+([A-Za-z0-9]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r"transactioninfo\.ethiotelecom\.et/receipt/([A-Za-z0-9]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    tokens = re.findall(r"\b([A-Z0-9]{8,12})\b", text.upper())
    if tokens:
        return tokens[0]
    return None


def verify_recipient(parsed: ParsedDeposit, expected_name: str, expected_last4: str) -> tuple[bool, str]:
    """Checks the SMS was sent to the expected (currently active) deposit
    account. Comparisons are case-insensitive. If a field couldn't be
    extracted from the SMS (None), that check is skipped — the unique
    reference-ID duplicate check is the primary anti-fraud mechanism here;
    name/phone matching is a secondary layer, not the only one.

    Returns (ok, reason). ok=False means "reject this deposit."
    """
    if parsed.recipient_name and expected_name:
        if parsed.recipient_name.strip().lower() != expected_name.strip().lower():
            return False, "name_mismatch"

    if parsed.recipient_last4 and expected_last4:
        if parsed.recipient_last4 != expected_last4:
            return False, "phone_mismatch"

    return True, "ok"


def validate_deposit_amount(
    parsed: ParsedDeposit, expected_amount: Decimal | None = None, min_amount: Decimal | None = None
) -> tuple[bool, str]:
    if min_amount is not None and parsed.amount < min_amount:
        return False, f"below_minimum_{min_amount}"
    if expected_amount is not None and abs(parsed.amount - expected_amount) > Decimal("0.01"):
        return False, "amount_mismatch"
    return True, "ok"
