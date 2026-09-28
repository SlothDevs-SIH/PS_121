# NWIS Backend — Build Specification

This document is a complete blueprint for the NWIS backend. It is written to be handed to an AI coding agent (or a human engineer) with the instruction: **"Build the full backend from this spec."** It covers project structure, database schema, every API endpoint, background jobs, real-time streaming, the ML/RAG services, auth, and deployment — for the stack already chosen:

**FastAPI · Celery + Redis · Redis Streams/Kafka · PostgreSQL + PostGIS + pgvector + TimescaleDB · MinIO · Keycloak/JWT · Docling · PaddleOCR · LlamaIndex · BGE-M3 · XGBoost/LightGBM · SHAP · PyOD · stumpy/tslearn · wellpathpy**

---

## 0. High-level architecture

```
                         ┌──────────────────────────┐
                         │        React frontend      │
                         └─────────────┬────────────┘
                          REST + WebSocket (JSON)
                                       │
                         ┌─────────────▼────────────┐
                         │       FastAPI app           │
                         │  (routers, services, ws)    │
                         └───┬──────────┬──────────┬──┘
                             │          │          │
                 ┌───────────▼──┐ ┌─────▼─────┐ ┌───▼─────────────┐
                 │ Celery workers │ │  ML/RAG    │ │ Stream consumer  │
                 │ (OCR/extract)  │ │  services  │ │ (Redis/Kafka)    │
                 └───────┬────────┘ └─────┬──────┘ └───┬─────────────┘
                         │                │            │
                 ┌───────▼────────────────▼────────────▼───────┐
                 │   PostgreSQL (PostGIS + pgvector + Timescale) │
                 │                    + MinIO (files)             │
                 └────────────────────────────────────────────────┘
```

Three independent "planes" the backend must support:
1. **Batch plane** — ingest historical PDFs → OCR → extract → embed → store (Celery).
2. **Streaming plane** — ingest live eRTMAC drilling parameters → detect risk → alert (Redis/Kafka consumer + WebSocket push).
3. **Query plane** — serve REST requests from the dashboard: map data, well detail, search, correlation, alerts (FastAPI routers).

---

## 1. Project structure

