"""Operational CLI. Run: ``python -m app.cli --help``.

bootstrap  wait for dependencies, apply migrations, create object-storage buckets
check      print the readiness report (and optionally round-trip a Celery task)
seed       generate the synthetic field and ingest its reports
extract    (re-)run S2 extraction over ingested reports
index      (re-)run S5 search indexing (embeddings + lesson cards)
realtime   build the real-time assets: classifiers, Deja Vu library, replay file (B4)
user-add   create a local user for jwt auth mode (B5)
"""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.health import DEFAULT_CHECKS, check_redis, run_checks
from app.core.logging import configure_logging
from app.db.session import get_engine
from app.storage.s3 import ensure_buckets, get_s3_client

if TYPE_CHECKING:
    from app.synthetic.generator import SyntheticField

cli = typer.Typer(add_completion=False, no_args_is_help=True)

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
# Relative to backend/, where the CLI is run from in development and CI.
DEFAULT_OPENAPI_OUT = Path("../frontend/src/lib/api/openapi.json")


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


@cli.command()
def openapi(
    out: Annotated[Path, typer.Option(help="Output file ('-' for stdout)")] = DEFAULT_OPENAPI_OUT,
) -> None:
    """Deterministic (sorted keys) so CI can diff it against the committed copy."""
    from app.main import create_app

    schema = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    if str(out) == "-":
        typer.echo(schema, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema, encoding="utf-8")
    typer.echo(f"wrote {out}")


@cli.command()
def seed(
    wells: Annotated[int, typer.Option(help="Completed wells to generate")] = 40,
    documents: Annotated[bool, typer.Option(help="Render and ingest reports")] = True,
    max_documents: Annotated[int, typer.Option(help="Ingest at most N reports (0 = all)")] = 0,
    inline: Annotated[bool, typer.Option(help="Process here instead of via the worker")] = False,
    wait: Annotated[bool, typer.Option(help="Wait until queued reports are processed")] = False,
    timeout_s: Annotated[float, typer.Option(help="Max wait for --wait")] = 900.0,
    realtime: Annotated[bool, typer.Option(help="Also build the real-time assets")] = True,
) -> None:
    """Idempotent: re-seeding updates wells in place and skips reports already ingested."""
    import tempfile

    from sqlalchemy import func, select

    from app.db.models import Document
    from app.db.session import session_scope
    from app.ingest.service import process_document, store_upload
    from app.normalise.master_import import import_field
    from app.synthetic.documents import write_documents
    from app.synthetic.generator import generate

    configure_logging(json_output=False)
    settings = get_settings()
    data = generate(wells)
    with session_scope() as session:
        typer.echo(f"[seed] master data: {import_field(session, data)}")
    truth = data.to_json()
    new_ids: list[int] = []
    if documents:
        with tempfile.TemporaryDirectory() as tmp:
            docs = write_documents(data, Path(tmp))
            truth["documents"] = [d.__dict__ for d in docs]
            if max_documents:
                docs = docs[:max_documents]
            for gd in docs:
                with session_scope() as session:
                    stored = store_upload(
                        session, gd.file, (Path(tmp) / gd.file).read_bytes(), "seed"
                    )
                    if not stored.duplicate:
                        new_ids.append(stored.document.id)
        typer.echo(f"[seed] reports: {len(docs)} selected, {len(new_ids)} new")
    else:  # keep the report list of an earlier seed (the extraction eval reads it)
        try:
            earlier = json.loads(
                get_s3_client()
                .get_object(Bucket=settings.s3_bucket_raw, Key="synthetic/truth.json")["Body"]
                .read()
            )
            truth["documents"] = earlier.get("documents", [])
        except Exception:
            truth["documents"] = []
    get_s3_client().put_object(
        Bucket=settings.s3_bucket_raw,
        Key="synthetic/truth.json",
        Body=json.dumps(truth).encode(),
        ContentType="application/json",
    )
    typer.echo(
        "[seed] ground truth written to s3://" + settings.s3_bucket_raw + "/synthetic/truth.json"
    )
    if inline:
        from app.extract.service import extract_document
        from app.search.service import index_document

        for doc_id in new_ids:
            with session_scope() as session:
                process_document(session, doc_id)
        for doc_id in new_ids:  # after all ingestion: one report's events merge with the next
            with session_scope() as session:
                extract_document(session, doc_id)
            with session_scope() as session:
                index_document(session, doc_id)
    else:
        from app.ingest.tasks import process_document_task

        for doc_id in new_ids:
            process_document_task.delay(doc_id)
    if wait and new_ids and not inline:
        deadline = time.monotonic() + timeout_s
        while True:
            with session_scope() as session:
                # Every stage: ingestion, then extraction, then search indexing.
                pending = (
                    session.scalar(
                        select(func.count()).where(
                            Document.id.in_(new_ids),
                            Document.ingest_status.in_(("queued", "processing"))
                            | Document.extract_status.in_(("pending", "running"))
                            | Document.index_status.in_(("pending", "running")),
                            Document.ingest_status != "failed",
                        )
                    )
                    or 0
                )
            if pending == 0:
                break
            if time.monotonic() > deadline:
                typer.echo(f"[seed] timed out with {pending} reports still pending")
                raise typer.Exit(code=1)
            time.sleep(3)
    with session_scope() as session:
        rows = session.execute(
            select(Document.ingest_status, func.count()).group_by(Document.ingest_status)
        ).all()
    typer.echo(f"[seed] document status: {dict((str(k), int(v)) for k, v in rows)}")
    if realtime:
        _build_realtime(data)


