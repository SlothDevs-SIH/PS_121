# NWIS — Nearby Wells Intelligence System

An AI/ML-enabled decision-support platform that gives drilling teams instant, geospatial access to institutional knowledge from nearby and historical wells — built alongside Oil India's eRTMAC real-time monitoring system.

This README documents the full tech stack and, for every tool, **why it was chosen** and what it was chosen over.

---

## Table of Contents

1. [Document Processing (OCR & Extraction)](#1-document-processing-ocr--extraction)
2. [AI Models (Language, Embeddings, Retrieval)](#2-ai-models-language-embeddings-retrieval)
3. [Machine Learning & Analytics](#3-machine-learning--analytics)
4. [Backend](#4-backend)
5. [Data Storage](#5-data-storage)
6. [Frontend](#6-frontend)
7. [DevOps](#7-devops)
8. [Demo Data](#8-demo-data)
9. [Final Stack at a Glance](#9-final-stack-at-a-glance)

---

## Guiding principles

Every tool below is chosen against the same five constraints:

- **Self-hosted where possible** — drilling data is sensitive for a public-sector operator, so nothing leaves OIL infrastructure by default.
- **Works on small, messy, imbalanced data** — historical drilling events (kicks, stuck pipe) are rare and reports are often scanned PDFs, which rules out data-hungry deep learning.
- **Explainable** — an engineer won't act on an alert they can't understand, so every prediction must be traceable to a reason and a source document.
- **Real-time capable** — must run alongside the live eRTMAC feed with low latency.
- **Buildable fast** — fewer moving parts, mature libraries, minimal glue code.

---

## 1. Document Processing (OCR & Extraction)

| Tool | Used for | Why this one |
|---|---|---|
| **Docling** (IBM) | PDF & layout parsing | Preserves tables, headings and reading order — critical because mud programs, casing tables and formation tops lose their meaning if flattened into plain text like `PyPDF`/`pdfminer` would do |
| **PaddleOCR** (Tesseract as fallback) | OCR on scanned pages | Old well reports are frequently noisy scans with dense tables; PaddleOCR is more accurate on this kind of content than Tesseract, which is kept only as a lightweight fallback |
| **TrOCR** (optional) | Handwritten notes | Legacy reports sometimes carry handwritten annotations that standard OCR engines cannot read; TrOCR is a transformer model purpose-built for handwriting |
| **LLM + Pydantic schema** (via `instructor` / `Outlines`) | Structured extraction | Regex cannot handle the many phrasings of an event ("lost 120 bbl at 2,340 m" vs "circulation loss, ~2340m MD"). An LLM understands the sentence; the Pydantic schema forces valid, predictable JSON out of it, so the pipeline never breaks on malformed output |
| **spaCy** + custom rules | Entity tagging (depths, units, well/formation names) | Fast, deterministic, and free — also acts as a sanity check on the LLM's output (e.g. flags a depth deeper than the well's total depth) |

**Rejected:** cloud OCR/extraction services (Azure Document Intelligence, AWS Textract, Google Vision) — technically strong, but they send sensitive drilling data outside OIL's infrastructure.

---

## 2. AI Models (Language, Embeddings, Retrieval)

| Tool | Used for | Why this one |
|---|---|---|
| **Qwen 2.5 / Llama 3.1 (8B–14B)** via **Ollama** (demo) / **vLLM** (production) | Self-hosted language model | Strong enough for extraction and summarization, runs on a single GPU, keeps all data on-premises |
| **BGE-M3** (or `nomic-embed-text`) | Embeddings | Runs locally, handles long technical passages well, strong retrieval benchmark performance, multilingual |
| **bge-reranker** | Re-ranking search results | Vector search alone returns "roughly similar" passages; the reranker re-scores against the actual query, which matters when an engineer needs *the* relevant lesson, not ten vaguely related ones |
| **LlamaIndex** | Retrieval pipeline | Purpose-built for document-heavy retrieval: chunking, metadata filters (well/formation/depth), hybrid search and citations come ready-made, saving build time versus LangChain's heavier abstractions |

**Rejected:** GPT/Claude-class hosted APIs as the default path (kept only as an optional demo enhancement) — better raw quality, but data leaves OIL; models above 14B — GPU cost not realistic for a first deployment.

---

## 3. Machine Learning & Analytics

**Why classical ML, not deep learning, for risk prediction:** kicks, stuck pipe and severe losses are rare events — a field may have hundreds of wells but only a few dozen labelled incidents. Deep networks need thousands of examples and overfit on data this small; gradient-boosted trees perform well on small tabular data and stay explainable.

| Tool | Used for | Why this one |
|---|---|---|
| **XGBoost / LightGBM** | Risk classification (loss, stuck pipe, kick, torque spike) | Best accuracy on small tabular data, handles missing values (common in field records) and class imbalance natively, fast to train/infer |
| **SHAP** | Explaining predictions | Gives a per-alert reason ("mud weight 0.8 ppg above the offset-well loss threshold was the main driver") — essential for an engineer to trust and act on an alert |
| **PyOD** (Isolation Forest, ECOD) | Anomaly detection | Works without labels, useful since confirmed event labels are scarce; catches unusual torque/pressure drift that hasn't been seen before |
| **stumpy** (matrix profile) + **tslearn** (DTW) | Pattern matching against offset wells | Finds "the last 200 m of this well's torque/ROP looks like what preceded the stuck pipe in offset well X" — DTW compares curves even when depth intervals are stretched between wells; needs no training data, so it works from even a single past incident |
| **tsfresh** | Time-series feature engineering | Automatically generates hundreds of features (trend, variance, spikes) from drilling parameter windows to feed into XGBoost |
| **Pandas / Polars, NumPy** | General data handling | Standard, fast, well-supported |
| **lasio, welly, WITSML parser** | Well log / real-time data formats | Well logs come in LAS format; eRTMAC-type feeds use WITSML — existing libraries avoid writing custom parsers |
| **wellpathpy** | Wellbore trajectory calculation | Converts survey data into true vertical depth and 3D coordinates via minimum curvature — essential so "nearby wells" are compared by real 3D distance, not just surface location, which matters for deviated wells |

**Rejected:** LSTM/Transformer forecasters (need far more labelled data than available); plain Euclidean distance for pattern matching (fails when depth scales differ between wells).

**How alerts stay trustworthy:** an alert only fires when multiple signals agree — proximity to a depth/formation where an offset well had an event, a high classifier risk score, and a live parameter pattern that resembles a pre-event pattern. Requiring agreement across signals reduces false alarms, the main reason field alert systems get ignored.

---

## 4. Backend

| Tool | Used for | Why this one |
|---|---|---|
| **FastAPI** | API layer | Async, native WebSocket support for live push, automatic docs, and same language (Python) as the ML/OCR code — no service boundary between model and API |
| **Celery + Redis** | Background jobs | OCR and LLM extraction on a large PDF can take minutes; must run as a background job with retries and status tracking instead of blocking a request |
| **Redis Streams** (demo) / **Apache Kafka** (production) | Real-time stream ingestion | Redis Streams is trivial to run for a demo; Kafka is the industry standard for the durable, high-volume, replayable stream a real eRTMAC feed needs at scale |
| **WebSockets** (via FastAPI) | Live push to dashboard | Alerts and live curves must appear the moment they occur — polling adds delay |
| **Keycloak** (or FastAPI + JWT for demo) | Auth & roles | Role-based access for field vs. office vs. admin users; Keycloak adds SSO/enterprise directory integration for production |

**Rejected:** Django (heavier than needed), Flask (no native async/WebSockets), Node/Express (would split the codebase away from the Python ML stack).

---

## 5. Data Storage

**Core decision: one PostgreSQL database, extended with three extensions**, instead of separate specialized databases — this means one backup strategy, one security model, and SQL joins across spatial, vector and time-series data in a single query.

| Tool | Used for | Why this one |
|---|---|---|
| **PostgreSQL** | Main database | One system for everything below |
| **PostGIS** | Geospatial queries | Radius search ("wells within 10 km") and 3D distance between wellbore paths, in plain SQL |
| **pgvector** | Vector/semantic search | Keeps embeddings next to metadata, so a query like "similar loss events, same formation, within 15 km" is one query, not a cross-database join |
| **TimescaleDB** | Time-series storage | Compressed, fast storage and queries for real-time drilling parameters |
| **MinIO** | File storage | Stores original PDFs so every extracted fact and alert can link back to the exact source page — this is what builds engineer trust in the system |
| **Neo4j** (optional) | Knowledge graph | Only added if graph-style queries (well → event → cause → mitigation chains) are a headline feature; otherwise relational tables are sufficient |

**Rejected:** Pinecone/Weaviate/Milvus/Qdrant (a second database to run, sync and secure — pgvector is sufficient at this scale); InfluxDB (weaker SQL joins with well metadata than TimescaleDB); AWS S3 (cloud, data leaves OIL).

---

## 6. Frontend

**Core decision: React over Flutter.** Flutter's animation strength is built for native mobile; for a browser-based dashboard demo, its map/GIS ecosystem (equivalents of Leaflet, MapLibre, deck.gl, D3) is weak or nonexistent on Flutter Web. React also talks to the FastAPI backend over plain REST/WebSocket with zero extra plumbing, and its animation libraries deliver cinematic polish with far less code.

| Tool | Used for | Why this one |
|---|---|---|
| **React + TypeScript + Vite** | Framework | Fastest dev loop, type safety for complex dashboard state, large ecosystem |
| **Tailwind CSS** | Styling | Speed — no hand-written CSS files to manage under time pressure |
| **shadcn/ui** | Component base | Pre-built, good-looking components (cards, dialogs, tables) to customize instead of building from scratch |
| **Framer Motion** | Page & element transitions | The single biggest lever for a polished feel — page transitions, staggered list reveals, hover/tap micro-interactions and layout animations in only a few lines of code |
| **GSAP + ScrollTrigger** (optional) | Scroll-triggered / timeline animation | Only needed for a hero sequence requiring frame-level timeline control; Framer Motion's `whileInView` covers most dashboard polish on its own |
| **lucide-react** | Icons | Clean, consistent, and animatable alongside Framer Motion |
| **MapLibre GL** | Geospatial map | Smooth pan/zoom/`flyTo` animation, 3D tilt and animated markers — visibly more polished than Leaflet's static rendering; consumes GeoJSON directly from PostGIS (`ST_AsGeoJSON`) |
| **react-three-fiber + @react-three/drei** (Three.js) | 3D wellbore trajectory | Makes a rotating 3D wellbore visualization achievable in hours rather than days |
| **Apache ECharts** (`echarts-for-react`) | Live parameter curves | Built-in smooth animated transitions on data updates — looks alive with no extra animation code, and consumes plain JSON straight from TimescaleDB queries |
| **cmdk** | Command palette / search | A ⌘K searchable knowledge repository feels like a mature product for minimal build effort |
| **tsparticles** (optional) | Ambient background effects | Cheap way to make hero/landing screens feel premium |
| **TanStack Query** | Server state management | Caching and refetching of API data with minimal boilerplate |

**Rejected:** Flutter (weak web/GIS ecosystem, adds a Dart↔Python boundary to a Python backend); Leaflet as the primary map (functional but visually static compared to MapLibre); Angular (heavier setup than needed for a one-day build).

---

## 7. DevOps

| Tool | Used for | Why this one |
|---|---|---|
| **Docker + Docker Compose** | Local/demo orchestration | One command brings up the entire stack |
| **Kubernetes** | Production orchestration path | Scaling and resilience for a real deployment, shown as the natural next step from Compose |
| **MLflow** | ML experiment tracking | Every alert can be traced back to a specific model version and its metrics |
| **Prometheus + Grafana** | Monitoring | System health and model drift visibility |
| **GitHub Actions** | CI | Automated testing/builds on push |

---

## 8. Demo Data

| Source | Provides |
|---|---|
| **Equinor Volve dataset** | Real, open Daily Drilling Reports, WITSML real-time data, well logs, trajectories |
| **Norwegian Offshore Directorate (Sodir) FactPages** | Formation tops, well coordinates |
| **Synthetic Assam-basin data** | LLM-generated offset wells and DDRs with injected events, to demonstrate OIL-relevant behaviour |

> **Note:** results on synthetic or Volve data demonstrate that the *pipeline* works, not real-world accuracy on OIL's own fields. This should be stated openly in any demo, with real OIL data validation positioned as the next step (pilot phase).

---

## 9. Final Stack at a Glance

```
Document AI     Docling · PaddleOCR (+Tesseract, TrOCR) · LLM+Pydantic · spaCy
Language/RAG    Qwen 2.5 / Llama 3.1 (Ollama/vLLM) · BGE-M3 · bge-reranker · LlamaIndex
ML/Analytics    XGBoost/LightGBM · SHAP · PyOD · stumpy/tslearn (DTW) · tsfresh
                lasio · welly · wellpathpy · Pandas/Polars
Backend         FastAPI (WebSockets) · Celery + Redis · Redis Streams/Kafka · Keycloak
Storage         PostgreSQL + PostGIS + pgvector + TimescaleDB · MinIO · (Neo4j optional)
Frontend        React + TypeScript + Vite · Tailwind + shadcn/ui · Framer Motion
                MapLibre GL · react-three-fiber · Apache ECharts · cmdk · TanStack Query
DevOps          Docker Compose → Kubernetes · MLflow · Prometheus/Grafana · GitHub Actions
```

**One-liner for a slide:**
*Docling, PaddleOCR, Qwen/Llama, LlamaIndex, BGE-M3, XGBoost, SHAP, stumpy/DTW, FastAPI, Celery, Redis/Kafka, PostgreSQL (PostGIS + pgvector + TimescaleDB), MinIO, React, Framer Motion, MapLibre GL, ECharts, Docker.*