```
nwis-backend/
├── app/
│   ├── main.py                     # FastAPI app factory, router registration, startup/shutdown hooks
│   ├── config.py                   # Pydantic Settings — all env vars, single source of truth
│   ├── dependencies.py             # shared FastAPI Depends() (db session, current_user, pagination)
│   │
│   ├── db/
│   │   ├── base.py                 # SQLAlchemy declarative Base, engine, session factory
│   │   ├── session.py              # async session dependency
│   │   └── init_db.py              # creates extensions (postgis, vector, timescaledb), runs seed
│   │
│   ├── models/                     # SQLAlchemy ORM models — one file per domain (see §3)
│   │   ├── well.py
│   │   ├── trajectory.py
│   │   ├── document.py
│   │   ├── event.py
│   │   ├── chunk.py                # embeddings table (pgvector)
│   │   ├── parameter.py            # timescale hypertable
│   │   ├── alert.py
│   │   ├── formation.py
│   │   ├── casing.py
│   │   ├── user.py
│   │   └── ml_model.py             # model registry metadata
│   │
│   ├── schemas/                    # Pydantic request/response models, mirrors models/ 1:1
│   │   └── ... (well.py, document.py, alert.py, etc.)
│   │
│   ├── routers/                    # one router per resource, thin — delegates to services/
│   │   ├── wells.py
│   │   ├── trajectories.py
│   │   ├── documents.py
│   │   ├── search.py               # RAG/semantic search endpoints
│   │   ├── events.py
│   │   ├── alerts.py
│   │   ├── predictions.py          # ML risk scoring endpoints
│   │   ├── correlation.py          # cross-well depth/formation correlation
│   │   ├── parameters.py           # time-series query endpoints
│   │   ├── auth.py
│   │   └── ws.py                   # WebSocket endpoints
│   │
│   ├── services/                   # business logic, framework-agnostic
│   │   ├── ocr_service.py          # Docling + PaddleOCR + TrOCR orchestration
│   │   ├── extraction_service.py   # LLM + Pydantic schema extraction, spaCy cross-check
│   │   ├── embedding_service.py    # BGE-M3 embedding generation
│   │   ├── retrieval_service.py    # LlamaIndex index build/query + bge-reranker
│   │   ├── geo_service.py          # PostGIS radius/nearest-well queries, wellpathpy TVD calc
│   │   ├── ml/
│   │   │   ├── risk_classifier.py  # XGBoost/LightGBM train + predict + SHAP explain
│   │   │   ├── anomaly_service.py  # PyOD isolation forest / ECOD
│   │   │   ├── pattern_service.py  # stumpy matrix profile + tslearn DTW matching
│   │   │   └── feature_service.py  # tsfresh feature extraction from parameter windows
│   │   ├── alert_engine.py         # combines risk_classifier + anomaly + pattern -> fires alerts
│   │   └── storage_service.py      # MinIO upload/download, presigned URLs
│   │
│   ├── workers/                    # Celery app + tasks
│   │   ├── celery_app.py
│   │   ├── tasks_ingest.py         # process_document, ocr_page, extract_events
│   │   ├── tasks_embed.py          # embed_chunks, rebuild_index
│   │   └── tasks_ml.py             # retrain_risk_model, batch_score_offset_wells
│   │
│   ├── streaming/
│   │   ├── consumer.py             # Redis Streams / Kafka consumer loop
│   │   ├── ws_manager.py           # WebSocket connection registry, broadcast by well_id
│   │   └── producer_sim.py         # dev-only: replays Volve WITSML data as a live stream
│   │
│   ├── core/
│   │   ├── security.py             # JWT issue/verify, password hashing, Keycloak token validation
│   │   ├── rbac.py                 # role definitions + permission checks
│   │   └── logging.py
│   │
│   └── utils/
│       ├── units.py                # ppg/bbl/m/ft normalization
│       ├── las_parser.py           # lasio wrapper
│       └── witsml_parser.py        # welly/komle wrapper
│
├── alembic/                        # DB migrations
│   └── versions/
├── tests/
│   ├── test_routers/
│   ├── test_services/
│   └── conftest.py                 # fixtures: test db, test client, sample well/document
├── scripts/
│   ├── seed_demo_data.py           # loads Volve + synthetic Assam data
│   ├── train_initial_models.py
│   └── replay_stream.py
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── Dockerfile.worker
├── requirements.txt / pyproject.toml
├── alembic.ini
└── .env.example
```

**Rule for the build agent:** routers stay thin (parse request → call service → return response). All logic lives in `services/`. This keeps ML/OCR code testable without spinning up FastAPI.

---

## 2. Configuration (`app/config.py`)

Single `Settings(BaseSettings)` class reading from `.env`. Required variables:

```
# App
APP_ENV=development|staging|production
SECRET_KEY=
CORS_ORIGINS=http://localhost:5173

# Postgres
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/nwis
POSTGIS_ENABLED=true

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Streaming
STREAM_BACKEND=redis|kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC_DRILLING=ertmac.drilling.parameters

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_BUCKET_DOCUMENTS=nwis-documents
MINIO_SECURE=false

# Auth
AUTH_MODE=jwt|keycloak
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
KEYCLOAK_URL=
KEYCLOAK_REALM=
KEYCLOAK_CLIENT_ID=

# LLM / AI
LLM_BACKEND=ollama|vllm|anthropic
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL_NAME=qwen2.5:14b
EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-base

# ML
MODEL_REGISTRY_PATH=/models
MLFLOW_TRACKING_URI=http://mlflow:5000
RISK_ALERT_THRESHOLD=0.65
ANOMALY_CONTAMINATION=0.05
```

---

## 3. Database schema (PostgreSQL + PostGIS + pgvector + TimescaleDB)

Enable extensions in `init_db.py` / first Alembic migration:
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### 3.1 `wells`
```sql
CREATE TABLE wells (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_name TEXT NOT NULL,
    well_uwi TEXT UNIQUE,                 -- unique well identifier
    operator TEXT,
    field_name TEXT,
    basin TEXT,
    status TEXT CHECK (status IN ('active','completed','abandoned','planned')),
    spud_date DATE,
    total_depth_md NUMERIC,               -- measured depth
    total_depth_tvd NUMERIC,              -- true vertical depth
    surface_location GEOGRAPHY(POINT, 4326) NOT NULL,
    is_deviated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_wells_geo ON wells USING GIST (surface_location);
CREATE INDEX idx_wells_field ON wells (field_name);
```

