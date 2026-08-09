"""
Lightweight in-memory sliding-window rate limiter.

Process-local state — same pattern and the same tradeoff already made
for the Telebirr circuit breaker in telebirr_verify.py: fine for a
single uvicorn worker process, which is this deployment's actual shape
(see README's deployment notes). If this API ever runs multiple worker
processes behind a load balancer, each worker gets its own independent
counters instead of a shared one — move this to Redis if that matters
more than the simplicity of leaving it as-is.

Two usage patterns, both built on the same sliding window:
  - `allow(key)` — call once per request, records the attempt and
    returns whether it's within limit. Use for "every call counts"
    limits (deposit submissions, bet placement, the global per-IP guard).
  - `peek_blocked(key)` + manually calling `allow(key)` only on failure —
    use when only *failures* should count against the limit (admin auth:
    a legitimate admin using the right token every time should never be
    throttled; repeated wrong tokens should be).
"""

import threading
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, hits: list[float], now: float) -> list[float]:
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.pop(0)
        return hits

    def allow(self, key: str) -> bool:
        """Records this call as a hit against key's window. Returns False
        (without recording) if key is already at the limit."""
        now = time.time()
        with self._lock:
            hits = self._prune(self._hits[key], now)
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True

    def peek_blocked(self, key: str) -> bool:
        """Checks whether key is currently at/over the limit, without
        recording a new hit — for gating before doing any real work."""
        now = time.time()
        with self._lock:
            hits = self._prune(self._hits.get(key, []), now)
            return len(hits) >= self.max_requests

    def retry_after_seconds(self, key: str) -> float:
        """How long until the oldest hit in the current window ages out
        and a slot frees up. Approximate — good enough for a Retry-After
        hint, not a precision guarantee."""
        now = time.time()
        with self._lock:
            hits = self._hits.get(key, [])
            if not hits:
                return 0.0
            return max(hits[0] + self.window_seconds - now, 0.0)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


def get_client_ip(request) -> str:
    """Prefers X-Forwarded-For (set by Render's proxy and most reverse
    proxies) over request.client.host, which behind a proxy is the
    proxy's own address, not the real caller's — using it directly would
    silently rate-limit every user on the same deployment together
    instead of individually."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
