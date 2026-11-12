"""
Service-to-service auth for /internal routes, a login-failure throttle, and
per-dealer daily quotas for costly operations.
"""
import hmac
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_service_token(x_service_token: str = Header(default="")) -> None:
    expected = get_settings().service_token
    # Fail closed: an unset token must never match an empty header.
    if not expected or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(status_code=401, detail="not authorized")


class LoginThrottle:
    """Sliding-window cap on failed logins.

    - 5 failures per (email, client IP): stops guessing from one source
      without letting a stranger lock a dealer out from the dealer's own IP.
    - 50 failures per email across all IPs: hard ceiling on distributed guessing.

    Client IP is the real one only when uvicorn runs with --proxy-headers
    behind the ingress (see Dockerfile).

    ponytail: in-process memory — each replica counts separately and a restart
    resets it. Move to Redis when running more than one replica.
    """

    WINDOW_SECONDS = 15 * 60
    MAX_FAILURES = 5
    MAX_FAILURES_PER_EMAIL = 50

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _count(self, key: str) -> int:
        hits = self._failures[key]
        cutoff = time.monotonic() - self.WINDOW_SECONDS
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return len(hits)

    def check(self, email: str, ip: str) -> None:
        if self._count(f"{email}|{ip}") >= self.MAX_FAILURES or self._count(email) >= self.MAX_FAILURES_PER_EMAIL:
            raise HTTPException(status_code=429, detail="too many failed sign-in attempts, try again later")

    def record_failure(self, email: str, ip: str) -> None:
        now = time.monotonic()
        self._failures[f"{email}|{ip}"].append(now)
        self._failures[email].append(now)

    def reset(self, email: str, ip: str) -> None:
        self._failures.pop(f"{email}|{ip}", None)


login_throttle = LoginThrottle()


class DailyQuota:
    """At most `limit` uses per key per rolling 24h.

    ponytail: in-process memory, same ceiling as LoginThrottle — per replica,
    reset on restart. Move to Redis/DB when running more than one replica.
    """

    WINDOW_SECONDS = 24 * 60 * 60

    def __init__(self, limit: int, detail: str) -> None:
        self.limit = limit
        self.detail = detail
        self._uses: dict[str, deque[float]] = defaultdict(deque)

    def take(self, key: str) -> None:
        uses = self._uses[key]
        now = time.monotonic()
        while uses and uses[0] <= now - self.WINDOW_SECONDS:
            uses.popleft()
        if len(uses) >= self.limit:
            raise HTTPException(status_code=429, detail=self.detail)
        uses.append(now)


# Every parse is a paid LLM call (up to 64k output tokens) — cap it per dealer.
rate_sheet_parse_quota = DailyQuota(20, "daily rate sheet upload limit reached, try again tomorrow")