### 3.2 `well_trajectories` (survey stations → 3D path via wellpathpy)
```sql
CREATE TABLE well_trajectories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_id UUID REFERENCES wells(id) ON DELETE CASCADE,
    md NUMERIC NOT NULL,                  -- measured depth at this station
    inclination NUMERIC,
    azimuth NUMERIC,
    tvd NUMERIC,                          -- computed via minimum curvature
    northing NUMERIC,
    easting NUMERIC,
    position GEOGRAPHY(POINTZ, 4326),     -- computed 3D point
    sequence_no INT NOT NULL
);
CREATE INDEX idx_traj_well ON well_trajectories (well_id, sequence_no);
CREATE INDEX idx_traj_geo ON well_trajectories USING GIST (position);
```

### 3.3 `formations`
```sql
CREATE TABLE formations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_id UUID REFERENCES wells(id) ON DELETE CASCADE,
    formation_name TEXT NOT NULL,
    top_md NUMERIC,
    top_tvd NUMERIC,
    base_md NUMERIC,
    base_tvd NUMERIC,
    lithology TEXT,
    source_document_id UUID REFERENCES documents(id)
);
CREATE INDEX idx_formation_name ON formations (formation_name);
```

### 3.4 `documents` (raw files + OCR/extraction status)
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_id UUID REFERENCES wells(id) ON DELETE SET NULL,
    doc_type TEXT CHECK (doc_type IN ('WCR','DDR','geological_report','other')),
    original_filename TEXT NOT NULL,
    minio_object_key TEXT NOT NULL,       -- pointer to MinIO for source-page citation
    page_count INT,
    ocr_status TEXT DEFAULT 'pending' CHECK (ocr_status IN ('pending','processing','done','failed')),
    extraction_status TEXT DEFAULT 'pending' CHECK (extraction_status IN ('pending','processing','done','failed','needs_review')),
    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT now()
);
```

### 3.5 `document_pages` (per-page OCR text, for citation)
```sql
CREATE TABLE document_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    page_number INT NOT NULL,
    raw_text TEXT,
    ocr_confidence NUMERIC,
    UNIQUE (document_id, page_number)
);
```

### 3.6 `events` (extracted drilling events — the core "institutional memory" table)
```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_id UUID REFERENCES wells(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id),
    source_page INT,
    event_type TEXT CHECK (event_type IN (
        'mud_loss','kick','stuck_pipe','fishing','npt',
        'torque_spike','overpressure','cementing_issue','other'
    )),
    depth_md NUMERIC,
    depth_tvd NUMERIC,
    formation_name TEXT,
    severity TEXT CHECK (severity IN ('minor','moderate','severe')),
    volume_bbl NUMERIC,                   -- for losses/kicks
    description TEXT NOT NULL,
    root_cause TEXT,
    mitigation TEXT,
    extracted_by TEXT,                    -- model name/version that extracted this
    extraction_confidence NUMERIC,
    verified_by UUID REFERENCES users(id),  -- human-in-the-loop sign-off
    event_date DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_events_well_depth ON events (well_id, depth_md);
CREATE INDEX idx_events_type ON events (event_type);
CREATE INDEX idx_events_formation ON events (formation_name);
```

### 3.7 `document_chunks` (RAG — pgvector)
```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    well_id UUID REFERENCES wells(id),
    page_number INT,
    chunk_text TEXT NOT NULL,
    chunk_metadata JSONB,                 -- {formation, depth_range, doc_type, ...} used as LlamaIndex metadata filters
    embedding VECTOR(1024)                -- BGE-M3 dimension
);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_well ON document_chunks (well_id);
```

### 3.8 `drilling_parameters` (TimescaleDB hypertable — live + historical time-series)
```sql
CREATE TABLE drilling_parameters (
    time TIMESTAMPTZ NOT NULL,
    well_id UUID NOT NULL REFERENCES wells(id),
    depth_md NUMERIC,
    rop NUMERIC,                          -- rate of penetration
    wob NUMERIC,                          -- weight on bit
    torque NUMERIC,
    spp NUMERIC,                          -- standpipe pressure
    flow_in NUMERIC,
    flow_out NUMERIC,
    mud_weight_in NUMERIC,
    mud_weight_out NUMERIC,
    hookload NUMERIC,
    rpm NUMERIC,
    gas_units NUMERIC
);
SELECT create_hypertable('drilling_parameters', 'time');
CREATE INDEX idx_params_well_time ON drilling_parameters (well_id, time DESC);
-- Optional: continuous aggregate for 1-min rollups used by the dashboard charts
CREATE MATERIALIZED VIEW drilling_parameters_1min
WITH (timescaledb.continuous) AS
SELECT well_id, time_bucket('1 minute', time) AS bucket,
       avg(rop) AS avg_rop, avg(torque) AS avg_torque, avg(spp) AS avg_spp,
       max(gas_units) AS max_gas
