# SMRITI Backend — Master Plan & Build Record

**Team:** Slothdevs · **Solution:** SMRITI (working name) · **Problem Statement:** PS 121 — eRTMAC-NWIS (Oil India Limited)
**Parent document:** [`SMRITI_MASTER_PLAN.md`](../SMRITI_MASTER_PLAN.md). That is the product source of truth; **this** document is the source of truth for the backend. When the two disagree, fix both in the same PR.
**Document date:** 2026-09-28 (v1.0) · **updated 2026-09-28 (v1.1):** frontend F0 landed (V-B4 resolved); new `app.cli openapi` command exports the API contract for the frontend (+1 unit test → 31); CI jobs restructured (`backend-checks`, `frontend-checks`, `integration`).
**Backend phase:** **B0 — Skeleton: ✅ COMPLETE (2026-09-28)**. Next: **B1 — Data foundation**.

> ⚠️ **Same honesty rule as the master plan and DHRUVA:** a "✅" must point to a file and a test that passed. Every number in §0 was measured on 2026-09-28 in this repository. Everything from B1 onward is a **plan**.

---

## 0. Where the backend actually stands right now (2026-09-28)

**Built and verified in B0**, with the evidence recorded in Appendix B:

- **Runnable stack:** `docker compose up -d --build --wait` starts 6 services and all reach *healthy* (or *exited 0* for the one-shot `migrate`): PostgreSQL 16.15 (TimescaleDB 2.30.1, PostGIS 3.6.4, pgvector 0.8.6, pg_trgm 1.6), Redis 7.4, SeaweedFS 4.47 (S3 API), `migrate`, `api` (FastAPI), `worker` (Celery).
- **FastAPI app factory** (`backend/app/main.py`) with:
  - `/healthz` (liveness).
  - `/readyz` (readiness). This checks PostgreSQL **and that the required extensions are installed**, Redis, and that the object-storage buckets exist. It returns 200 or 503 with per-component latency and detail.
  - OpenAPI docs at `/docs`.
- **The full API contract from master plan §8 is mounted:** all 21 domain routes from the plan's §8 table, plus `/api/v1/meta` and `/api/v1/me` — 23 operations under `/api/v1/` (counted from `/openapi.json`), plus `/healthz`, `/readyz` and 2 WebSockets. `/api/v1/meta` and `/api/v1/me` are implemented. Every other route returns **HTTP 501 in the standard error envelope and names the phase that will implement it** (e.g. `"phase": "B1"`). The two WebSockets accept, send a `not_implemented` message, and close with code 4501. The frontend team can build against the real contract from day one.
- **Platform code:**
  - Typed settings (`pydantic-settings`, `SMRITI_*` env vars, secrets as `SecretStr`).
  - Structured JSON logging with a per-request `X-Request-ID` (echoed or generated).
  - One error envelope for 404/422/501/503 and application errors.
  - A dev-mode auth dependency that **refuses to run when `SMRITI_ENV=prod`**.
  - A component-status registry served at `/api/v1/meta`.
  - The unit-conversion module (master plan Appendix D) with property tests.
