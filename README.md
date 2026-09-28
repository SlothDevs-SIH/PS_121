# SMRITI — eRTMAC-NWIS (SIH PS 121)

AI-powered offset-well knowledge and decision-support platform for Oil India Limited's drilling operations
(Smart India Hackathon 2026, PS 121). Team **Slothdevs**.

| Document | What it is |
|---|---|
| [`SMRITI_MASTER_PLAN.md`](SMRITI_MASTER_PLAN.md) | Product plan — single source of truth |
| [`docs/BACKEND_PLAN.md`](docs/BACKEND_PLAN.md) | Backend plan and build record (phase **B0 complete**) |
| [`docs/FRONTEND_PLAN.md`](docs/FRONTEND_PLAN.md) | Frontend plan and build record (phase **F0 complete**) |
| [`backend/README.md`](backend/README.md) · [`frontend/README.md`](frontend/README.md) | Developer guides |

## Quick start

```bash
cp .env.example .env
docker compose up -d --build --wait     # postgres, redis, s3, migrate, api, worker, frontend
make seed                               # synthetic Upper-Assam-style field: 42 wells, ~190 reports
# Web app:  http://localhost:8080
# API docs: http://localhost:8000/docs
curl localhost:8080/readyz              # {"status":"ready", ...} (via the web server's proxy)
```

Status: **Part 1 done** (phases B0–B1 and F0–F1): report ingestion with OCR and evidence highlighting, well
master data with 3D trajectories, offset-well search, and the Well Map and Ingestion screens, all on a
**synthetic** Upper-Assam-style dataset (not Oil India data). Later features (extraction, search, correlation,
risk, alerts, copilot) are planned for phases B2–B6 / F2–F6; their API routes return HTTP 501 naming their phase,
and their screens show that status live.