FROM drilling_parameters
GROUP BY well_id, bucket;
```

### 3.9 `alerts`
```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_id UUID REFERENCES wells(id) ON DELETE CASCADE,
    alert_type TEXT,                      -- matches events.event_type
    risk_score NUMERIC,                   -- from XGBoost classifier
    triggered_at TIMESTAMPTZ DEFAULT now(),
    current_depth_md NUMERIC,
    matched_offset_well_id UUID REFERENCES wells(id),
    matched_event_id UUID REFERENCES events(id),
    pattern_similarity NUMERIC,           -- from DTW/matrix profile
    anomaly_score NUMERIC,                -- from PyOD
    shap_explanation JSONB,               -- top contributing features
    recommendation TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active','acknowledged','dismissed','resolved')),
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ
);
CREATE INDEX idx_alerts_well_status ON alerts (well_id, status);
```

### 3.10 `casing_programs` / `cementing_records`
```sql
CREATE TABLE casing_programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    well_id UUID REFERENCES wells(id) ON DELETE CASCADE,
    casing_type TEXT,                     -- conductor, surface, intermediate, production
    od_inches NUMERIC,
    set_depth_md NUMERIC,
    cement_type TEXT,
    cement_volume_bbl NUMERIC,
    cement_top_md NUMERIC,
    issues_noted TEXT,
    source_document_id UUID REFERENCES documents(id)
);
```

### 3.11 `users` / RBAC
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT,                 -- null if using Keycloak SSO
    full_name TEXT,
    role TEXT CHECK (role IN ('field_engineer','office_engineer','admin','viewer')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 3.12 `ml_models` (model registry, links to MLflow)
```sql
CREATE TABLE ml_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name TEXT,                      -- e.g. 'risk_classifier_stuck_pipe'
    model_type TEXT,                      -- xgboost, isolation_forest, etc.
    version TEXT,
    mlflow_run_id TEXT,
    file_path TEXT,
    trained_at TIMESTAMPTZ,
    metrics JSONB,                        -- {precision, recall, f1, auc}
    is_active BOOLEAN DEFAULT FALSE
);
```

---

## 4. API surface (REST)

All routes under `/api/v1`. All list endpoints paginated (`?page=&page_size=`), all mutating endpoints require auth, RBAC enforced via `Depends(require_role(...))`.

### 4.1 Auth — `routers/auth.py`
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | email+password → JWT (or redirect info if `AUTH_MODE=keycloak`) |
| POST | `/auth/refresh` | refresh token → new access token |
| GET | `/auth/me` | current user profile + role |

### 4.2 Wells — `routers/wells.py`
| Method | Path | Purpose |
|---|---|---|
| GET | `/wells` | list/filter wells (field, basin, status) |
| GET | `/wells/{well_id}` | well detail |
| POST | `/wells` | create well (admin) |
| PATCH | `/wells/{well_id}` | update well metadata |
| GET | `/wells/{well_id}/nearby?radius_km=10` | **PostGIS radius query** → GeoJSON FeatureCollection of nearby wells, sorted by distance |
| GET | `/wells/{well_id}/formations` | formation tops for this well |
| GET | `/wells/nearby-map?bbox=` | wells within a map bounding box, for initial map load |

### 4.3 Trajectories — `routers/trajectories.py`
| Method | Path | Purpose |
|---|---|---|
| GET | `/wells/{well_id}/trajectory` | full survey-station list + computed TVD/3D path |
| POST | `/wells/{well_id}/trajectory` | bulk upload survey stations → triggers wellpathpy TVD calc |
| GET | `/wells/{well_id}/trajectory/at-depth?md=` | interpolated position at a given depth |

### 4.4 Documents — `routers/documents.py`
| Method | Path | Purpose |
|---|---|---|
| POST | `/documents/upload` | multipart upload → store in MinIO → enqueue `process_document` Celery task |
| GET | `/documents` | list, filterable by well/doc_type/status |
| GET | `/documents/{id}` | metadata + processing status |
| GET | `/documents/{id}/pages/{page_number}` | OCR'd text + link to page image (for citation display) |
| GET | `/documents/{id}/download` | presigned MinIO URL |
| POST | `/documents/{id}/reprocess` | re-run OCR/extraction (admin) |

### 4.5 Events — `routers/events.py`
| Method | Path | Purpose |
|---|---|---|
| GET | `/events` | filter by well, event_type, formation, depth range, date range |
| GET | `/events/{id}` | event detail incl. source document/page link |
| POST | `/events` | manual entry (bypass extraction) |
| PATCH | `/events/{id}/verify` | human marks an extracted event as verified/corrected |
| GET | `/wells/{well_id}/events/timeline` | chronological event list for one well |

### 4.6 Search / RAG — `routers/search.py`
| Method | Path | Purpose |
|---|---|---|
| POST | `/search` | body: `{query, well_id?, formation?, depth_range?, event_type?, top_k}` → semantic search over `document_chunks` (embed query → pgvector similarity → bge-reranker → return ranked chunks with source citations) |
| POST | `/search/ask` | RAG Q&A: retrieval + LLM-generated natural-language answer with citations (LlamaIndex query engine) |

### 4.7 Correlation — `routers/correlation.py`
| Method | Path | Purpose |
|---|---|---|
| GET | `/correlation?well_ids=a,b,c&formation=` | depth-aligned parameter/event data across multiple wells, for the D3 correlation view |
| GET | `/correlation/formation-risk?formation=` | aggregated event counts/types across all wells that penetrated a given formation |

### 4.8 Predictions / ML — `routers/predictions.py`
| Method | Path | Purpose |
|---|---|---|
| POST | `/predictions/risk` | body: current well params + depth → risk scores per event_type + SHAP top-features (on-demand scoring) |
| GET | `/predictions/pattern-match?well_id=&window_minutes=` | DTW/matrix-profile match against offset-well pre-event patterns |
| GET | `/predictions/anomaly?well_id=` | current anomaly score from PyOD |
| POST | `/predictions/retrain` | admin-triggered retrain (enqueues Celery task) |

### 4.9 Alerts — `routers/alerts.py`
| Method | Path | Purpose |
|---|---|---|
| GET | `/alerts?well_id=&status=` | list alerts |
| GET | `/alerts/{id}` | alert detail with full explanation payload |
| PATCH | `/alerts/{id}/acknowledge` | engineer acknowledges |
| PATCH | `/alerts/{id}/dismiss` | dismiss with reason |

### 4.10 Live parameters — `routers/parameters.py`
| Method | Path | Purpose |
|---|---|---|
| GET | `/wells/{well_id}/parameters?from=&to=&resolution=` | historical/backfill query (uses `drilling_parameters_1min` for wide ranges) |
| GET | `/wells/{well_id}/parameters/latest` | last known reading (REST fallback if WS not connected) |

### 4.11 WebSocket — `routers/ws.py`
| Path | Purpose |
|---|---|
| `WS /ws/wells/{well_id}` | client subscribes to a well; server pushes `{type: "parameter_update"}` and `{type: "alert"}` messages as they occur |
| `WS /ws/dashboard` | global feed for the office dashboard — all active-well alerts across the field |

**WebSocket message contract (server → client):**
```json
{ "type": "parameter_update", "well_id": "...", "time": "...", "data": { "rop": 12.4, "torque": 5400, "spp": 2100, "depth_md": 2345.2 } }
{ "type": "alert", "well_id": "...", "alert": { ...alerts row... } }
```

---

## 5. Background jobs (Celery — `app/workers/`)

### `tasks_ingest.py`
- **`process_document(document_id)`** — orchestrator task, chains the below:
  1. `ocr_document(document_id)` → Docling for layout, PaddleOCR/TrOCR per page as needed → writes `document_pages`
  2. `extract_events(document_id)` → runs LLM+Pydantic extraction per page/section, spaCy cross-check, writes `events` rows with `extraction_confidence`; rows below a confidence threshold get `extraction_status='needs_review'`
  3. `chunk_and_embed(document_id)` → splits page text into chunks (LlamaIndex node parser), calls `embedding_service`, writes `document_chunks`
  4. On failure at any step: set `ocr_status`/`extraction_status = 'failed'`, log error, notify via a `failed_jobs` table or Sentry-style logging

### `tasks_embed.py`
- **`rebuild_index()`** — full reindex of `document_chunks` into the LlamaIndex vector store (maintenance task)

### `tasks_ml.py`
- **`retrain_risk_model(event_type)`** — pulls labeled events + parameter windows, retrains XGBoost, logs to MLflow, writes `ml_models` row, flips `is_active`
- **`batch_score_offset_wells(well_id)`** — precomputes risk/pattern scores for all formations a new well is planned to penetrate, used to pre-populate the dashboard before spud

---

## 6. Real-time streaming pipeline

### `streaming/consumer.py`
- Long-running process (separate container) that:
  1. Subscribes to `STREAM_BACKEND` (Redis Streams `XREAD`/consumer group, or Kafka consumer on `KAFKA_TOPIC_DRILLING`)
  2. For each incoming reading: writes to `drilling_parameters` (Timescale insert), then calls `alert_engine.evaluate(well_id, reading)`
  3. `alert_engine.evaluate()`:
     - fetch current depth → query `events`/`formations` for offset wells within radius at this depth (`geo_service`)
     - run `risk_classifier.predict()` on the current feature window → probability per event_type
     - run `anomaly_service.score()` on the same window
     - run `pattern_service.match()` against known pre-event signatures from matched offset wells
     - **fire an alert only if at least two of the three signals agree** (documented threshold logic — configurable), insert into `alerts`, compute SHAP explanation, push via `ws_manager.broadcast(well_id, alert)`
  4. Also broadcasts every raw reading via `ws_manager.broadcast(well_id, {"type": "parameter_update", ...})` for live charts

### `streaming/producer_sim.py` (dev/demo only)
- Reads Volve WITSML/CSV data and replays it into the stream at configurable speed, so the whole pipeline can be demoed without a live rig connection.

### `streaming/ws_manager.py`
- In-memory (or Redis pub/sub-backed, for multi-instance deployments) registry of `well_id -> set of active WebSocket connections`
- `broadcast(well_id, message)` and `broadcast_global(message)` for the dashboard-wide feed

---

## 7. ML & RAG service details

### `services/geo_service.py`
- `find_nearby_wells(well_id, radius_km)` → PostGIS `ST_DWithin` query on `wells.surface_location`
- `find_nearby_at_depth(well_id, depth_tvd, radius_km)` → joins `well_trajectories` for true 3D proximity, not just surface distance
- `compute_trajectory(well_id)` → wraps `wellpathpy` minimum-curvature calc, writes back `tvd`/`position` into `well_trajectories`

### `services/ml/risk_classifier.py`
- One binary/multiclass XGBoost model per `event_type` (or one multi-output model — decide based on data volume)
- `predict(features) -> {event_type: probability}`
- `explain(features) -> SHAP values, formatted as top-5 contributing features with plain-language labels` (this feeds `alerts.shap_explanation`)
- Training pulls features via `feature_service` (tsfresh) from historical `drilling_parameters` windows labeled by `events`

### `services/ml/anomaly_service.py`
- PyOD `IForest`/`ECOD` fit per-well or per-formation on historical "normal" windows
- `score(current_window) -> anomaly_score (0-1)`

### `services/ml/pattern_service.py`
- Maintains a library of "pre-event signatures" — the N minutes of parameter data immediately before each historical `events` row
- `match(current_window) -> best matching offset event + similarity score`, using `stumpy` matrix profile for fast search and `tslearn` DTW for the final similarity score
- Result includes `matched_offset_well_id` and `matched_event_id`, which is exactly what `alerts` needs

### `services/retrieval_service.py`
- Wraps LlamaIndex: builds a `VectorStoreIndex` over `document_chunks` (via the `PGVectorStore` integration), applies metadata filters (well/formation/depth), reranks top-k with `bge-reranker`
- `query(text, filters) -> ranked chunks with citations`
- `ask(text, filters) -> LLM-composed answer + citations` (RAG endpoint)

### `services/extraction_service.py`
- Prompts the LLM (Ollama/vLLM) with a fixed system prompt + the `EventExtraction` Pydantic schema (fields: `event_type, depth_md, formation_name, severity, volume_bbl, description, root_cause, mitigation`)
- Uses `instructor` (or `Outlines`) to force valid JSON
- Cross-validates depths/units against spaCy NER output; if they disagree, lowers `extraction_confidence` and flags `needs_review`

---

## 8. Auth & RBAC (`core/security.py`, `core/rbac.py`)

Roles: `field_engineer`, `office_engineer`, `admin`, `viewer`

| Action | field_engineer | office_engineer | admin | viewer |
|---|---|---|---|---|
| View wells/alerts/search | ✅ | ✅ | ✅ | ✅ |
| Acknowledge/dismiss alert | ✅ | ✅ | ✅ | ❌ |
| Upload/reprocess documents | ❌ | ✅ | ✅ | ❌ |
| Verify extracted events | ❌ | ✅ | ✅ | ❌ |
| Trigger retrain, manage users | ❌ | ❌ | ✅ | ❌ |

`Depends(require_role("admin"))`-style dependency used on sensitive routes. `AUTH_MODE=keycloak` validates the Keycloak-issued JWT against its JWKS endpoint instead of issuing local tokens.

---

## 9. Docker Compose (services list)

```yaml
services:
  api:            # FastAPI app (uvicorn)
  worker:         # Celery worker (OCR/extraction/ML queues, can split into 2+ worker services by queue)
  beat:           # Celery beat, for scheduled tasks (e.g. periodic retrain check)
  stream-consumer: # streaming/consumer.py long-running process
  postgres:       # postgres:16 with postgis + timescaledb + pgvector extensions baked into image
  redis:
  minio:
  ollama:         # local LLM serving (dev)
  mlflow:         # optional, experiment tracking
  # kafka + zookeeper only in docker-compose.prod.yml