- **Database migrations:** Alembic migration `0001` enables `postgis`, `vector`, `timescaledb` and `pg_trgm`. The integration test checks that each one actually works (a PostGIS point, a pgvector distance, a trigram similarity), not just that it's listed.
- **Operations CLI:** `python -m app.cli bootstrap` waits for dependencies, migrates and creates buckets, and is idempotent (verified by re-running it). `python -m app.cli check --worker` prints readiness plus a round-trip through a real Celery task.
- **Celery worker** on queues `default`, `ingest`, `extract`, with a `system.ping` task. Its Docker health check uses `celery inspect ping`.
- **Tests:** **30 unit tests** (no services needed) and **5 integration tests** against the live stack — all passing. `ruff check`, `ruff format --check`, and `mypy --strict` on `app/` are all clean.
- **Failure behaviour verified:** stopping Redis makes `/readyz` return **503**; restarting it returns it to **200** without restarting the API.
- **CI** (`.github/workflows/ci.yml`) has two jobs:
  1. lint + types + unit tests;
  2. build the Compose stack, run the integration tests, run the CLI check inside the worker, and dump logs on failure.

  ✅ **CI green on GitHub (2026-09-28):** [run #1](https://github.com/SlothDevs-SIH/PS_121/actions/runs/36460112777), both jobs passed on commit `8c25b69`.

**Not in B0 (by design; each is planned and listed in §5):**
- No domain tables yet (from B1).
- No real authentication (B6).
- ~~No frontend "hello"~~ — **resolved 2026-09-28:** frontend F0 is built (see [`FRONTEND_PLAN.md`](FRONTEND_PLAN.md)); V-B4 closed.
- No LLM or OCR services in Compose yet (B1/B2).

**Deviation from the master plan, made on evidence:** object storage is **SeaweedFS**, not MinIO, because `minio/minio` could not be pulled from Docker Hub on 2026-09-28 ("repository does not exist or may require docker login") and `quay.io/minio/minio` was refused from this environment. The code talks plain S3 through `boto3`, so switching to MinIO, Ceph or AWS S3 is a configuration change only. Master plan updated accordingly (see its 2026-09-28 update line).

---

## ⚠️ Verification & Discrepancy Log — Read First

| # | Item | Detail | Resolution / action | Status |
|---|---|---|---|---|
| V-B1 | Object storage ≠ master plan | Master plan said MinIO; MinIO's Docker Hub image wasn't pullable (2026-09-28) | SeaweedFS 4.47 (Apache-2.0) behind the S3 API; master plan corrected | ✅ Resolved |
| V-B2 | GitHub CI not yet observed green | Workflow committed; every step verified locally | First run [#1](https://github.com/SlothDevs-SIH/PS_121/actions/runs/36460112777) passed both jobs on commit `8c25b69` | ✅ Resolved 2026-09-28 |
| V-B3 | Image tags pinned by tag, not digest | `timescale/timescaledb-ha:pg16.15-ts2.30.1`, `redis:7.4-alpine`, `chrislusf/seaweedfs:4.47`, `python:3.11-slim` | Pin digests before any OIL pilot deployment (B6) | ⏳ Open |
| V-B4 | Master-plan P0 frontend "hello" not done | This task covered the backend only | Done 2026-09-28: frontend F0 with a `frontend` Compose service — see [`FRONTEND_PLAN.md`](FRONTEND_PLAN.md) | ✅ Resolved |
| V-B5 | Local image build in this sandbox needed a CA-trusting base image | The development sandbox intercepts TLS; containers don't trust its CA | Solved *without* committing any sandbox CA: `backend/Dockerfile` takes `ARG PYTHON_IMAGE`, and the sandbox build used a local base image with the CA. Normal machines and GitHub runners need nothing special. The same argument lets OIL build from an internal mirror | ✅ Resolved |
| V-B6 | Starlette deprecation warning in tests | `fastapi.testclient` warns "install httpx2 instead" (Starlette 1.7) | Harmless today; revisit when upgrading FastAPI/Starlette | ⏳ Watch |
| V-B7 | Docker Hub rate limits (HTTP 429) during pulls | Seen in the sandbox; may also hit CI | Retry succeeded; if CI hits it, add Docker Hub login or a registry mirror | ⏳ Watch |
| V-B8 | Sync SQLAlchemy chosen for B0 | Async not needed yet; see ADR-B3 | Re-evaluate in B4 when WebSocket fan-out lands | ⏳ Planned review |

---

## 1. Backend Identity & Scope

| Field | Value |
|---|---|
| Language / runtime | Python 3.11 (`requires-python >=3.11,<3.13`) |
| Package / env manager | uv 0.8.17 with a committed `uv.lock` (reproducible installs) |
| Web framework | FastAPI 0.141 on Starlette 1.7, Uvicorn 0.54 |
| Data validation / settings | Pydantic 2.13, pydantic-settings 2.15 |
| Database | PostgreSQL 16.15 + TimescaleDB 2.30.1 + PostGIS 3.6.4 + pgvector 0.8.6 + pg_trgm 1.6 |
| DB access / migrations | SQLAlchemy 2.0.54 (psycopg 3.3), Alembic 1.20 |
| Jobs | Celery 5.6 with the Redis broker (redis-py 6.4) |
| Object storage | S3 API via boto3 1.43; SeaweedFS 4.47 in Compose |
| CLI | Typer 0.27 |
| Quality | ruff 0.16 (lint + format), mypy 2.3 (`strict = true`), pytest 9.1, hypothesis 6.168 |

*(Versions above are what `uv.lock` resolved on 2026-09-28; ranges in `pyproject.toml` allow patch/minor updates.)*

**The backend owns:** master-plan stages S1–S10 and S12 (every stage except the UI, S11), the data model (§6 of the master plan), the evaluation hooks, and the operational tooling.
**The backend does not own:** the UI (S11), model training notebooks (`ml/`, owned by the ML engineer, though the backend serves the trained artefacts), or dataset download scripts (`data/`).

---

## 2. Architecture

### 2.1 Process view (target at B4; ✅ = running in B0)

```
                      ┌────────────────────── clients ──────────────────────┐
                      │ React web app (office/field) · curl/Swagger · tests  │
                      └───────────────┬──────────────────────────┬───────────┘
                               REST / SSE                      WebSocket
                                      ▼                          ▼
 ┌───────────────────────────────── api (FastAPI, uvicorn) ✅ ─────────────────────────────────┐
 │ routes → services → repositories │ auth dep │ error envelope │ request-id │ /healthz /readyz │
 └───────┬──────────────┬───────────────────┬────────────────────────────┬──────────────────────┘
         │ SQL          │ enqueue tasks     │ read/write objects         │ XREAD alerts/scores (B4)
         ▼              ▼                   ▼                            ▼
   PostgreSQL ✅     Redis ✅ ◄──── broker/results ────► worker (Celery) ✅   Redis Streams (B4)
   PostGIS·pgvector  (Celery broker,                     queues: default,          ▲
   TimescaleDB       streams from B4)                    ingest, extract           │ XADD rt samples
         ▲                                                  │ OCR/LLM/extraction   │
         │                                                  ▼                      │
         │                                            S3 (SeaweedFS) ✅     stream service (B4)
         │                                            raw files, page images  replay / WITSML / ETP / WITS0
         │                                                                     rig state → features → scores
         └───────────────────────────── scoring results, alerts ◄──────────────┘
 migrate ✅ (one-shot): wait for deps → alembic upgrade head → ensure buckets
 llm (B2, Ollama/vLLM) · keycloak (B6) · mlflow/prometheus/grafana (B5–B6, Compose profiles)
```

### 2.2 Code layering (enforced by review from B1; see §3.2)

```
app/api/v1/routes/*.py   HTTP only: parse/validate input, call a service, shape the response
app/<module>/service.py  business logic for one master-plan stage (pure where possible)
app/<module>/repo.py     SQL/ORM access for that module; no business rules
app/<module>/tasks.py    Celery tasks: thin wrappers that call services
app/core/                cross-cutting: config, logging, errors, auth, health, units, phases
app/db/                  engine/session, Base, migrations
app/storage/             S3 client
```

**Dependency rule:** `routes → service → repo`. Services never import routes. Modules talk to each other through service functions, never another module's repo. `core` imports nothing from the modules.

### 2.3 Module map (master-plan stage → package → phase)

| Stage | Package | Phase | Main outputs |
|---|---|---|---|
| S1 Ingestion & OCR | `app/ingest/` | B1 | `document`, `page`, `text_span`, `chunk` rows; page images in S3 |
| S2 Extraction | `app/extract/` | B2 | events, casing/cement/mud/bit records, `ddr_operation`, review queue |
| S3 Normalisation | `app/normalise/` | B1 | canonical wells, formations, aliases, TVDSS |
| S4 Trajectory & proximity | `app/geo/` | B1 (surface) / B2 (other modes) | survey stations, `path_geom`, offset queries |
| S5 Search & RAG | `app/search/` | B2 | hybrid search, lessons cards |
| S6 Correlation | `app/correlation/` | B2 | panel JSON, formation stats |
| S7a Offset prior | `app/risk/prior.py` | B3 | risk-by-depth |
| S7b Rig state + ML | `app/risk/rigstate.py`, `app/risk/realtime.py` | B4 | states, probabilities, SHAP |
| S7c Physics | `app/physics/` | B3 | indicators |
| S7d Déjà Vu | `app/risk/dejavu.py` | B4 | similarity matches |
| S8 Ledger | `app/ledger/` | B3 | ranked mitigations |
| S9 Alerts | `app/alerts/` | B4 | alert lifecycle, WebSocket push |
| S10 Copilot | `app/copilot/` | B5 | cited answers (SSE) |
| S12 Stream | `app/stream/` | B4 | replay + protocol adapters |

---

## 3. Conventions (apply from B1 onward; B0 code already follows them)

### 3.1 API conventions

| Topic | Rule |
|---|---|
| Versioning | Everything under `/api/v1`; breaking changes go to `/api/v2`. Health endpoints are unversioned. |
| Errors | Always `{"error": {"code", "message", "details", "request_id"}}` (`app/core/errors.py`). Codes are snake_case and stable (`not_found`, `validation_error`, `not_implemented`, `auth_not_configured`, …). Never return a bare string. |
| Not-yet-built routes | Raise `NotImplementedYetError(feature, phase)` → 501 with `details.phase`. Delete the raise when the phase lands; the contract test (`tests/unit/test_api_contract.py`) keeps the route list honest. |
| Request IDs | `X-Request-ID` accepted (≤ 64 printable chars) or generated; returned on every response and included in every log line and error body. |
| Pagination | Cursor-based: `?limit=50&cursor=<opaque>`; response `{"items": [...], "next_cursor": "..."}`. Max `limit` 500. |
| Filtering | Explicit query parameters (as in master plan §8); no free-form query language. |
| Time | ISO-8601 with offset in APIs; `TIMESTAMPTZ` in UTC in the database; the UI converts to IST. |
| Units | SI canonical in storage (`app/core/units.py` is the only place factors live). APIs return canonical units plus `unit` fields; the UI converts for display. |
| Depths | Every depth field is named with its reference: `md_m`, `tvd_m`, `tvdss_m`. Never a bare `depth`. |
| IDs | Integer surrogate keys internally; documents are also addressable by `sha256`. |
| Evidence | Any response carrying an extracted fact includes `confidence`, `verified`, and evidence references (`document_id`, `page_no`, `span_ids`). This enforces master plan principle P1 ("no citation, no claim"). |
| Idempotency | Uploads are idempotent by SHA-256; `POST` endpoints that create jobs accept an `Idempotency-Key` header (B1). |

### 3.2 Code conventions

- Type hints everywhere; `mypy --strict` must stay clean on `app/`.
- `ruff` rules: `E, F, W, I, B, UP, N, SIM, RUF, ASYNC, S` (bandit-style security checks included).
- Pydantic models for every request/response body; no untyped `dict` responses except the error `details`.
- No `print` in library code; use `logging.getLogger("smriti.<module>")`.
- Secrets only via `SecretStr` settings; never logged (tested in `test_config.py`).
- A new module comes with its tests in the same PR; a new route comes with a contract test.
- Whoever changes a component's status updates **both** `app/core/phases.py` and §5 of this document (the `test_component_registry_is_consistent` test fails if more than the platform is marked built in B0 — relax it as phases land).

### 3.3 Git & review

- `main` is protected; feature branches per role (master plan §17); PRs need 1 review and green CI.
- Commit messages: imperative subject ≤ 72 chars; body explains *why*.
- Migrations: one Alembic revision per PR at most, named `NNNN_<slug>.py` with sequential numbers.

---

## 4. Module Designs (what each phase will build)

Each module uses the same layout: **Responsibilities · Files · Tables · Endpoints · Jobs · Tests · Done when**.

### 4.1 `ingest` — S1 Document ingestion & OCR (B1)

- **Responsibilities:**
  - Accept uploads (multipart, many files), compute the SHA-256, deduplicate, and store the original at `s3://smriti-raw/<sha256>.<ext>`.
  - Create a `document` row (`ingest_status=queued`) and enqueue `ingest.process_document(document_id)`.
  - Classify the document type (rules first, then an LLM zero-shot fallback in B2).
  - Split into pages. Route each page to native-text extraction (Docling) or OCR (PaddleOCR) after preprocessing (OpenCV deskew/denoise).
  - Save page images to `s3://smriti-pages/<document_id>/<page_no>.png`, and save spans with bounding boxes and OCR confidence.
  - Build section-aware chunks (~300–500 tokens).
- **Files:**
  - `ingest/service.py` (orchestration)
  - `ingest/classify.py`
  - `ingest/pdf.py` (Docling wrapper)
  - `ingest/ocr.py` (PaddleOCR wrapper + preprocessing)
  - `ingest/chunking.py`
  - `ingest/repo.py`, `ingest/tasks.py`
- **Tables (migration `0002_documents`):** `document`, `page`, `text_span`, `chunk` (the `embedding` column is added in B2's migration).
- **Endpoints:**
  - `POST /api/v1/documents`
  - `GET /api/v1/documents/{id}`
  - `GET /api/v1/documents/{id}/pages/{n}` (a pre-signed S3 URL for the image, plus spans)
- **Jobs:** `ingest.process_document` on queue `ingest`, with `acks_late` and `max_retries=3` and exponential backoff. Tasks are idempotent: re-running one deletes and rebuilds that document's pages/spans/chunks in a single transaction.
- **Dependencies added:**
  - `docling`, `paddleocr` and `paddlepaddle` (CPU build by default), `opencv-python-headless`, `pypdfium2`.
  - A separate worker image `smriti-worker-ocr` so the API image stays small (see ADR-B6).
- **Tests:**
  - Unit: SHA dedupe; classifier rules; chunk boundaries never split a table.
  - Integration: upload a 3-page PDF fixture (1 native page, 1 scanned, 1 table) → 3 pages, spans with bboxes, images in S3.
- **Done when:** the 50 Volve DDRs and 10 synthetic scanned reports from master plan P1 are ingested; failures are visible with a reason in `ingest_status`/`error`.

### 4.2 `normalise` — S3 Units, datums, formations, aliases, CRS (B1)

- **Responsibilities:**
  - Canonical well master data. Every depth is stored with its type and datum, and TVDSS is computed.
  - The formation dictionary per basin (synonyms, stratigraphic order).
  - Well-name aliasing: `pg_trgm` similarity plus normalisation; merges are proposed, never auto-applied, and a human confirms.
  - CRS handling with `pyproj`: WGS84 for display, the projected CRS per field for distances.
- **Files:** `normalise/datums.py`, `normalise/formations.py`, `normalise/aliases.py`, `normalise/crs.py`, `normalise/repo.py`.
- **Tables (migration `0003_master_data`):** `field`, `well`, `wellbore`, `formation`, `formation_top`, plus an `alias_candidate` review table.
- **Endpoints:** `GET /api/v1/wells`, `GET /api/v1/wells/{id}` (basic in B1; the Well 360 enrichment comes in B2); admin endpoints for formations/aliases (B2).
- **Tests:**
  - Property tests: `tvdss = tvd − rkb_elev` for random inputs.
  - Alias candidates for known pairs (e.g. `"HPJ-12"` ~ `"HAPJAN-12"` style synthetic names).
  - CRS round-trips with an accuracy bound.
- **Done when:** every Volve and synthetic well has a canonical record with a datum (or an `assumed` flag) and a data-quality score.

### 4.3 `geo` — S4 Trajectory engine & proximity (B1: surface mode; B2: the other two modes)

- **Responsibilities:**
  - Minimum-curvature computation (master plan §Stage 4) from survey stations to N/E/TVD/TVDSS/DLS.
  - Build `path_geom` (`LINESTRINGZ`, Z = −TVDSS) in the field CRS.
  - Compute formation entry points.
  - Offset queries:
    - `SURFACE`: `ST_DWithin` on `geography`.
    - `AT_FORMATION`: distance between entry points.
    - `CLOSEST_APPROACH`: `ST_3DDistance` over a TVDSS range.
- **Files:** `geo/mincurv.py` (pure NumPy), `geo/paths.py`, `geo/offsets.py`, `geo/repo.py`.
- **Tables (migration `0004_trajectory`):** `survey_station`; the `path_geom` column plus a GiST index on `wellbore`; `entry_point` on `formation_top`.
- **Endpoints:** `GET /api/v1/wells/{id}/trajectory`, `GET /api/v1/wells/{id}/offsets`.
- **Tests:**
  - Minimum-curvature results against published worked examples (tolerance 0.01 m).
  - A vertical well gives TVD = MD.
  - Radius results equal brute-force haversine on 10,000 random wells (master plan §13.5).
  - Offset query p95 < 500 ms on 10,000 wells (benchmark test, marked `perf`).
- **Done when:** the map's radius search works for Volve and the synthetic field in all three modes.

### 4.4 `extract` — S2 Schema extraction & review queue (B2)

- **Responsibilities:**
  - The deterministic pass: spaCy + regex for depths, units, dates, MW, volumes, casing sizes, formations.
  - The LLM pass: Pydantic schema (master plan Appendix B) with constrained JSON via `instructor`/Outlines against an OpenAI-compatible endpoint (Ollama/vLLM).
  - The DDR time-log parser.
  - Validation and range checks, the span-grounding check, and confidence fusion.
  - The review queue, event de-duplication, and linking events to well/depth/formation/section.
- **Files:** `extract/rules.py`, `extract/llm.py`, `extract/schemas.py`, `extract/ddr_timelog.py`, `extract/validate.py`, `extract/confidence.py`, `extract/dedupe.py`, `extract/service.py`, `extract/tasks.py`.
- **Tables (migration `0005_engineering_records`):** `casing_string`, `cement_job`, `mud_interval`, `ddr_operation`, `event`, `event_evidence`, `mitigation`, `review_item`.
- **Endpoints:** `GET /api/v1/review-queue`, `POST /api/v1/review-queue/{item_id}`, `GET /api/v1/events`.
- **Config added:**
  - `SMRITI_LLM_BASE_URL` and `SMRITI_LLM_MODEL`.
  - `SMRITI_EXTRACT_CONFIDENCE_THRESHOLD` (default 0.75).
  - A Compose `llm` service (Ollama) under profile `llm`.
- **Tests:**
  - Rules on fixtures.
  - Schema validation.
  - Span grounding: a value that isn't in its span gets confidence 0.
  - De-duplication.
  - The LLM is mocked in unit tests; one integration test with a small local model, marked `llm`.
- **Done when:** the master plan §13.1 gold set is annotated and `eval/results/extraction_*.json` records event F1. Quote no number before then.

### 4.5 `search` — S5 Hybrid search, RAG, lessons cards (B2)

- **Responsibilities:**
  - Embeddings (BGE-M3, 1024-d) computed in the worker.
  - Lexical search (`tsvector`) plus dense search (pgvector HNSW), fused with RRF (k = 60), then a `bge-reranker` pass.
  - Structured filters.
  - Lessons cards (LLM summary per verified event).
  - `answer_with_citations()` with a relevance floor and a citation-faithfulness check (reused by the copilot).
- **Tables (migration `0006_search`):** `chunk.embedding VECTOR(1024)` + HNSW index; `chunk.tsv` + GIN index; `event.lesson_card JSONB`.
- **Endpoint:** `GET /api/v1/search`.
- **Tests:** RRF correctness; filters applied before ranking; an unanswerable question returns "no record found"; Recall@5 harness wired to `eval/`.

### 4.6 `correlation` — S6 (B2)

- **Responsibilities:** build panel JSON for `TVDSS`, `FLATTEN_ON_TOP` and `FORMATION_RELATIVE` (piecewise-linear between tops); tracks (formations, casing shoes, MW/ECD, events, cement tops); formation statistics; never interpolate a missing top (badge the well instead).
- **Endpoint:** `GET /api/v1/correlation`.
- **Tests:** piecewise mapping monotonicity; flattening puts the chosen top at 0 for every well; a missing top falls back to TVDSS with a flag.

### 4.7 `risk.prior` — S7a Offset prior risk (B3)

- **Responsibilities:** the weighted Beta-Binomial per event type × interval (master plan §Stage 7a); base-rate prior per basin; n_eff and a 90% credible interval (`scipy.stats.beta`); exclude the target well from its own offsets.
- **Endpoint:** `GET /api/v1/wells/{id}/risk-profile`.
- **Tests:** no offsets returns the prior; identical offsets give a closed-form answer; the CI narrows as n grows; the Brier-score harness hook (§13.2 of the master plan).

### 4.8 `physics` — S7c Physics indicators (B3)

- **Responsibilities:** pure functions for the d-exponent, dc-exponent, Eaton pore pressure (dc form, exponent 1.2), ECD, kick/loss indicators, torque & drag deviation, MSE (Teale), and the cementing checklist risk (formulas in master plan §Stage 7c); all inputs in canonical units, converted with `core.units`.
- **Tests:** textbook worked examples per formula; unit-consistency property tests; the threshold-crossing detector with hysteresis.

### 4.9 `ledger` — S8 Mitigation Effectiveness Ledger (B3)

- **Responsibilities:** outcome derivation (success / partial / fail / unknown with the configurable recurrence window); Beta(1,1) posterior per (event type, action, context); ranking only when n ≥ 3; stratification by severity where recorded.
- **Endpoint:** `GET /api/v1/ledger`.
- **Tests:** recovers the planted success-rate ranking on synthetic data (Spearman ρ ≥ 0.8, master plan §13.7); "insufficient evidence" when n < 3; unknown outcomes are never counted as success or failure.

### 4.10 `stream` — S12 eRTMAC adapters & replay (B4)

- **Responsibilities:**
  - A new Compose service `stream` (same image, command `python -m app.stream.run`).
  - Adapters produce canonical `rt_sample` messages: CSV/Parquet **replay** (the demo path, 1×–60× speed); WITSML 1.4.1.x store polling; an ETP WebSocket client; a WITS0 TCP reader.
  - A channel-mapping table (mnemonic → canonical channel, unit).
  - Data-quality flags (stale, flat-lined, unit jump).
- **Redis Streams design:**
  - `rt:{wellbore_id}` holds raw samples, capped at `MAXLEN ~ 200k`.
  - `scores:{wellbore_id}` holds rig state + risk scores.
  - `alerts` is the single stream for all alert events.
  - The consumer group `persist` writes batches to the TimescaleDB `rt_sample` hypertable (1–5 s batches).
  - The consumer group `score` runs rig state → features → S7b/S7c/S7d.
- **Tables (migration `0007_realtime`):** `rt_sample` (hypertable on `ts`, compression after 7 days), `rig_state`, `channel_mapping`, `replay_session`.
- **Endpoints:** `POST /api/v1/replay`; `WS /ws/wells/{id}/live`, which tails `rt:`/`scores:` at 1 Hz.
- **Tests:** replay timing (simulated clock); mapping + unit conversion; the persist consumer is idempotent (duplicate delivery doesn't duplicate rows); the WITSML adapter against a mock SOAP server fixture.

### 4.11 `risk.rigstate`, `risk.realtime`, `risk.dejavu` — S7b, S7d (B4)

- **Rig state:** a rules state machine (bit depth vs hole depth, hookload, block velocity, RPM, flow, WOB).
- **Real-time classifiers:**
  - LightGBM models are loaded from the MLflow registry, or from a local `models/` directory in demo mode.
  - Features are computed incrementally over 2/5/15-min windows at 10 s resolution.
  - Calibration is isotonic; SHAP runs per evaluation for the top drivers.
  - Scoring every 10–30 s per active well.
- **Déjà Vu:**
  - The signature library is loaded into memory per basin.
  - Stage A is MASS (`stumpy.mass`) on top-20 candidates; stage B is multivariate DTW (`tslearn`, Sakoe-Chiba 10%) plus the level term.
  - τ is calibrated offline; evaluation runs every 30 s; hysteresis is 2 consecutive hits.
- **Table:** `pattern_signature` (migration `0008_dejavu`).
- **Tests:**
  - A known injected precursor in a synthetic stream is matched to its source signature.
  - Normal windows stay below the threshold at the calibrated false-match rate.
  - The scoring loop stays within its latency budget (p95 < 1 s per well per cycle on the demo machine: a **target**).

### 4.12 `alerts` — S9 (B4)

- **Responsibilities:**
  - Alert types `LOOKAHEAD`, `ANOMALY_ML`, `PHYSICS`, `DEJA_VU`, `PLAN_CHECK`, plus a merged `FUSED` alert.
  - De-duplication within 30 m TVD, hysteresis (clear below 0.8·T), 30-min cooldown after acknowledgement, and a per-shift budget (kick alerts are exempt).
  - Lifecycle `NEW → ACK → ACTIONED/DISMISSED → CLOSED`.
  - Feedback.
  - Recommendations pulled from `ledger`.
  - Every alert must carry ≥ 1 evidence reference; the service refuses to emit otherwise.
- **Tables (migration `0009_alerts`):** `alert`, `alert_feedback`.
- **Endpoints:** `GET /api/v1/alerts`, `POST .../ack|dismiss|feedback`, `WS /ws/alerts`.
- **Tests:**
  - A property test that every emitted alert has evidence.
  - Budget enforcement never suppresses `KICK`.
  - Hysteresis/cooldown state transitions.
  - End-to-end: replay a synthetic well → the expected alert sequence arrives over the WebSocket.

### 4.13 `copilot` — S10 (B5)

- **Responsibilities:** an LLM agent with the fixed read-only tools of master plan §Stage 10, each tool calling a service function (never SQL). SSE token streaming. Answers must cite; the prompt-injection defence treats tool outputs as delimited data.
- **Endpoint:** `POST /api/v1/copilot/chat` (SSE).
- **Tests:** the tool-call contract per tool; "no record found" for empty tool results; a document containing an injected instruction is not followed (a red-team fixture).

### 4.14 Reports (B5)

`GET /api/v1/reports/offset-brief/{well_id}` renders HTML with a Jinja2 template and converts it to PDF with WeasyPrint. The brief contains the map snapshot, the offsets table, the risk-by-depth chart (server-side SVG) and citations.

### 4.15 Auth, RBAC, audit (B6)

- `SMRITI_AUTH_MODE=oidc`: validate Keycloak JWTs (JWKS cached, `aud`/`iss` checked) and map realm roles to master plan §16 roles.
- A `require_roles(...)` dependency per route.
- Row-level security by field/asset where required.
- `audit_log` rows written for logins, document views, alert actions, review decisions and copilot queries.
- WebSocket auth via a token in the first message.
- Compose service `keycloak` with a realm export in `infra/keycloak/`.

---

## 5. Designed vs. Built (backend)

Status keys: 📋 Planned · 🔨 In progress · ✅ Built & tested · ⚠️ Built with a known limitation. Keep this table in sync with `app/core/phases.py`.

| # | Component | Phase | Status | Evidence |
|---|---|---|---|---|
| 1 | Repo layout, `pyproject.toml`, `uv.lock` | B0 | ✅ | `backend/pyproject.toml`, `backend/uv.lock` |
| 2 | Settings (`SMRITI_*`, SecretStr) | B0 | ✅ | `app/core/config.py` · `tests/unit/test_config.py` (2) |
| 3 | JSON logging + request IDs | B0 | ✅ | `app/core/logging.py`, `app/core/middleware.py` · `test_request_id_is_echoed_or_generated` |
| 4 | Error envelope (404/422/501/503/app) | B0 | ✅ | `app/core/errors.py` · `test_api_contract.py` |
| 5 | `/healthz`, `/readyz` (DB+extensions, Redis, S3 buckets) | B0 | ✅ | `app/main.py`, `app/core/health.py` · `test_health.py` (5) + integration `test_api_is_ready` |
| 6 | Full §8 API contract mounted (501 + phase) | B0 | ✅ | `app/api/v1/routes/*` · `test_openapi_contains_every_planned_endpoint`, 9 parametrised 501 tests, 2 WebSocket tests |
| 7 | `/api/v1/meta`, `/api/v1/me`, component registry | B0 | ✅ | `routes/system.py`, `core/phases.py` · `test_meta_auth.py` (5) |
| 8 | Dev auth with prod refusal | B0 | ⚠️ dev-only by design | `app/core/auth.py` · `test_auth_refuses_unconfigured_modes` |
| 9 | Unit conversions (Appendix D) | B0 | ✅ | `app/core/units.py` · `test_units.py` (3, incl. hypothesis) |
| 10 | SQLAlchemy engine/session + Base naming convention | B0 | ✅ | `app/db/session.py`, `app/db/base.py` |
| 11 | Alembic + migration `0001` (extensions) | B0 | ✅ | `app/db/migrations/versions/0001_extensions.py` · integration `test_required_extensions_installed_and_migration_at_head` |
| 12 | S3 client + bucket bootstrap | B0 | ✅ | `app/storage/s3.py` · integration `test_object_storage_round_trip` |
| 13 | Celery app + `system.ping` + worker health check | B0 | ✅ | `app/workers/celery_app.py` · integration `test_celery_worker_round_trip`, compose health check |
| 14 | CLI `bootstrap` (idempotent) / `check --worker` / `openapi` (contract export, added with F0) | B0 | ✅ | `app/cli.py` · run twice (Appendix B); `tests/unit/test_cli.py` |
| 15 | Dockerfile (non-root, health check, `PYTHON_IMAGE` arg) | B0 | ✅ | `backend/Dockerfile` |
| 16 | docker-compose (6 services, health-gated startup) | B0 | ✅ | `docker-compose.yml` · `docker compose up -d --wait` all healthy |
| 17 | CI workflow (checks + compose integration) | B0 | ✅ | `.github/workflows/ci.yml` · [run #1](https://github.com/SlothDevs-SIH/PS_121/actions/runs/36460112777) green |
| 18 | S1 ingestion | B1 | 📋 | §4.1 |
| 19 | S3 normalisation + master data tables | B1 | 📋 | §4.2 |
| 20 | S4 min-curvature + surface offsets | B1 | 📋 | §4.3 |
| 21 | S4 at-formation + closest-approach | B2 | 📋 | §4.3 |
| 22 | S2 extraction + review queue + DDR parser | B2 | 📋 | §4.4 |
| 23 | S5 search + lessons cards | B2 | 📋 | §4.5 |
| 24 | S6 correlation | B2 | 📋 | §4.6 |
| 25 | S7a prior, S7c physics, S8 ledger | B3 | 📋 | §4.7–4.9 |
| 26 | S12 stream/replay, S7b, S7d, S9 alerts, WebSockets | B4 | 📋 | §4.10–4.12 |
| 27 | S10 copilot, reports | B5 | 📋 | §4.13–4.14 |
| 28 | OIDC/RBAC/audit, digests pinned, perf & security hardening | B6 | 📋 | §4.15, §12 |

---

## 6. Phase Plan (backend)

Backend phases map onto master plan §18 (P0–P5). Durations assume ~7 weeks to finale-ready; compress proportionally once V4 (deadlines) is known.

| Phase | Master plan | When | Scope | Exit criteria (all must be true) |
|---|---|---|---|---|
| **B0 Skeleton** | P0 | Days 1–3 | Platform, Compose, migrations, CI, API contract | ✅ **Met 2026-09-28**, including a green GitHub CI run — see Appendix B |
| **B1 Data foundation** | P1 | W1–W2 | S1 ingestion; S3 master data & datums; S4 min-curvature + surface offsets; migrations 0002–0004; OCR worker image | 50+ Volve DDRs and 10 synthetic scanned reports ingested with page images and spans; `/wells`, `/wells/{id}/trajectory`, `/wells/{id}/offsets?mode=SURFACE` return real data; min-curvature tests pass; offsets p95 < 500 ms on 10k wells |
| **B2 Knowledge layer** | P2 | W2–W3 | S2 extraction + review queue + DDR parser; S5 search; S6 correlation; S4 other proximity modes; LLM service; migrations 0005–0006 | Gold-set event F1 measured and saved; search Recall@5 measured; correlation JSON for all 3 alignment modes; review queue round trip works |
| **B3 Batch intelligence** | P3 (first half) | W3–W4 | S7a prior, S7c physics, S8 ledger | Risk-profile endpoint live; physics formula tests pass; ledger recovers the planted ranking (ρ ≥ 0.8) |
| **B4 Real-time** | P3 (second half) | W4–W5 | S12 stream + replay; rig state; S7b scoring; S7d Déjà Vu; S9 alerts; WebSockets; migrations 0007–0009 | Replay of a Volve well and a synthetic well produces the expected alerts over the WebSocket; alert latency p95 ≤ 5 s; every alert has evidence (property test) |
| **B5 Copilot & reports** | P4 | W5–W6 | S10 copilot (SSE); Offset Risk Brief PDF; MLflow profile | Copilot answers the 50-question set with citations measured; unanswerable refusal rate measured; PDF renders |
| **B6 Hardening** | P5 | W6–W7 | OIDC/RBAC/audit; image digests pinned; Prometheus metrics + Grafana; load test; security review; backups script | All master plan §9 targets measured and recorded in `eval/results/`; `SMRITI_AUTH_MODE=oidc` works end-to-end; no critical findings open |

### 6.1 B1 task breakdown (next up — ordered)

1. Migration `0002_documents` + ORM models (`document`, `page`, `text_span`, `chunk` without embedding) + repo tests.
2. `POST /documents` (multipart, SHA-256 dedupe, S3 put, row, enqueue) + `GET /documents/{id}`; replace the two 501 stubs; update contract tests.
3. OCR worker image (`backend/Dockerfile.worker-ocr`): Docling + PaddleOCR (CPU), Compose service `worker-ocr` consuming queue `ingest`.
4. `ingest.process_document` task: classify → per-page route → spans + bboxes → page PNGs → chunks; idempotent rebuild.
5. `GET /documents/{id}/pages/{n}`: pre-signed URL + spans.
6. Migration `0003_master_data`; `normalise` datums/formations/aliases; seed loaders for Volve well headers and the synthetic field (from `data/`).
7. `geo/mincurv.py` + tests against worked examples; migration `0004_trajectory`; survey loader; `path_geom` builder.
8. `/wells`, `/wells/{id}`, `/wells/{id}/trajectory`, `/wells/{id}/offsets?mode=SURFACE`; perf test on 10k synthetic wells.
9. Update §5, `phases.py`, and the master plan §5 in the same PRs.

---

## 7. Configuration Reference

All variables are prefixed `SMRITI_` and read by `app/core/config.py`. Defaults suit local development only.

| Variable | Default | Phase | Meaning |
|---|---|---|---|
| `SMRITI_ENV` | `dev` | B0 | `dev` / `test` / `prod`. Dev auth is refused in `prod`. |
| `SMRITI_LOG_LEVEL` | `INFO` | B0 | Root log level |
| `SMRITI_LOG_JSON` | `true` | B0 | JSON log lines (set `false` for human-readable local logs) |
| `SMRITI_GIT_SHA` | `unknown` | B0 | Set at image build (`--build-arg GIT_SHA=`); shown in `/api/v1/meta` |
| `SMRITI_DATABASE_URL` | `postgresql+psycopg://smriti:smriti@localhost:5432/smriti` | B0 | SQLAlchemy URL (secret) |
| `SMRITI_REQUIRED_PG_EXTENSIONS` | `["postgis","vector","timescaledb","pg_trgm"]` | B0 | Checked by `/readyz` |
| `SMRITI_REDIS_URL` | `redis://localhost:6379/0` | B0 | Celery broker/results; streams from B4 |
| `SMRITI_S3_ENDPOINT_URL` | `http://localhost:8333` | B0 | Any S3-compatible endpoint |
| `SMRITI_S3_ACCESS_KEY` / `SMRITI_S3_SECRET_KEY` | `smriti` / `smriti-secret` | B0 | Secrets |
| `SMRITI_S3_REGION` | `us-east-1` | B0 | Required by the S3 client; not meaningful for SeaweedFS |
| `SMRITI_S3_BUCKET_RAW` / `SMRITI_S3_BUCKET_PAGES` | `smriti-raw` / `smriti-pages` | B0 | Created by `bootstrap` |
| `SMRITI_AUTH_MODE` | `dev` | B0 | `dev` or `oidc` (B6) |
| `SMRITI_READINESS_TIMEOUT_S` | `2.0` | B0 | Per-dependency probe timeout |
| `SMRITI_LLM_BASE_URL`, `SMRITI_LLM_MODEL` | — | B2 | OpenAI-compatible endpoint (Ollama/vLLM) |
| `SMRITI_EMBEDDING_MODEL` | — | B2 | e.g. BGE-M3 |
| `SMRITI_EXTRACT_CONFIDENCE_THRESHOLD` | — (0.75 planned) | B2 | Review-queue cut-off |
| `SMRITI_ALERT_BUDGET_PER_SHIFT` | — (6 planned) | B4 | Non-critical alerts per 12 h per rig |
| `SMRITI_OIDC_ISSUER`, `SMRITI_OIDC_AUDIENCE` | — | B6 | Keycloak |

Compose-level variables (`.env.example`): `POSTGRES_USER/PASSWORD/DB/PORT`, `REDIS_PORT`, `S3_ACCESS_KEY/SECRET_KEY/PORT`, `API_PORT`. All published ports bind to `127.0.0.1` only.

---

## 8. Database & Migrations Plan

| Revision | Phase | Contents |
|---|---|---|
| `0001_extensions` ✅ | B0 | `postgis`, `vector`, `timescaledb`, `pg_trgm` |
| `0002_documents` | B1 | `document`, `page`, `text_span`, `chunk` (no embedding yet) |
| `0003_master_data` | B1 | `field`, `well`, `wellbore`, `formation`, `formation_top`, `alias_candidate` |
| `0004_trajectory` | B1 | `survey_station`, `wellbore.path_geom` + GiST, `formation_top.entry_point` |
| `0005_engineering_records` | B2 | `casing_string`, `cement_job`, `mud_interval`, `ddr_operation`, `event`, `event_evidence`, `mitigation`, `review_item` |
| `0006_search` | B2 | `chunk.embedding VECTOR(1024)` + HNSW; `chunk.tsv` + GIN; `event.lesson_card` |
| `0007_realtime` | B4 | `rt_sample` hypertable (+ compression policy), `rig_state`, `channel_mapping`, `replay_session` |
| `0008_dejavu` | B4 | `pattern_signature` |
| `0009_alerts` | B4 | `alert`, `alert_feedback` |
| `0010_auth_audit` | B6 | `app_user`, `audit_log`, row-level security policies |

**Rules:**
- Migrations are forward-only in shared environments; `downgrade()` is written for local use.
- Every migration is tested by the integration job (`bootstrap` runs `upgrade head` on a fresh database every CI run).
- Autogenerate is a starting point, never committed unreviewed.
- Hypertable creation and extension-specific DDL go in `op.execute` with a comment.

---

## 9. Jobs & Queues (Celery)

| Queue | Tasks (phase) | Concurrency guidance | Notes |
|---|---|---|---|
| `default` | `system.ping` (B0), light housekeeping | 2 | ✅ running |
| `ingest` | `ingest.process_document` (B1) | 1–2 per CPU-heavy worker | OCR-heavy; separate `worker-ocr` image |
| `extract` | `extract.process_document`, `search.embed_chunks`, `search.build_lesson_cards` (B2) | 1 per GPU | LLM-bound |
| `batch` | `risk.recompute_prior`, `ledger.recompute` (B3) | 1 | Triggered after review decisions and nightly |

**Task rules:**
- Names are `<module>.<verb>`.
- JSON arguments only (IDs, never objects).
- Tasks are idempotent: a re-run rebuilds the results.
- `acks_late=True` and `worker_prefetch_multiplier=1` (set in B0) so long tasks aren't lost or hoarded.
- Explicit `autoretry_for` on transient errors with exponential backoff, max 3.
- Failures are recorded on the owning row (e.g. `document.ingest_status='failed'`, `error` text) so the UI can show them.

---

## 10. Real-Time Pipeline (B4 design)

```
adapter (replay | WITSML | ETP | WITS0)
   │  canonical rt_sample {wellbore_id, ts, channel, value, unit→canonical, quality}
   ▼
Redis Stream  rt:{wellbore_id}  (MAXLEN ~200k)
   ├── group "persist" → batch INSERT into rt_sample hypertable (1–5 s batches, idempotent on (wellbore_id, ts, channel))
   └── group "score"   → rig state → rolling features (10 s grid) → S7c indicators (every sample batch)
                                                               → S7b classifiers (every 10–30 s)
                                                               → S7d Déjà Vu (every 30 s)
                                                               → S7a look-ahead (on bit-depth change ≥ 1 m)
                         │ XADD scores:{wellbore_id}
                         ▼
                      S9 alert engine (dedupe, hysteresis, budget, evidence, ledger recs)
                         │ INSERT alert; XADD alerts
                         ▼
               api WebSocket fan-out: /ws/wells/{id}/live (1 Hz), /ws/alerts (push)
```

- **Latency budget (target, master plan §9: ≤ 5 s p95 end to end):** adapter → stream ≤ 0.5 s; scoring cycle ≤ 1 s; alert engine ≤ 0.5 s; WebSocket push ≤ 0.5 s; the rest is headroom.
- **Backpressure:** if the scoring group falls behind by more than 60 s of data, it skips to the newest window and logs `scoring_lag`; alerts are never computed on stale data without a banner.
- **Failure isolation:** an adapter crash doesn't stop the API; `/readyz` stays about dependencies; stream health is reported by a separate `GET /api/v1/stream/status` (B4).

---

## 11. Testing Strategy & CI

| Layer | Tooling | Runs where | B0 count |
|---|---|---|---|
| Unit (pure logic, API contract with TestClient, dependency overrides) | pytest, hypothesis | every push (CI job 1) and locally | **30 ✅** at B0 · **31** after the `openapi` CLI test (2026-09-28) |
| Integration (real Postgres/Redis/S3/worker via Compose) | pytest `-m integration`, httpx | CI job 2 and locally with the stack up | **5 ✅** |
| Performance (`perf` marker) | pytest-benchmark / Locust (B6) | on demand, before demo | 0 (from B1) |
| LLM-dependent (`llm` marker) | local small model | on demand | 0 (from B2) |
| Evaluation harness | `eval/run_all.py` → `eval/results/*.json` | on demand; results committed | 0 (from B2) |

**Rules:**
1. Unit tests never touch the network. Checks are injected through FastAPI dependencies (`get_health_checks`) and replaced in tests.
2. Every bug fix gets a regression test first (the DHRUVA lesson: the HMM jitter test caught a real bug).
3. No number is quoted in the pitch unless an `eval/` script produced it.
4. The contract test keeps the route list aligned with master plan §8; when a route is implemented, move it from the "501" parametrisation to its own behaviour tests.

**CI (`.github/workflows/ci.yml`):**
- `backend-checks`: `uv sync --frozen` → ruff check → ruff format check → mypy → pytest.
- `backend-checks` also diffs a fresh `app.cli openapi` export against `frontend/src/lib/api/openapi.json` (contract drift check, added with F0).
- `frontend-checks`: see [`FRONTEND_PLAN.md`](FRONTEND_PLAN.md) §9.
- `integration` (renamed from `backend-integration` 2026-09-28; needs both checks jobs): build images with `GIT_SHA` → `docker compose up -d --wait` → `pytest -m integration` → `app.cli check --worker` inside the worker → Playwright e2e through nginx → logs/report on failure → `down -v` always.

---

## 12. Observability, Security & Operations

**Observability**
- **B0 ✅:** JSON logs with `request_id`; the access log line per request with latency; `/healthz` and `/readyz`; Docker health checks on every service.
- **B6:** Prometheus metrics (`prometheus-fastapi-instrumentator`; custom metrics for ingestion pages/hour, extraction confidence histogram, scoring lag, alert counts by type, WebSocket clients); Grafana dashboards in `infra/grafana/`; OpenTelemetry tracing optional.

**Security**
- **B0 ✅:**
  - The container runs as non-root (uid 10001).
  - Published ports bind to `127.0.0.1`.
  - Secrets come from env (`SecretStr`, never logged; tested); `.env` is git-ignored.
  - S3 authentication is enforced (bad credentials rejected, verified).
  - Dev auth is refused in `prod`.
  - Ruff's `S` (bandit-style) rules are on.
- **B6:**
  - OIDC + RBAC + audit log.
  - Image digests pinned.
  - Dependency audit (`pip-audit`) in CI.
  - Upload limits (size and MIME sniffing; PDFs/images/Office/XML/CSV only).
  - Pre-signed URLs with short expiry.
  - Rate limiting on the copilot.
  - Row-level security for asset scoping.
  - Backups (`pg_dump` + WAL, S3 bucket replication), with a restore drill.

**Operations runbook (B0)**

| Task | Command (repo root) |
|---|---|
| Start everything | `cp .env.example .env && make up` (= `docker compose up -d --build --wait`) |
| Status | `make ps` · `curl localhost:8000/readyz` |
| API docs | `http://localhost:8000/docs` |
| Re-run migrations/buckets | `docker compose run --rm migrate` (idempotent) |
| Full health incl. worker | `make check` |
| Unit / integration tests | `make test` · `make itest` |
| Logs | `make logs` or `docker compose logs api worker` |
| Reset all data (destructive) | `docker compose down -v` |

**Troubleshooting**

| Symptom | Likely cause | Fix |
|---|---|---|
| `/readyz` 503, postgres "missing extensions" | Migrations not applied | `docker compose run --rm migrate` |
| `/readyz` 503, object_storage "missing buckets" | Bootstrap not run against this S3 | Same as above |
| `migrate` exits 1 after "waiting for …" | A dependency never became reachable within 90 s | `docker compose logs <service>`; check `.env` credentials match |
| Image build fails on `pip install uv` with a TLS error | Corporate/sandbox TLS inspection | Build with `--build-arg PYTHON_IMAGE=<base image that trusts your CA>` (V-B5) |
| Pull fails with HTTP 429 | Docker Hub rate limit | Wait and retry, `docker login`, or use a registry mirror (V-B7) |

---

## 13. Backend Architecture Decision Log

| ID | Chose | Over | Why |
|---|---|---|---|
| ADR-B1 | FastAPI + Pydantic v2 | Django REST, Flask, Node | Python ML/geo/OCR ecosystem; typed contracts; OpenAPI for the frontend team; native WebSocket/SSE |
| ADR-B2 | uv + lockfile | pip-tools, Poetry | Fast, reproducible (`--frozen` in CI and Docker); one tool for venv + lock + run |
| ADR-B3 | Sync SQLAlchemy (psycopg 3) in B0–B3 | Async SQLAlchemy | Simpler, well-trodden; FastAPI runs sync routes in a threadpool; heavy work goes to Celery anyway. Revisit in B4 for WebSocket fan-out (V-B8); psycopg 3 supports async, so migrating is contained |
| ADR-B4 | Celery + Redis | RQ, Dramatiq, Arq | Mature retries/acks/queues/routing; Redis is already needed for streams |
| ADR-B5 | S3 API via boto3; SeaweedFS in Compose | MinIO SDK + MinIO server | MinIO image unavailable on Docker Hub (2026-09-28); plain S3 keeps storage swappable (SeaweedFS, MinIO, Ceph RGW, AWS S3) |
| ADR-B6 | Separate OCR/LLM worker image (B1) | One fat image | Docling/PaddleOCR/torch are large; keep the API image small and fast to start |
| ADR-B7 | One PostgreSQL with extensions | Separate vector/time-series/graph stores | Master plan ADR; fewer systems; SQL joins across geo + vector + time-series |
| ADR-B8 | Redis Streams for real-time (B4) | Kafka in the demo | Same consumer-group semantics; fewer moving parts; Kafka is the production answer |
| ADR-B9 | Skeleton routes return 501 with the phase | Leaving routes undefined | The frontend builds against the real contract now; the contract test prevents drift; the status stays honest |
| ADR-B10 | `/readyz` checks extensions and buckets, not just connectivity | Plain TCP pings | "Connected but not migrated" is the most common broken state; the probe says exactly what to run |
| ADR-B11 | Dev auth refused in `prod` | Trusting configuration | Fail closed: a misconfigured pilot can't silently run without auth |

---

## 14. Backend Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| RB1 | OCR/LLM dependencies bloat or break images | High | Medium | Separate worker image (ADR-B6); pin versions; build in CI | Integration eng. |
| RB2 | CPU-only demo machine makes extraction slow | Medium | Medium | Pre-compute extractions into the seeded DB; measure pages/hour and state it | Data eng. |
| RB3 | Sync DB layer limits WebSocket fan-out | Low | Medium | Fan-out reads Redis, not Postgres; async review in B4 (V-B8) | Integration eng. |
| RB4 | Migration drift between branches | Medium | Medium | Sequential numbering, one revision per PR, CI runs `upgrade head` on a fresh DB | Infra |
| RB5 | Docker Hub rate limits / image availability (as with MinIO) | Medium | Medium | Pin tags now, digests in B6; mirror images for the finale machine; save images with `docker save` before the finale | Infra |
| RB6 | Stream scoring falls behind in the live demo | Medium | High | Backpressure skip-to-latest; tuned replay speed; latency metric on screen in the admin view | ML eng. |
| RB7 | Contract drift between backend and frontend | Medium | Medium | OpenAPI is the contract; the frontend generates types from `/openapi.json` | UI + integration eng. |
| RB8 | Secrets committed by mistake | Low | High | `.env` ignored; `SecretStr`; GitHub secret scanning; pre-commit hook (B1) | Everyone |

---

## 15. Backend Q&A Preparation

**"Is the backend real or a mock?"**
The platform layer is real and tested: 30 unit and 5 integration tests, and a health-gated Docker stack with PostGIS, pgvector and TimescaleDB verified working. Domain endpoints exist as a published contract that returns 501 with the phase that implements them. We don't pretend a stub is a feature.

**"Why FastAPI and PostgreSQL?"**
See ADR-B1 and ADR-B7. It's one language for ML, OCR, geospatial and API work, and one database for relational, spatial, vector and time-series data.

**"How do you know the database is actually ready?"**
`/readyz` checks that the required extensions are installed and the buckets exist, not just that ports are open. The integration test exercises each extension.

**"What happens if Redis or storage goes down?"**
`/readyz` flips to 503 with the failing component. We tested this by stopping Redis. The API process stays up and recovers without a restart. From B4, live pages show a "no live data" banner instead of stale values.

**"Can it run inside OIL's network?"**
Yes. It's all containers, with no mandatory internet at runtime. The base image is a build argument, so it can come from an internal mirror, and any S3-compatible store works.

**"Why SeaweedFS instead of MinIO?"**
MinIO's Docker Hub image wasn't available when we built. Our code speaks plain S3, so MinIO or Ceph can replace SeaweedFS by changing configuration.

---

## 16. Immediate Next Actions (backend)

1. ~~Watch the first GitHub CI run~~ — done, green (V-B2).
2. **B1 kickoff:** tasks 1–2 of §6.1 (documents migration + upload endpoint) — Integration + Data eng.
3. **OCR worker image spike:** build `Dockerfile.worker-ocr` with Docling + PaddleOCR (CPU); record the image size and pages/minute on a 10-page scanned fixture in this document — Data eng.
4. **`geo/mincurv.py`** with textbook test cases — Domain eng.
5. **Frontend "hello" + OpenAPI type generation** (closes V-B4) — UI eng.
6. **Save the pinned images** (`docker save`) to a shared drive for the finale machine (RB5) — Infra.

---

## Appendix A — Backend File Tree (as built in B0)

```
.
├── .env.example                     Compose + app variables (dev defaults)
├── .github/workflows/ci.yml         backend-checks + backend-integration
├── .gitignore
├── Makefile                         up/down/ps/logs/lint/fmt/types/test/itest/check
├── docker-compose.yml               postgres, redis, s3, migrate, api, worker
├── infra/seaweedfs/entrypoint.sh    writes S3 identities from env, starts SeaweedFS
├── docs/BACKEND_PLAN.md             this document
└── backend/
    ├── Dockerfile                   python:3.11-slim (overridable), uv, non-root, health check
    ├── .dockerignore
    ├── README.md
    ├── pyproject.toml · uv.lock
    ├── alembic.ini
    ├── app/
    │   ├── main.py                  app factory, /healthz, /readyz
    │   ├── cli.py                   bootstrap, check
    │   ├── api/v1/router.py
    │   ├── api/v1/routes/           system.py (implemented), knowledge.py, wells.py,
    │   │                            realtime.py, ws.py (501 skeletons with phases)
    │   ├── core/                    config, logging, middleware, errors, auth, health,
    │   │                            units, phases
    │   ├── db/                      session.py, base.py, migrations/{env.py, script.py.mako,
    │   │                            versions/0001_extensions.py}
    │   ├── storage/s3.py
    │   ├── workers/celery_app.py
    │   └── ingest/ extract/ normalise/ geo/ search/ correlation/ risk/ physics/
    │       ledger/ alerts/ copilot/ stream/      (stage packages, empty until their phase)
    └── tests/
        ├── conftest.py
        ├── unit/                    test_api_contract, test_health, test_meta_auth,
        │                            test_units, test_config
        └── integration/test_stack.py
```

## Appendix B — B0 Verification Record (2026-09-28)

Run in this repository on 2026-09-28. Numbers are copied from the actual output.

| Check | Command | Result |
|---|---|---|
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `53 files already formatted` |
| Types | `uv run mypy app` (strict) | `Success: no issues found in 40 source files` |
| Unit tests | `uv run pytest` | `30 passed, 5 deselected` (1 Starlette deprecation warning, V-B6) |
| Stack up | `docker compose up -d --wait` | postgres, redis, s3, api, worker **healthy**; migrate **exited 0** |
| Bootstrap log | `docker compose logs migrate` | deps reachable → `Running upgrade -> 0001` → `migrations: at head` → `buckets: created ['smriti-raw', 'smriti-pages']` |
| Readiness | `curl localhost:8000/readyz` | `{"status":"ready"}`: postgres "extensions ok: postgis, vector, timescaledb, pg_trgm", redis "ping ok", object_storage "buckets ok" |
| Skeleton route via real server | `curl localhost:8000/api/v1/wells` | 501, `{"error":{"code":"not_implemented",…,"details":{"feature":"Well list (S3)","phase":"B1"},"request_id":"…"}}` |
| Meta | `curl localhost:8000/api/v1/meta` | `backend_phase: B0`, `git_sha` set from the build, 16 components |
| Integration tests | `uv run pytest -m integration` | `5 passed` |
| Worker round trip | `docker compose exec worker python -m app.cli check --worker` | `worker: {'pong': '2026-09-28T17:38:05…'}`, exit 0 |
| Failure handling | `docker compose stop redis` → `/readyz`; then `start redis` | **503**, then **200** without restarting the API |
| Idempotent bootstrap | `docker compose run --rm migrate` (second run) | `migrations: at head`, `buckets: created none` |
| Image versions | `SELECT … FROM pg_available_extensions` | PostgreSQL 16.15; timescaledb 2.30.1; postgis 3.6.4; vector 0.8.6; pg_trgm 1.6 |
| S3 auth enforced | boto3 with wrong credentials | request rejected (`ClientError`) |
| GitHub CI | push of commit `8c25b69` | [run #1](https://github.com/SlothDevs-SIH/PS_121/actions/runs/36460112777): `backend-checks` ✅, `backend-integration` ✅ |

## Appendix C — Document Maintenance Rules

Same as master plan Appendix F:
- Dated update lines go in the header.
- Correct wrong statements in place with a dated note.
- Update §5 and `app/core/phases.py` in the same PR as the code.
- Every "✅" cites a file and a test.