def _build_realtime(data: "SyntheticField", train_wells: int = 120) -> None:
    from app.db.session import session_scope
    from app.risk.assets import build_all

    with session_scope() as session:
        build_all(session, data, train_wells=train_wells, log=typer.echo)


@cli.command(name="realtime")
def realtime_build(
    wells: Annotated[int, typer.Option(help="Completed wells of the seeded field")] = 40,
    train_wells: Annotated[int, typer.Option(help="Synthetic training-field wells")] = 120,
) -> None:
    """(Re)build the real-time assets over an already seeded database."""
    from app.synthetic.generator import generate

    configure_logging(json_output=False)
    _build_realtime(generate(wells), train_wells)


def _select_documents(document_id: int | None, all_: bool, status_col: str) -> list[int]:
    from sqlalchemy import select

    from app.db.models import Document
    from app.db.session import session_scope

    with session_scope() as session:
        q = select(Document.id).where(Document.ingest_status.in_(("processed", "needs_review")))
        if document_id is not None:
            q = q.where(Document.id == document_id)
        elif not all_:
            q = q.where(getattr(Document, status_col).in_(("pending", "failed")))
        return list(session.scalars(q.order_by(Document.id)))


@cli.command()
def extract(
    document_id: Annotated[int | None, typer.Option(help="Only this document")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Re-extract every document")] = False,
    queue: Annotated[
        bool, typer.Option(help="Enqueue on the worker instead of running here")
    ] = False,
) -> None:
    """Default: documents whose extraction is pending or failed, in upload order."""
    from app.db.session import session_scope
    from app.extract.service import extract_document, mark_failed

    configure_logging(json_output=False)
    ids = _select_documents(document_id, all_, "extract_status")
    totals: dict[str, int] = {}
    for doc_id in ids:
        if queue:
            from app.workers.celery_app import celery_app

            celery_app.send_task("extract.process_document", args=[doc_id, False])
            continue
        try:
            with session_scope() as session:
                result = extract_document(session, doc_id)
        except Exception as exc:
            with session_scope() as session:
                mark_failed(session, doc_id, f"{type(exc).__name__}: {exc}")
            result = {"status": "failed"}
            typer.echo(f"[extract] document {doc_id}: FAILED {type(exc).__name__}: {exc}")
        for k, v in result.items():
            if isinstance(v, int) and k != "document_id":
                totals[k] = totals.get(k, 0) + v
        totals[f"status_{result['status']}"] = totals.get(f"status_{result['status']}", 0) + 1
    typer.echo(f"[extract] {len(ids)} document(s) {'queued' if queue else 'done'}: {totals}")


@cli.command()
def index(
    document_id: Annotated[int | None, typer.Option(help="Only this document")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Re-index every document")] = False,
    queue: Annotated[
        bool, typer.Option(help="Enqueue on the worker instead of running here")
    ] = False,
) -> None:
    """Embed chunks and (re)build lesson cards. Default: pending or failed documents."""
    from app.db.session import session_scope
    from app.search.service import index_document, mark_failed

    configure_logging(json_output=False)
    ids = _select_documents(document_id, all_, "index_status")
    done = 0
    for doc_id in ids:
        if queue:
            from app.workers.celery_app import celery_app

            celery_app.send_task("search.index_document", args=[doc_id])
            continue
        try:
            with session_scope() as session:
                index_document(session, doc_id)
            done += 1
        except Exception as exc:
            with session_scope() as session:
                mark_failed(session, doc_id, f"{type(exc).__name__}: {exc}")
            typer.echo(f"[index] document {doc_id}: FAILED {type(exc).__name__}: {exc}")
    typer.echo(f"[index] {len(ids)} document(s) {'queued' if queue else f'processed, {done} ok'}")


@cli.command(name="user-add")
def user_add(
    username: Annotated[str, typer.Option(help="Login name (lowercase)")],
    name: Annotated[str, typer.Option(help="Display name")],
    role: Annotated[list[str], typer.Option(help="Repeat for several roles")],
    password_env: Annotated[
        str, typer.Option(help="Environment variable holding the password (never an argument)")
    ] = "SMRITI_NEW_USER_PASSWORD",  # noqa: S107 (a variable name, not a password)
) -> None:
    """Create a local user for jwt auth mode (the first admin is created this way)."""
    import os

    from pydantic import ValidationError

    from app.api.v1.schemas.auth import UserCreate
    from app.core.auth import DEV_USER
    from app.core.users import create_user
    from app.db.session import session_scope

    configure_logging(json_output=False)
    password = os.environ.get(password_env) or typer.prompt(
        "Password", hide_input=True, confirmation_prompt=True
    )
    try:
        body = UserCreate.model_validate(
            {"username": username, "name": name, "password": password, "roles": role}
        )
    except ValidationError as exc:
        typer.echo(f"[user-add] invalid: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}")
        raise typer.Exit(code=1) from exc
    with session_scope() as session:
        out = create_user(session, body, DEV_USER.model_copy(update={"user_id": "cli"}))
    typer.echo(f"[user-add] created {out.username} ({', '.join(out.roles)})")


if __name__ == "__main__":
    cli()