```

Each service reads from the same `.env`. `postgres` uses a custom image (`Dockerfile.postgres`) built `FROM postgis/postgis:16-3.4` with `timescaledb` and `pgvector` extensions installed on top.

---

## 10. Build order (recommended sequence for the coding agent)

1. `config.py`, `db/base.py`, all `models/`, Alembic migration for the full schema in §3.
2. `schemas/` mirroring models.
3. Auth (`core/security.py`, `routers/auth.py`) + RBAC — needed before any protected route works.
4. `routers/wells.py` + `services/geo_service.py` — get the map working first, it's the most visible feature.
5. `routers/documents.py` + MinIO `storage_service.py` (upload working end-to-end, processing can be a stub at first).
6. Celery skeleton (`workers/celery_app.py`, empty tasks) + wire `POST /documents/upload` to enqueue.
7. `services/ocr_service.py` and `services/extraction_service.py`, fill in `tasks_ingest.py`.
8. `services/embedding_service.py`, `services/retrieval_service.py`, `routers/search.py`.
9. `routers/events.py`, `routers/correlation.py`.
10. TimescaleDB `drilling_parameters`, `routers/parameters.py`, `streaming/producer_sim.py` (fake live data to test against).
11. `streaming/consumer.py`, `ws_manager.py`, `routers/ws.py` — wire live updates end-to-end.
12. ML services (`risk_classifier`, `anomaly_service`, `pattern_service`) + `alert_engine.py` + `routers/predictions.py`, `routers/alerts.py`.
13. `scripts/seed_demo_data.py` — load Volve + synthetic Assam data last, once schema is stable, to drive the demo.

---

## 11. Non-functional requirements to keep in mind

- All endpoints that touch time-series or vector data must be **paginated or windowed** — never `SELECT *` on `drilling_parameters` or `document_chunks` without a time/limit bound.
- Every `alerts` row must be traceable: `matched_event_id` → `events` → `document_id`/`source_page` → MinIO file, so a user can click an alert and see the exact original report page it's based on.
- WebSocket broadcast must not block the streaming consumer loop — use `asyncio` queues or a pub/sub layer (Redis pub/sub) between the consumer and connected clients if running multiple API instances.
- All extraction results start as unverified (`extraction_confidence` + `needs_review` flag); nothing from an LLM should be presented to an engineer as ground truth without this flag being visible in the API response.
