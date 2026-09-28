"""Readiness checks for PostgreSQL (+ required extensions), Redis and object storage."""

import time
from collections.abc import Callable
from typing import Literal

import redis
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import get_engine
from app.storage.s3 import bucket_exists, get_s3_client


class ComponentStatus(BaseModel):
    name: str
    ok: bool
    latency_ms: float
    detail: str = ""


class ReadinessReport(BaseModel):
    status: Literal["ready", "not_ready"]
    components: list[ComponentStatus]


Check = Callable[[Settings], ComponentStatus]


def _timed(name: str, fn: Callable[[], str]) -> ComponentStatus:
    started = time.perf_counter()
    try:
        detail = fn()
        ok = True
    except Exception as exc:  # a readiness probe reports failures, it never raises
        detail, ok = f"{type(exc).__name__}: {exc}"[:300], False
    return ComponentStatus(
        name=name, ok=ok, latency_ms=round((time.perf_counter() - started) * 1000, 1), detail=detail
    )


def check_database(settings: Settings) -> ComponentStatus:
    def probe() -> str:
        with get_engine().connect() as conn:
            installed = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
        missing = [e for e in settings.required_pg_extensions if e not in installed]
        if missing:
            raise RuntimeError(f"missing extensions {missing} (run: python -m app.cli bootstrap)")
        return "extensions ok: " + ", ".join(settings.required_pg_extensions)

    return _timed("postgres", probe)


def check_redis(settings: Settings) -> ComponentStatus:
    def probe() -> str:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.readiness_timeout_s,
            socket_timeout=settings.readiness_timeout_s,
        )
        try:
            client.ping()
        finally:
            client.close()
        return "ping ok"

    return _timed("redis", probe)


def check_object_storage(settings: Settings) -> ComponentStatus:
    def probe() -> str:
        client = get_s3_client()
        missing = [b for b in settings.s3_buckets if not bucket_exists(client, b)]
        if missing:
            raise RuntimeError(f"missing buckets {missing} (run: python -m app.cli bootstrap)")
        return "buckets ok: " + ", ".join(settings.s3_buckets)

    return _timed("object_storage", probe)


DEFAULT_CHECKS: list[Check] = [check_database, check_redis, check_object_storage]


def run_checks(settings: Settings, checks: list[Check]) -> ReadinessReport:
    components = [check(settings) for check in checks]
    return ReadinessReport(
        status="ready" if all(c.ok for c in components) else "not_ready", components=components
    )
