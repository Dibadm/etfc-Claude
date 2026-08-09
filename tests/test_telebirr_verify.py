from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services import telebirr_verify


SAMPLE_RECEIPT_HTML = """
<html><body>
  <div>Payment Receipt</div>
  <div>Transferred Amount: ETB 30.00</div>
  <div>Payee: hanan reda</div>
  <div>To: (2519****8740)</div>
  <div>Date: 14/06/2026 20:47:00</div>
</body></html>
"""


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """The circuit breaker is process-local state (see telebirr_verify.py's
    docstring) — reset it between tests so one test's failures don't trip
    the breaker for the next."""
    telebirr_verify._circuit.failure_timestamps = []
    telebirr_verify._circuit.open_until = 0.0
    yield
    telebirr_verify._circuit.failure_timestamps = []
    telebirr_verify._circuit.open_until = 0.0


def test_parse_receipt_html_extracts_amount_and_recipient():
    result = telebirr_verify.parse_receipt_html(SAMPLE_RECEIPT_HTML)
    assert result.ok is True
    assert result.amount == Decimal("30.00")
    assert result.recipient_phone_last4 == "8740"


def test_parse_receipt_html_missing_amount_fails():
    result = telebirr_verify.parse_receipt_html("<html><body>Nothing useful here</body></html>")
    assert result.ok is False
    assert result.error == "amount_not_found_on_receipt"


def test_verify_receipt_online_rejects_malformed_receipt_number():
    result = telebirr_verify.verify_receipt_online("not valid!!")
    assert result.ok is False
    assert result.error == "invalid_receipt_number"


@patch("app.services.telebirr_verify._session")
def test_verify_receipt_online_success(mock_session):
    mock_resp = MagicMock(status_code=200, text=SAMPLE_RECEIPT_HTML)
    mock_session.get.return_value = mock_resp

    result = telebirr_verify.verify_receipt_online("DFE8VVNNIC")
    assert result.ok is True
    assert result.amount == Decimal("30.00")


@patch("app.services.telebirr_verify._session")
def test_verify_receipt_online_404_not_found(mock_session):
    mock_resp = MagicMock(status_code=404, text="")
    mock_session.get.return_value = mock_resp

    result = telebirr_verify.verify_receipt_online("NOSUCHRCPT1")
    assert result.ok is False
    assert result.error == "receipt_not_found_http_404"


@patch("app.services.telebirr_verify._session")
def test_verify_receipt_online_timeout_reported_as_site_issue_not_rejection(mock_session):
    import requests

    mock_session.get.side_effect = requests.Timeout()
    result = telebirr_verify.verify_receipt_online("DFE8VVNNIC")
    assert result.ok is False
    assert result.error == "receipt_site_timeout"


@patch("app.services.telebirr_verify._session")
def test_circuit_breaker_opens_after_repeated_failures(mock_session):
    import requests

    mock_session.get.side_effect = requests.ConnectionError()

    # Threshold is 5 failures within the window (see telebirr_verify.py)
    for _ in range(5):
        telebirr_verify.verify_receipt_online("DFE8VVNNIC")

    assert telebirr_verify._circuit.is_open() is True

    # While open, it should fail fast without even attempting a request
    mock_session.reset_mock()
    result = telebirr_verify.verify_receipt_online("DFE8VVNNIC")
    assert result.ok is False
    assert result.error == "receipt_site_circuit_open"
    mock_session.get.assert_not_called()


@patch("app.services.telebirr_verify._session")
def test_circuit_breaker_resets_on_success(mock_session):
    import requests

    mock_session.get.side_effect = requests.ConnectionError()
    for _ in range(3):
        telebirr_verify.verify_receipt_online("DFE8VVNNIC")
    assert len(telebirr_verify._circuit.failure_timestamps) == 3

    mock_session.get.side_effect = None
    mock_session.get.return_value = MagicMock(status_code=200, text=SAMPLE_RECEIPT_HTML)
    telebirr_verify.verify_receipt_online("DFE8VVNNIC")

    assert telebirr_verify._circuit.failure_timestamps == []
