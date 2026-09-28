"""Operational CLI. Run: ``python -m app.cli --help``.

bootstrap  wait for dependencies, apply migrations, create object-storage buckets
check      print the readiness report (and optionally round-trip a Celery task)
"""

import json
import time
from collections.abc import Callable
from pathlib import Path

import typer
from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.health import DEFAULT_CHECKS, check_redis, run_checks
from app.core.logging import configure_logging
from app.db.session import get_engine
from app.storage.s3 import ensure_buckets, get_s3_client

cli = typer.Typer(add_completion=False, no_args_is_help=True)

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _wait_for(name: str, probe: Callable[[], None], timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            probe()
            typer.echo(f"[bootstrap] {name}: reachable")
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                raise typer.Exit(code=1) from exc
            typer.echo(f"[bootstrap] waiting for {name}: {type(exc).__name__}")
            time.sleep(2)


def _db_probe() -> None:
    with get_engine().connect():
        pass


def _s3_probe() -> None:
    get_s3_client().list_buckets()


def _redis_probe() -> None:
    status = check_redis(get_settings())
    if not status.ok:
        raise RuntimeError(status.detail)


@cli.command()
def bootstrap(timeout_s: float = typer.Option(90.0, help="Max wait per dependency")) -> None:
    """Idempotent: safe to run on every deploy."""
    configure_logging(json_output=False)
    settings = get_settings()
    _wait_for("postgres", _db_probe, timeout_s)
    _wait_for("redis", _redis_probe, timeout_s)
    _wait_for("object storage", _s3_probe, timeout_s)

    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    typer.echo("[bootstrap] migrations: at head")

    created = ensure_buckets(get_s3_client(), settings.s3_buckets)
    typer.echo(f"[bootstrap] buckets: created {created or 'none'}; required {settings.s3_buckets}")


@cli.command()
def check(worker: bool = typer.Option(False, help="Also round-trip a Celery ping task")) -> None:
    """Exit code 0 only if every dependency (and optionally the worker) is healthy."""
    report = run_checks(get_settings(), DEFAULT_CHECKS)
    typer.echo(json.dumps(report.model_dump(), indent=2))
    ok = report.status == "ready"
    if worker:
        from app.workers.celery_app import ping

        try:
            result = ping.delay().get(timeout=15)
            typer.echo(f"worker: {result}")
        except Exception as exc:
            typer.echo(f"worker: FAILED {type(exc).__name__}: {exc}")
            ok = False
    raise typer.Exit(code=0 if ok else 1)


if __name__ == "__main__":
    cli()
