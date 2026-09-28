# SMRITI frontend

React + TypeScript web app for SMRITI (eRTMAC-NWIS, SIH PS 121). Current phase: **F1 done** (Well Map, Ingestion, evidence viewer).
Design and roadmap: [`docs/FRONTEND_PLAN.md`](../docs/FRONTEND_PLAN.md).

## Run

```bash
# Whole stack (from the repo root): web app on http://localhost:8080
docker compose up -d --build --wait

# Dev server with hot reload on http://localhost:5173 (needs the API on :8000)
cd frontend && npm ci && npm run dev
```

## Checks

```bash
npm run lint && npm run format:check && npm run typecheck
npm test            # unit/component tests (no services)
npm run e2e         # browser tests against the running stack (:8080)
npm run check:api   # generated API types match the committed contract
```

## API contract

The backend's OpenAPI schema is committed at `src/lib/api/openapi.json`; TypeScript types are generated
into `src/lib/api/schema.d.ts`. After changing the backend API, run from the repo root: `make api-contract`.
CI fails if either file is out of date.
