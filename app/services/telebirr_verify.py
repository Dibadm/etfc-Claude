"""
Verifies a Telebirr deposit against Ethio Telecom's own official online
receipt system — the actual "checks online" step, not just SMS-text regex
matching. A pasted SMS can be edited by hand; the receipt page at
transactioninfo.ethiotelecom.et can't (it's Ethio Telecom's own record of
the transaction), so this is what turns "the user says they paid" into
"Ethio Telecom's own system confirms this transaction happened."

Ported from Habesha Bet's telebirr_verify.py (github.com/Dibadm/mosses-,
backend/telebirr_verify.py) — same URL, same parsing, same circuit
breaker. Adapted: Decimal instead of float for the amount, module-level
circuit-breaker state kept as-is (matches the original; see the note on
`_CircuitBreaker` below for why this is fine for a single-process
deployment and what to change if this ever runs multi-process).
"""

import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("etfc_betting.telebirr_verify")

TELEBIRR_RECEIPT_URL = "https://transactioninfo.ethiotelecom.et/receipt/{receipt_no}"

_CIRCUIT_BREAKER_WINDOW = 60
_CIRCUIT_BREAKER_THRESHOLD = 5
_CIRCUIT_BREAKER_COOLDOWN = 120


class _CircuitBreaker:
    """Process-local state, same as the original Habesha Bet module. Fine
    for a single `uvicorn` worker process (the deployment this was built
    for — see README). If this API ever runs with multiple worker
    processes behind a load balancer, each worker gets its own circuit
    breaker instead of a shared one — move this to Redis/the DB if that
    matters more than the simplicity of leaving it as-is."""

    def __init__(self):
        self.failure_timestamps: list[float] = []
        self.open_until = 0.0

    def record(self, success: bool):
        now = time.time()
        if success:
            self.failure_timestamps = []
            self.open_until = 0.0
            return
        self.failure_timestamps.append(now)
        cutoff = now - _CIRCUIT_BREAKER_WINDOW
        self.failure_timestamps = [t for t in self.failure_timestamps if t >= cutoff]
        if len(self.failure_timestamps) >= _CIRCUIT_BREAKER_THRESHOLD:
            self.open_until = now + _CIRCUIT_BREAKER_COOLDOWN
            logger.warning("[telebirr_verify] circuit breaker open until %s", self.open_until)

    def is_open(self) -> bool:
        return time.time() < self.open_until


_circuit = _CircuitBreaker()
_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; ETFCBetting/1.0)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en,am;q=0.9",
    }
)


@dataclass
class ReceiptVerification:
    ok: bool
    amount: Decimal | None = None
    recipient_name: str = ""
    recipient_phone_last4: str = ""
    timestamp: str = ""
    error: str | None = None


def verify_receipt_online(receipt_no: str, timeout: int = 10) -> ReceiptVerification:
    if not receipt_no or not re.match(r"^[A-Za-z0-9]{8,20}$", receipt_no):
        return ReceiptVerification(ok=False, error="invalid_receipt_number")

    if _circuit.is_open():
        return ReceiptVerification(ok=False, error="receipt_site_circuit_open")

    url = TELEBIRR_RECEIPT_URL.format(receipt_no=receipt_no.upper())

    max_retries = 2
    backoff = 1.0
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = _session.get(url, timeout=(timeout, timeout))
            if resp.status_code == 200:
                _circuit.record(True)
                result = parse_receipt_html(resp.text)
                if not result.ok:
                    _circuit.record(False)
                    return result
                return result

            if resp.status_code == 404:
                _circuit.record(False)
                return ReceiptVerification(ok=False, error="receipt_not_found_http_404")

            last_error = f"receipt_not_found_http_{resp.status_code}"
        except requests.Timeout:
            last_error = "receipt_site_timeout"
        except requests.ConnectionError:
            last_error = "receipt_site_unreachable"
        except Exception as e:
            logger.warning("[telebirr_verify] unexpected error fetching receipt %s: %s", receipt_no, e)
            last_error = "receipt_fetch_error"

        if attempt < max_retries:
            time.sleep(backoff)
            backoff *= 2

    _circuit.record(False)
    return ReceiptVerification(ok=False, error=last_error)


def parse_receipt_html(html: str) -> ReceiptVerification:
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        return ReceiptVerification(ok=False, error=f"html_parse_error: {e}")

    amount = _extract_amount(soup)
    if amount is None:
        return ReceiptVerification(ok=False, error="amount_not_found_on_receipt")

    return ReceiptVerification(
        ok=True,
        amount=amount,
        recipient_name=_extract_recipient_name(soup) or "",
        recipient_phone_last4=_extract_recipient_phone_last4(soup) or "",
        timestamp=_extract_timestamp(soup) or "",
    )


def _extract_amount(soup) -> Decimal | None:
    text = soup.get_text(separator=" ", strip=True)
    m = re.search(r"(?:amount|transferred|debit|paid)[\s:]*ETB\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"ETB\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if m:
        try:
            return Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            pass
    return None


def _extract_recipient_name(soup) -> str | None:
    text = soup.get_text(separator=" ", strip=True)
    patterns = [
        r"(?:to|recipient|beneficiary)[\s:]*([A-Za-z][A-Za-z\s]{2,40}?)(?:\s*\(|\s*$|\s*–|\s*-)",
        r"Payee[\s:]*([A-Za-z][A-Za-z\s]{2,40}?)(?:\s*\(|\s*$|\s*–|\s*-)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) >= 2:
                return name
    return None


def _extract_recipient_phone_last4(soup) -> str | None:
    text = soup.get_text(separator=" ", strip=True)
    m = re.search(r"(?:\(|phone[\s:]*|to[\s:]*)(?:2519|09)?\d*\*+(\d{4})(?:\))?", text)
    return m.group(1) if m else None


def _extract_timestamp(soup) -> str | None:
    text = soup.get_text(separator=" ", strip=True)
    m = re.search(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", text)
    return m.group(1) if m else None
