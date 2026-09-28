# SMRITI — eRTMAC-NWIS (SIH PS 121)

AI-powered offset-well knowledge and decision-support platform for Oil India Limited's drilling operations
(Smart India Hackathon 2026, PS 121). Team **Slothdevs**.

| Document | What it is |
|---|---|
| [`SMRITI_MASTER_PLAN.md`](SMRITI_MASTER_PLAN.md) | Product plan — single source of truth |
| [`docs/BACKEND_PLAN.md`](docs/BACKEND_PLAN.md) | Backend plan and build record (phase **B0 complete**) |
| [`backend/README.md`](backend/README.md) | Backend developer guide |

## Quick start

```bash
cp .env.example .env
docker compose up -d --build --wait     # postgres, redis, s3, migrate, api, worker
curl localhost:8000/readyz              # {"status":"ready", ...}
# API docs: http://localhost:8000/docs
```

Status: backend skeleton only. Domain features (ingestion, search, correlation, risk, alerts) are planned
phases B1–B6 and currently return HTTP 501 naming their phase.
