import time

from app.services.rate_limiter import RateLimiter, get_client_ip


def test_allows_requests_under_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is True


def test_blocks_requests_over_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        assert limiter.allow("user1") is True
    assert limiter.allow("user1") is False


def test_different_keys_have_independent_limits():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is False
    # user2 is unaffected by user1 having hit their limit
    assert limiter.allow("user2") is True
    assert limiter.allow("user2") is True
    assert limiter.allow("user2") is False


def test_window_slides_old_hits_age_out():
    limiter = RateLimiter(max_requests=2, window_seconds=0.2)
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is False
    time.sleep(0.25)
    assert limiter.allow("user1") is True  # old hits aged out of the window


def test_peek_blocked_does_not_record_a_hit():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.peek_blocked("user1") is False
    assert limiter.peek_blocked("user1") is False  # calling peek repeatedly never counts
    assert limiter.allow("user1") is True
    assert limiter.peek_blocked("user1") is True


def test_reset_clears_a_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("user1") is True
    assert limiter.allow("user1") is False
    limiter.reset("user1")
    assert limiter.allow("user1") is True


def test_retry_after_seconds_reflects_remaining_window():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    limiter.allow("user1")
    remaining = limiter.retry_after_seconds("user1")
    assert 0 < remaining <= 10


def test_retry_after_seconds_zero_when_no_hits():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    assert limiter.retry_after_seconds("never-hit") == 0.0


def test_failure_only_counting_pattern():
    """The pattern app/admin_auth.py uses: peek_blocked() gates before
    doing work, allow() is only called in the failure branch so success
    never counts against the limit."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    def attempt(succeeds: bool) -> str:
        if limiter.peek_blocked("ip1"):
            return "blocked"
        if succeeds:
            limiter.reset("ip1")
            return "ok"
        limiter.allow("ip1")
        return "failed"

    assert attempt(succeeds=False) == "failed"
    assert attempt(succeeds=False) == "failed"
    assert attempt(succeeds=False) == "blocked"  # 2 failures hit the limit
    # a correct attempt right after being blocked is still blocked —
    # peek_blocked gates before we even look at whether it would succeed
    assert attempt(succeeds=True) == "blocked"


class _FakeRequest:
    def __init__(self, headers=None, client_host=None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})() if client_host else None


def test_get_client_ip_prefers_x_forwarded_for():
    req = _FakeRequest(headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1"}, client_host="10.0.0.1")
    assert get_client_ip(req) == "203.0.113.5"


def test_get_client_ip_falls_back_to_client_host():
    req = _FakeRequest(headers={}, client_host="192.168.1.1")
    assert get_client_ip(req) == "192.168.1.1"


def test_get_client_ip_handles_missing_client():
    req = _FakeRequest(headers={}, client_host=None)
    assert get_client_ip(req) == "unknown"
