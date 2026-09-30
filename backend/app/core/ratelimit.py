"""Fixed-window rate limits in Redis (B6): login attempts per client address, copilot
questions per user.

A window is ``INCR key`` + ``EXPIRE key window`` on first use. If Redis is unreachable the
request is allowed and a warning logged: a limiter outage must not lock everyone out.
"""

import logging
from typing import Protocol, cast

import redis

from app.core.config import get_settings
from app.core.errors import RateLimitedError

log = logging.getLogger("smriti.ratelimit")


class Counter(Protocol):
    def incr(self, name: str) -> int: ...
    def expire(self, name: str, time: int) -> bool: ...
    def ttl(self, name: str) -> int: ...


_client: Counter | None = None


def _redis() -> Counter:
    global _client
    if _client is None:
        _client = cast(Counter, redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5))
    return _client


def set_counter(counter: Counter | None) -> None:
    """Swap the backend (tests use an in-memory counter)."""
    global _client
    _client = counter


def hit(key: str, limit: int, window_s: int = 60, counter: Counter | None = None) -> None:
    """Count one request under ``key``; raise RateLimitedError (429) past ``limit``."""
    c = counter or _redis()
    name = f"rl:{key}"
    try:
        n = c.incr(name)
        if n == 1:
            c.expire(name, window_s)
        if n > limit:
            ttl = c.ttl(name)
            raise RateLimitedError(
                "Too many requests; try again shortly.", max(1, ttl if ttl > 0 else window_s)
            )
    except redis.RedisError as exc:
        log.warning("rate limiter unavailable, allowing request: %s", exc)
