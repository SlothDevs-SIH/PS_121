# SMRITI backend

FastAPI + Celery backend for SMRITI (eRTMAC-NWIS, SIH PS 121). Current phase: **B0 (skeleton)**.
Design and roadmap: [`docs/BACKEND_PLAN.md`](../docs/BACKEND_PLAN.md). Product plan: [`SMRITI_MASTER_PLAN.md`](../SMRITI_MASTER_PLAN.md).

## Run the full stack (Docker)

From the repository root:

```bash
cp .env.example .env          # dev defaults; change secrets for anything shared
docker compose up -d --build --wait
curl localhost:8000/readyz    # {"status":"ready", ...}
open http://localhost:8000/docs
```

Services: `postgres` (PostgreSQL 16 + PostGIS + pgvector + TimescaleDB), `redis`, `s3` (SeaweedFS, S3 API),
`migrate` (one-shot: migrations + buckets), `api` (FastAPI :8000), `worker` (Celery).

## Develop locally (without Docker for the API)

```bash
cd backend
uv sync                                   # Python 3.11, installs app + dev tools
docker compose up -d postgres redis s3    # dependencies only (from repo root)
uv run python -m app.cli bootstrap        # migrations + buckets
uv run uvicorn app.main:app --reload
uv run celery -A app.workers.celery_app worker -l INFO
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest                    # unit tests, no services needed
uv run pytest -m integration     # needs the compose stack running
uv run python -m app.cli check --worker
```

## Layout

```
app/
  main.py            app factory, /healthz, /readyz
  cli.py             bootstrap / check
  core/              config, logging, middleware, errors, auth, health, units, phases
  api/v1/            router + routes (system implemented; everything else 501 with its phase)
  db/                engine/session, declarative base, Alembic migrations
  storage/           S3-compatible client
  workers/           Celery app
  ingest/ extract/ normalise/ geo/ search/ correlation/ risk/ physics/ ledger/ alerts/ copilot/ stream/
                     one package per master-plan stage, empty until its phase
tests/unit/          fast tests (CI)
tests/integration/   tests against the running stack (CI "integration" job)
```
