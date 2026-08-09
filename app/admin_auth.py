"""
Gates every admin-only endpoint (creating fights/markets, adjusting odds,
suspending markets, settling/voiding fights, viewing liability) behind a
single bearer token. This was an explicitly flagged, deliberate gap left
open through Phase 1 and 2 — fine while only the operator was calling
these URLs directly, not fine once the product is live and those URLs
are guessable/discoverable.

Deliberately simple: one shared secret, not per-admin accounts or roles.
Fine for a single-operator product; if a team ends up running this,
upgrade to per-user admin accounts before handing the token out to
multiple people.

Also rate-limits repeated wrong-token attempts per IP — a single shared
secret is exactly the kind of thing worth brute-force-guessing if
nothing stops repeated attempts. Only failures count against the limit,
so a legitimate admin using the right token is never throttled by their
own past typos.
"""

import hmac

from fastapi import Header, HTTPException, Request

from app.config import get_settings
from app.services.rate_limiter import RateLimiter, get_client_ip

# 10 wrong-token attempts per 5 minutes per IP. Generous enough that a
# real admin mistyping the token a couple times never gets blocked;
# tight enough that brute-forcing a token this way is impractical.
_admin_auth_failures = RateLimiter(max_requests=10, window_seconds=300)


def require_admin(request: Request, authorization: str = Header(...)) -> None:
    settings = get_settings()
    if not settings.admin_token:
        # Fails closed: refuse to treat "no token configured" as "no auth
        # required" — that would silently reopen every admin endpoint.
        raise HTTPException(500, "Server is missing ETFC_ADMIN_TOKEN — admin endpoints cannot be used until it's set")

    client_ip = get_client_ip(request)
    if _admin_auth_failures.peek_blocked(client_ip):
        retry_after = _admin_auth_failures.retry_after_seconds(client_ip)
        raise HTTPException(
            429,
            "Too many failed admin auth attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    if not authorization.startswith("Bearer "):
        _admin_auth_failures.allow(client_ip)
        raise HTTPException(401, "Expected 'Authorization: Bearer <token>'")

    provided = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(provided, settings.admin_token):
        _admin_auth_failures.allow(client_ip)
        raise HTTPException(401, "Invalid admin token")

    _admin_auth_failures.reset(client_ip)
