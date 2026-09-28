# SMRITI backend

FastAPI + Celery backend for SMRITI (eRTMAC-NWIS, SIH PS 121). Current phase: **B1 done** (ingestion, master data, trajectories, offsets).
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
uv run python -m app.cli seed --inline    # synthetic field + reports (needs `tesseract` on PATH for scans)
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
uv run python scripts/perf_offsets.py   # offset-query latency on 10,000 wells
```

## Layout

```
app/
  main.py            app factory, /healthz, /readyz
  cli.py             bootstrap / check / openapi / seed
  core/              config, logging, middleware, errors, auth, health, units, phases
  api/v1/            router, schemas, routes (unbuilt routes return 501 naming their phase)
  db/                engine/session, declarative base, Alembic migrations
  storage/           S3-compatible client
  workers/           Celery app
  synthetic/         deterministic synthetic field + report renderer (ground truth for later phases)
  ingest/            upload, PDF text layer / OCR, spans + bboxes, chunks, classification, Celery task
  normalise/         master-data import, TVDSS, well aliases, well listing and data quality
  geo/               minimum curvature, 3D paths, offset queries
  extract/ search/ correlation/ risk/ physics/ ledger/ alerts/ copilot/ stream/
                     later stages, empty until their phase
tests/unit/          fast tests (CI)
tests/integration/   tests against the running stack (CI "integration" job)
```
