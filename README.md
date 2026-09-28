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
# Web app:  http://localhost:8080
# API docs: http://localhost:8000/docs
curl localhost:8080/readyz              # {"status":"ready", ...} (via the web server's proxy)
```

Status: backend and frontend skeletons (phases B0 and F0). Domain features (ingestion, search, correlation,
risk, alerts) are planned for phases B1–B6 / F1–F6; their API routes return HTTP 501 naming their phase, and
their screens show that status live.
