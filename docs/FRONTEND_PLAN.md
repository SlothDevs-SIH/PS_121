# SMRITI Frontend — Master Plan & Build Record

**Team:** Slothdevs · **Solution:** SMRITI (working name) · **Problem Statement:** PS 121 — eRTMAC-NWIS (Oil India Limited)
**Parent documents:** [`SMRITI_MASTER_PLAN.md`](../SMRITI_MASTER_PLAN.md) (product) · [`BACKEND_PLAN.md`](BACKEND_PLAN.md) (API and data). This document is the source of truth for the web app. When they disagree, fix all of them in the same PR.
**Document date:** 2026-09-28 (v1.0)
**Frontend phase:** **F0 — Skeleton: ✅ COMPLETE (2026-09-28)**. Next: **F1 — Map & ingestion**.

> ⚠️ **Same honesty rule as the master and backend plans:** a "✅" must point to a file and a test that passed. Every number in §0 and Appendix B was measured on 2026-09-28 in this repository. Everything from F1 onward is a **plan**.

---

## 0. Where the frontend actually stands right now (2026-09-28)

**Built and verified in F0** (evidence in Appendix B):

- **A running web app in the Compose stack.** `docker compose up -d --build --wait` now starts **7** services, all healthy. The new `frontend` service is nginx 1.28 serving the built single-page app at **http://localhost:8080**. It proxies `/api`, `/ws`, `/healthz` and `/readyz` to the API on the same origin, so there is no CORS and no hard-coded host.
- **Stack:** React 19.3, TypeScript 5.9 (`strict` + `noUncheckedIndexedAccess`), Vite 8.3, React Router 8.4, TanStack Query 5, Tailwind CSS 4.3 with design tokens, and lucide icons.
- **App shell:**
  - Sidebar navigation for every screen in master plan §10 (10 screens + System Status). Each unbuilt screen shows the frontend phase that builds it.
  - Header with a live **backend status pill** (ready / degraded: which component / unreachable, polled every 15 s).
  - **Office ↔ Field view** switch. Field view means larger type (19 px root) and a reduced navigation for rig tablets.
  - **Light / Dark / Auto theme**, applied before first paint with no flash. Theme and mode are remembered; storage access is guarded so the app still works when storage is blocked (tested).
- **System Status page (fully built):**
  - Live readiness per backend dependency with latency and detail.
  - Backend version, build SHA, environment, phase and signed-in user.
  - Frontend phase and build.
  - The backend's component-status registry (16 components) from `/api/v1/meta`.
- **Every other screen is a "planned screen" page.** It states the screen's purpose, audience and PS requirements, and **probes its real backend endpoints live**. For example, Well Map shows `501 · backend phase B1` for both of its endpoints. The contract between frontend and backend is visible and tested from day one.
- **Typed API layer:**
  - `backend/app/cli.py openapi` exports the backend's OpenAPI schema. It's committed at `frontend/src/lib/api/openapi.json`, and `openapi-typescript` generates `schema.d.ts` from it.
  - `lib/api/client.ts` turns the backend's error envelope into a typed `ApiError`, exposing `plannedPhase` for 501s, the request ID, and `network_error` when the backend is unreachable.
- **Security headers from nginx:**
  - A strict Content-Security-Policy: `script-src 'self'`, no inline scripts. The pre-paint theme script was moved to `/theme-init.js` for this.
  - `X-Frame-Options: DENY`, `nosniff`, a referrer policy, and `Cache-Control: no-cache` on the HTML with 1-year immutable caching on hashed assets.
  - `X-Request-ID` is passed through to the API (verified with `trace-42`).
- **Tests:**
  - **21 unit/component tests** (Vitest + Testing Library, no services).
  - **14 browser end-to-end tests** (Playwright: 7 scenarios × desktop and tablet) against the real Compose stack through nginx. These include a WebSocket round trip through the proxy, **zero console errors on every screen** (so CSP violations would fail), and **no horizontal scroll at 375 px**.
  - oxlint, Prettier and `tsc -b` are all clean.
- **CI** (`.github/workflows/ci.yml`) now has three jobs:
  1. `backend-checks`, which now also **fails if the backend API changed without re-exporting the frontend's copy of the contract**;
  2. **`frontend-checks`**: generated types up to date, lint, format, type-check, unit tests, build;
  3. **`integration`**: Compose stack → backend integration tests → CLI check → **Playwright e2e** → report uploaded on failure.

  ⏳ The new jobs have not run on GitHub yet — see V-F3.

**Real problems found and fixed while building F0** (kept here, as DHRUVA's doc does, because they're the kind of thing a judge or reviewer asks about):
1. **Live Well Monitor was tagged field-only.** The master plan's own persona table (§2.3) says RTMAC monitoring engineers, who work in the office, use it. The e2e navigation test caught the count mismatch. It's fixed, and a unit test now asserts that office users see Live.
2. **The readiness table overflowed by 6 px at phone width.** The e2e "no horizontal scroll" test caught it. The table now scrolls inside its card.
3. **The theme button read "System"**, which is ambiguous next to "System Status". It now reads "Auto theme" (seen in the screenshot review).

**Not in F0 (planned, see §5):** maps, charts, depth tracks, uploads, search, alerts, copilot, offline/PWA and real login. All wait for their backend phases.

---

## ⚠️ Verification & Discrepancy Log — Read First

| # | Item | Detail | Resolution / action | Status |
|---|---|---|---|---|
| V-F1 | TypeScript pinned to 5.9, not the template's 6.0 | `openapi-typescript` 7.13 (latest) declares `peer typescript@^5.x`; npm refused TS 6 | Pinned `typescript ~5.9.3`; every template compiler option is supported. Revisit when `openapi-typescript` supports TS 6 | ✅ Resolved |
| V-F2 | Playwright pinned to exactly 1.56.1 | That release uses Chromium build 1194, which is pre-installed in the dev sandbox (checked against `browsers.json` of 1.55/1.56/1.57). CI installs the matching browser itself | Keep pinned; bump deliberately with `npx playwright install` | ✅ Resolved |
| V-F3 | New CI jobs not yet observed green on GitHub | Every step run locally with the same commands | Watch the first run; record the link here | ⏳ Open |
| V-F4 | Source maps are shipped in the nginx image | `build.sourcemap: true` puts `*.map` files next to the JS; useful for debugging, but they expose source | Before any OIL pilot (F6): build with `sourcemap: 'hidden'` and strip `*.map` from the image | ⏳ Open |
| V-F5 | Linter is **oxlint** (the Vite template default), not ESLint | Master plan named no linter; oxlint is much faster, supports React rules, and caught fast-refresh export issues | Keep. Add ESLint only if a needed rule (e.g. `jsx-a11y` depth) is missing | ✅ Decided |
| V-F6 | "shadcn/ui" in the master plan | shadcn is a copy-in component convention, not a dependency. F0 hand-writes `Button`, `Card`, `Badge` in that convention (`cn()` = `clsx` + `tailwind-merge`) | Add further shadcn components (Dialog, Tabs, Select, Tooltip…) as needed, copied into `components/ui/` | ✅ Decided |
| V-F7 | Single JS bundle, 125 kB gzip | Fine for F0; Leaflet/D3/ECharts in F1–F3 would grow it | Route-level code splitting (`React.lazy`) from F1; budget in §10 | ⏳ Planned |
| V-F8 | Docker Hub rate limits (HTTP 429) | Hit repeatedly when pulling `node`/`nginx` in the sandbox (same as V-B7) | Retry/back-off worked; `docker save` the images for the finale machine | ⏳ Watch |
| V-F9 | Local image build needed a CA-trusting Node base (sandbox TLS inspection) | Same situation as V-B5 | `frontend/Dockerfile` takes `ARG NODE_IMAGE` / `NGINX_IMAGE`; no sandbox CA committed | ✅ Resolved |
| V-F10 | Map tiles need a Content-Security-Policy change | CSP `img-src` is `'self' data: blob:` only | F1 decides the tile source (self-hosted/offline tiles preferred for the on-prem story) and adds only that host | ⏳ F1 |

---

## 1. Frontend Identity & Scope

| Field | Value (resolved in `package-lock.json`, 2026-09-28) |
|---|---|
| Runtime / package manager | Node 22 (engines `>=22`), npm with committed `package-lock.json` |
| UI | React 19.3, React DOM 19.3 |
| Language | TypeScript 5.9.3 (`strict`, `noUncheckedIndexedAccess`, `verbatimModuleSyntax`, `erasableSyntaxOnly`) |
| Build / dev server | Vite 8.3 (+ `@vitejs/plugin-react`) |
| Routing | React Router 8.4 (data router, `createBrowserRouter`) |
| Server state | TanStack Query 5.104 |
| Styling | Tailwind CSS 4.3 (`@tailwindcss/vite`), CSS-variable design tokens, `clsx` + `tailwind-merge` |
| Icons | lucide-react |
| API types | openapi-typescript 7.13, generated from the backend's exported OpenAPI |
| Unit/component tests | Vitest 5, Testing Library (React 16, jest-dom, user-event), jsdom 30 |
| E2E | Playwright 1.56.1 (Chromium) |
| Lint / format | oxlint 1.86, Prettier 3.9 |
| Serving | nginx 1.28 (alpine), multi-stage Docker image |

**The frontend owns:** master-plan stage **S11** (all screens in §10), the field/office experience, accessibility, client-side performance, the offline well pack (F5), and the UI rules that enforce the product's honesty principles (evidence links, badges, similarity ≠ probability).
**It does not own:** business logic, risk calculations, or unit conversions beyond display. The backend returns canonical units and the frontend only formats them (§3.3).

---

## 2. Architecture

### 2.1 Runtime view

```
 Browser (office laptop · RTMAC wall screen · rig tablet)
   │  https://<host>/            SPA (React)       ─┐
   │  /api/v1/*  REST · SSE (copilot, B5)           │ same origin → no CORS,
   │  /ws/*      WebSocket (live well, alerts; B4)  │ no hard-coded API host
   │  /healthz /readyz                              │
   ▼                                               ─┘
 nginx 1.28 (frontend container) ✅
   ├─ /assets/*        hashed files, Cache-Control: immutable 1y
   ├─ /*               SPA fallback to index.html (no-cache), strict CSP + security headers
   └─ /api /ws /healthz /readyz ──proxy──► api:8000 (FastAPI) ✅
        (Docker DNS resolved per request, so nginx starts even if the API is down)

 Dev: Vite dev server :5173 proxies the same four paths to localhost:8000 (VITE_API_PROXY_TARGET).
```

### 2.2 Code structure and data flow

```
src/main.tsx                entry: <Providers> (QueryClient + ThemeProvider) + <RouterProvider>
src/app/
  router.tsx                routes generated from the screen registry; built screens → real page,
                            others → <PlannedScreen>; "/" → /system; "*" → NotFound
  screens.ts                SCREEN REGISTRY: id, path, title, purpose, audiences, PS refs,
                            phase, status, endpoints — single source for nav + routes + tests
  AppShell.tsx              sidebar nav (filtered by office/field), header (phase, status, toggles)
  theme.tsx / themeContext.ts   ThemeProvider + useTheme (theme choice, resolved theme, mode)
  providers.tsx, queryClient.ts
src/lib/api/
  openapi.json              COMMITTED copy of the backend contract (exported by backend CLI)
  schema.d.ts               GENERATED types (npm run gen:api) — never edit by hand
  client.ts                 apiFetch<T>(), ApiError (code, status, details, requestId, plannedPhase),
                            fetchReadiness() (treats 503 as a report, not an error)
  hooks.ts                  useReadiness (15 s poll), useMeta, useMe; queryKeys
src/lib/storage.ts          guarded localStorage (per-viewer preferences only)
src/components/ui/          Button, Card, Badge (shadcn-style, token-based)
src/components/             BackendStatus (header pill)
src/pages/                  SystemStatus (built), PlannedScreen, NotFound
src/styles/index.css        Tailwind + design tokens (light/dark), field-mode scale
public/theme-init.js        pre-paint theme/mode (external for CSP)
```

**Data flow rule:** components never call `fetch` directly. They use hooks (TanStack Query) → `apiFetch` → the backend. Responses are typed with `components['schemas'][...]` from the generated schema, so a backend contract change breaks the type-check, not the demo.

### 2.3 How the contract stays in sync (end to end)

1. A backend developer changes a route or model.
2. `cd backend && uv run python -m app.cli openapi` rewrites `frontend/src/lib/api/openapi.json`, then `cd frontend && npm run gen:api` regenerates the types (or `make api-contract` does both).
3. CI enforces it twice:
   - `backend-checks` diffs a fresh export against the committed JSON;
   - `frontend-checks` regenerates `schema.d.ts` and fails on any diff.
4. `screens.test.ts` fails if any screen references an endpoint that isn't in the contract.

---

## 3. Conventions

### 3.1 Code

- TypeScript `strict` + `noUncheckedIndexedAccess`; no `any` (use `unknown` + narrowing).
- One component per file for React Fast Refresh. Hooks, contexts and constants live in `.ts` files (oxlint enforces `only-export-components`).
- Server state lives **only** in TanStack Query. UI state is local `useState`, or a small context when shared (theme/mode). No Redux.
- Query keys are centralised in `lib/api/hooks.ts` (`queryKeys`).
- Styling: Tailwind utilities + tokens (`bg-surface`, `text-muted`, `bg-ok-bg`…). **No raw hex colours in components**; add a token in `index.css` instead.
- Tests sit next to their code (`*.test.ts(x)`); browser tests in `e2e/`.
- Prettier: no semicolons, single quotes, width 100, trailing commas.

### 3.2 UI rules that implement the master plan's principles (non-negotiable from F1)

| Master-plan principle | Frontend rule |
|---|---|
| P1 No citation, no claim | Every extracted fact, alert, recommendation and copilot sentence renders an **`<EvidenceLink>`** (document + page → opens the page image with the span highlighted). A component that shows a fact without evidence fails review. |
| P2 TVDSS & formation | Depth labels always name their reference: "2,340 m MD", "1,912 m TVDSS". A bare "depth" is not allowed in UI text. Cross-well views use TVDSS or formation alignment only. |
| P3 Advisory | Wording is "recommended", "consider", "offset evidence suggests", never "do", "will prevent". No control affordances towards rig systems. |
| P6 Honest uncertainty | Risk numbers always show `n of N offsets` and a credible interval. Low-evidence values are de-emphasised (muted, with a "low evidence" badge). **Déjà Vu shows "similarity", never "probability"**; only calibrated classifier outputs may be labelled probability. |
| P7 Human-in-the-loop | **Unverified extracted values render with a dashed outline** and a "unverified" tooltip. Assumed datum/trajectory → an "assumed" badge. Every alert has Useful / Not useful / False alarm buttons. |
| P8 Alarm budget | Alert UI never auto-plays sound for non-critical alerts. Kick/well-control alerts are visually distinct and never collapsed. |
| Data honesty (§24) | Demo data is captioned "Equinor Volve (real)" or "Synthetic Upper-Assam-style", and a persistent **SYNTHETIC** badge appears on any view showing synthetic wells. "eRTMAC" is never expanded. The live stream is labelled "replay" when it is one. |

### 3.3 Units & formatting

- The backend sends canonical SI units with a `unit` field. The frontend converts for display only, via a single `lib/format/units.ts` (F1) that mirrors `backend/app/core/units.py` factors (test: shared fixture values).
- User unit preference (metric/oilfield) is a per-viewer preference in guarded localStorage.
- Numbers: `Intl.NumberFormat('en-IN')` (Indian digit grouping, e.g. 1,23,456); fixed decimals per quantity (depth 0–1 dp, MW 2 dp SG / 1 dp ppg).
- Time: stored/sent as UTC ISO-8601; displayed in IST (`Asia/Kolkata`) with a timezone suffix.

### 3.4 Accessibility (WCAG 2.2 AA target, master plan §9)

- Keyboard reachable everything, with a visible `:focus-visible` ring (token-coloured).
- Colour is never the only signal: badges carry text, and risk colours are paired with labels/icons.
- Landmarks: `<nav aria-label="Main">`, `<main>`, headings in order (one `h1` per page; e2e checks every page has one).
- Contrast: tokens are chosen for AA in both themes. From F2, add an automated axe check in e2e (`@axe-core/playwright`).
- Field view: ≥ 19 px base type and large touch targets (min 36 px height already on buttons; 44 px target in F4 for field controls).

### 3.5 Error, loading and empty states (every data view)

| State | Rendering |
|---|---|
| Loading | Skeleton or "Checking…/Loading…" text; `aria-busy` |
| 501 `not_implemented` | "Planned for backend phase Bx" badge (uses `ApiError.plannedPhase`) — never a generic error |
| Network error | "Backend unreachable" + how to start it (dev) or "retrying" (prod) |
| Other API error | Message + `request_id` (copyable) for support |
| Empty | Explains why and what to do ("No offset wells within 5 km — widen the radius") |

---

## 4. Screen Designs (what each phase will build)

Each screen uses the same layout: **Purpose · Layout · Data (endpoints) · Key components · States & rules · Tests · Done when**. Backend phases are from `BACKEND_PLAN.md` §6.

### 4.1 Well Map — master plan screen 1 (F1, needs B1; other proximity modes F2/B2)

- **Purpose:** offset wells around the active/selected well within a user-defined radius (O-ii, G-i).
- **Layout:**
  - A full-height map on the left.
  - A right panel with the well picker, radius slider (1–20 km, numeric input too), proximity mode segmented control (Surface / At formation + formation picker / Closest approach — the last two disabled with "B2" until the backend supports them), filters (event type, date, status), and the offset list sorted by distance.
- **Data:** `GET /api/v1/wells`, `GET /api/v1/wells/{id}/offsets?radius_km&mode&formation`.
- **Components:**
  - `WellMap` (react-leaflet): active well highlighted; offsets coloured by worst event type and sized by NPT; a radius circle; hover card; click → Well 360.
  - `RadiusControl`, `ProximityModeSwitch`, `OffsetList`.
  - Optional trajectory surface projections.
- **Tiles:** decide in F1 (V-F10). Preferred: a self-hosted/offline tile pack served from our origin (fits on-prem/air-gap), with OSM online tiles as the dev fallback. The CSP is updated for exactly the chosen host.
- **States & rules:** the SYNTHETIC badge when any synthetic well is shown; an "assumed trajectory" badge on wells without surveys; the distance label always names the mode ("3.2 km at Barail entry").
- **Tests:** unit tests for the radius slider ↔ query params sync and the list sort; e2e: move the slider → the list count changes, and clicking a marker → Well 360.
- **Done when:** the radius search works on Volve and the synthetic field, with the URL holding the state (`/map?well=12&r=5&mode=SURFACE`) so views can be shared.

### 4.2 Ingestion & Review — screen 8 (F1 upload/status with B1; review queue F2 with B2)

- **Purpose:** get reports in, and make extraction trustworthy (O-i).
- **Layout:**
  - **Upload tab:** drag-and-drop (multi-file), per-file progress, a SHA-256 "duplicate" notice, and a job list with status (`queued/processed/failed/needs_review`) and error reasons.
  - **Review tab (F2):** a split view with the page image and highlighted spans on the left and the extracted fields on the right (value, unit, confidence bar, evidence span). Accept / Edit / Reject, with keyboard shortcuts (A/E/R, J/K next/previous).
- **Data:** `POST /api/v1/documents`, `GET /api/v1/documents/{id}`, `GET /api/v1/documents/{id}/pages/{n}`, `GET /api/v1/review-queue`, `POST /api/v1/review-queue/{item_id}`.
- **Components:** `DropZone`, `JobTable` (polling while any job is running), `PageViewer` (image + SVG overlay of span bboxes, zoom/pan), `ExtractionForm`.
- **Tests:** upload of fixtures (unit tests with a mocked API; e2e against B1 with a 3-page fixture PDF); the bbox overlay scales correctly with zoom.
- **Done when:** a data steward can upload 10 files, watch them process, and (F2) review a low-confidence event in under 30 seconds.

### 4.3 Well 360 — screen 2 (F2, needs B2)

- **Purpose:** everything about one well (O-iii).
- **Layout:**
  - Header: name, field, rig, spud/TD, a **data-quality score** with its reasons, and SYNTHETIC/assumed badges.
  - Tabs: Overview (casing & cement summary, mud program vs depth mini-chart); Events timeline (by date and by depth); Lessons cards; Documents; Trajectory (plan and section view).
- **Data:** `GET /api/v1/wells/{id}`, `/trajectory`, `/api/v1/events?well_id=`.
- **Components:** `DataQualityBadge`, `CasingSchematic` (simple SVG), `EventTimeline`, `LessonCard`, `EvidenceLink`.
- **Done when:** every number on the page links to evidence or is marked as derived.

### 4.4 Correlation Panel — screen 3 (F2, needs B2)

- **Purpose:** correlate wells by depth and formation (O-iv, G-iii). This is the screen judges will remember; give it the most design time.
- **Layout:** the well picker (from Map selection or search), the alignment switch (TVDSS / Flatten on top + top picker / Formation-relative), track toggles, then a **horizontally scrollable panel of well columns** sharing one vertical depth axis, with a formation statistics table below.
- **Tracks per column:** formation/lithology blocks; casing shoes and hole sizes; MW (and ECD) curve; event markers (icon per type, size by severity/NPT, click → evidence); cement tops. The active well column shows a **hazard strip** (risk-by-depth colour band, from S7a in F3).
- **Data:** `GET /api/v1/correlation?wells=&align=&top=`.
- **Rendering:** a custom **D3** `DepthTrack` component family on SVG (≤ 20 wells × ~5 tracks is fine in SVG; switch a track to canvas only if profiling says so). Shared y-scale; zoom and brush on depth; hover crosshair showing the depth in every column.
- **States & rules:** a well missing the chosen top falls back to TVDSS with a visible badge, never silent interpolation (mirrors BACKEND_PLAN §4.6); axis labels always "m TVDSS" or "relative position in formation".
- **Tests:** unit tests for scale maths (flattening puts the chosen top at 0; formation-relative mapping is monotonic); visual regression screenshot (Playwright) of a fixed synthetic panel.
- **Done when:** a 6-well synthetic panel renders in < 1 s and the event markers link to evidence.

### 4.5 Knowledge Search (+ Copilot) — screen 6 (search F2 with B2; copilot F5 with B5)

- **Purpose:** instant access to drilling history (O-iii, G-ii).
- **Layout:**
  - A search bar with filter chips (well, radius, formation, event type, depth range, date).
  - Results: **lessons cards first** (problem → cause → action → outcome → lesson), then passages with highlighted terms and `[doc:page]` citations.
  - The copilot in a side panel (F5): streamed answer, inline citations, "No record found" shown plainly, and a "Why this answer?" disclosure listing the tools called.
- **Data:** `GET /api/v1/search`, `GET /api/v1/events`, `POST /api/v1/copilot/chat` (SSE via `fetch` + `ReadableStream`).
- **Tests:** citation click opens the correct page; streamed rendering handles partial tokens; the unanswerable fixture shows "No record found".

### 4.6 Mitigation Ledger — screen 7 (F3, needs B3)

- **Purpose:** what actually worked (O-iii, O-vi, USP 2).
- **Layout:** pickers (event type, formation/basin, hole section); a ranked table: action · success "7 of 9" · rate with a **90% credible-interval bar** · median NPT h · n. Rows expand to the individual cases with evidence. Actions with n < 3 appear under an "Insufficient evidence" section, unranked.
- **Rules:** a header note: "Associated with better outcomes; observational data, not causal." "Outcome unknown" is never counted as success or failure.
- **Components:** `IntervalBar` (point + CI whisker, accessible text alternative), `CaseList`.
- **Done when:** the planted-ranking synthetic dataset displays in the planted order (it mirrors the backend ρ test).

### 4.7 Live Well Monitor — screen 4 (F4, needs B4)

- **Purpose:** the field and RTMAC real-time view (O-vi, O-vii).
- **Layout (field-first, works at 800×1280 tablet portrait and 1920×1080 wall screens):**
  - Big-number tiles: bit depth MD/TVD, formation now, next formation + distance, ROP, MW/ECD.
  - **Look-ahead bar:** "Next hazard: Losses risk 43% (3 of 7 offsets) in 64 m TVD ≈ 50 min".
  - Channel strips (torque, hookload, SPP, flow in/out, pit volume) for the last 60 min with a rig-state ribbon.
  - Per-event risk gauges with trend arrows.
  - The alert feed.
  - A "REPLAY ×30" banner when the source is replay.
- **Data:** `WS /ws/wells/{id}/live` (1 Hz channel frames + scores), `GET /api/v1/wells/{id}/risk-profile`.
- **Rendering:** **ECharts** (canvas) for the strips. It keeps a ring buffer of 360 points per channel at 10 s resolution and updates via `setOption` with `notMerge: false` at 1 Hz. It must stay smooth on a mid-range tablet (target: main-thread work < 16 ms per update).
- **Connection handling:** a WebSocket client with backoff reconnect (1, 2, 4… max 30 s). A "Stale data — last update 42 s ago" banner after 10 s without frames. **Never show stale values as live.**
- **Tests:** a WS mock server feeding a scripted stream (reconnect, stale banner, gauge updates); an e2e run against B4 replay.

### 4.8 Alerts & Alert Detail — screen 5 (F4, needs B4)

- **Purpose:** proactive alerts with evidence and recommendations (O-vi, G-iv).
- **Layout:**
  - **Alert list:** severity-sorted with filters; kick/well-control alerts pinned and red; a count against the per-shift budget.
  - **Alert detail** (master plan §Stage 9 template): title · severity · the plain-language trigger · evidence tabs:
    - Offset events (page thumbnails → `PageViewer`)
    - Model drivers (SHAP bar chart)
    - **Déjà Vu overlay:** live curves and the matched pre-event curves time-aligned, labelled "similarity 84%"
    - Physics chart
  - Recommended actions from the ledger with `IntervalBar`s; Acknowledge / Dismiss (with a reason) / Useful / Not useful / False alarm; "Ask copilot about this alert".
- **Data:** `GET /api/v1/alerts`, `POST .../ack|dismiss|feedback`, `WS /ws/alerts`.
- **Notifications:** an in-app toast plus the document title badge. Browser notifications are optional, behind permission, critical alerts only. No sounds for non-critical alerts.
- **Tests:** an alert without evidence cannot render (a component test asserts it throws or shows a defect banner); the lifecycle buttons update state optimistically and roll back on error.

### 4.9 Analytics — screen 9 (F5)

NPT by event type, formation, field and year (ECharts bar/heatmap); recurring problems; alert precision from feedback and alerts per shift. The data comes from aggregate endpoints to be specified with the backend in B5 (**not yet in the API contract** — add them to `BACKEND_PLAN.md` first).

### 4.10 Admin — screen 10 (F6)

Users and roles (read from Keycloak; role mapping only), channel mappings, alert thresholds and budget, replay control (`POST /api/v1/replay`). Visible only to the `admin` role.

### 4.11 System Status — supporting screen (F0 ✅)

Built. From B4 it gains stream status (adapter state, scoring lag) and from B6 build/deploy information and links to Grafana.

### 4.12 Shared components to build (inventory)

| Component | Phase | Notes |
|---|---|---|
| `EvidenceLink` + `PageViewer` | F1 | The heart of principle P1 |
| `ConfidenceValue` (dashed if unverified) | F1 | Used everywhere extracted values appear |
| `Badge` variants: SYNTHETIC, assumed, low-evidence, planned phase | F0/F1 | `Badge` exists |
| `DataTable` (sort, sticky header, virtualised > 200 rows) | F1 | Offsets, jobs, events |
| `WellMap` | F1 | react-leaflet |
| `DepthTrack` family (D3) | F2 | Correlation, Well 360 mini-charts |
| `IntervalBar` | F3 | Ledger, alert recommendations |
| `RiskCurve` (risk vs depth, with CI band) | F3 | Map panel, Live, Well 360 |
| `ChannelStrip` (ECharts) | F4 | Live monitor |
| `DejaVuOverlay` | F4 | USP 1 visual |
| `CopilotPanel` (SSE) | F5 | Search, alert detail |

---

## 5. Designed vs. Built (frontend)

Status keys: 📋 Planned · 🔨 In progress · ✅ Built & tested · ⚠️ Built with a known limitation. Keep in sync with `src/app/screens.ts` (`status`/`phase`).

| # | Item | Phase | Status | Evidence |
|---|---|---|---|---|
| 1 | Vite + React + TS strict project, lockfile | F0 | ✅ | `frontend/package.json`, `package-lock.json`, `tsconfig.*.json` |
| 2 | Design tokens, light/dark/auto theme, field mode, pre-paint script | F0 | ✅ | `src/styles/index.css`, `src/app/theme.tsx`, `public/theme-init.js` · `AppShell.test.tsx` (theme, mode, storage-blocked), e2e "persist across reloads" |
| 3 | App shell, navigation from the screen registry | F0 | ✅ | `src/app/AppShell.tsx`, `src/app/screens.ts` · `screens.test.ts` (5), e2e "every screen loads" |
| 4 | Backend status pill | F0 | ✅ | `src/components/BackendStatus.tsx` · ready/degraded/unreachable test |
| 5 | Typed API client + generated schema + contract checks | F0 | ✅ | `src/lib/api/*`, `backend/app/cli.py openapi` · `client.test.ts` (6), `screens.test.ts` endpoint check, backend `test_cli.py`, CI diff steps |
| 6 | System Status page | F0 | ✅ | `src/pages/SystemStatus.tsx` · `SystemStatus.test.tsx` (3), e2e home test |
| 7 | Planned-screen pages with live endpoint probes | F0 | ✅ | `src/pages/PlannedScreen.tsx` · component + e2e probe tests |
| 8 | nginx image: SPA fallback, proxy (HTTP + WS), CSP/security headers, caching | F0 | ⚠️ ships source maps (V-F4) | `frontend/Dockerfile`, `frontend/nginx/default.conf.template` · e2e WebSocket test, curl header checks (App. B) |
| 9 | Compose `frontend` service, health-gated | F0 | ✅ | `docker-compose.yml` · `up --wait` healthy |
| 10 | CI: frontend-checks + e2e in integration | F0 | ⚠️ not yet observed on GitHub (V-F3) | `.github/workflows/ci.yml` |
| 11 | Well Map | F1 | 📋 | §4.1 |
| 12 | Ingestion upload & job status | F1 | 📋 | §4.2 |
| 13 | `EvidenceLink`, `PageViewer`, `ConfidenceValue`, `DataTable`, units formatter | F1 | 📋 | §4.12, §3.3 |
| 14 | Review queue, Well 360, Correlation Panel, Knowledge Search | F2 | 📋 | §4.2–4.5 |
| 15 | Mitigation Ledger, risk curves on Map/Well 360 | F3 | 📋 | §4.6 |
| 16 | Live Well Monitor, Alerts, Déjà Vu overlay | F4 | 📋 | §4.7–4.8 |
| 17 | Copilot panel, Analytics, Offset Risk Brief button, PWA offline well pack | F5 | 📋 | §4.5, §4.9, §12 |
| 18 | OIDC login (PKCE), role-aware UI, Admin, axe checks, hidden source maps, perf budget enforcement | F6 | 📋 | §4.10, §11 |

---

## 6. Phase Plan (frontend)

Frontend phases follow the backend phases they depend on, typically starting a few days after the backend phase so real endpoints exist. They build against 501 contract stubs and fixtures in the meantime.

| Phase | Needs backend | Master plan | Scope | Exit criteria |
|---|---|---|---|---|
| **F0 Skeleton** | B0 | P0 | Shell, theming, field mode, API layer, System Status, planned screens, nginx image, CI | ✅ **Met 2026-09-28**, except V-F3 (GitHub CI observation) — Appendix B |
| **F1 Map & ingestion** | B1 | P1 | Well Map (surface mode), upload + job status, `EvidenceLink`/`PageViewer`, `ConfidenceValue`, `DataTable`, units formatter, route-level code splitting, tile decision | Radius search on Volve + synthetic wells works end to end in the browser; 10 files uploaded and tracked; e2e covers both |
| **F2 Knowledge** | B2 | P2 | Review queue, Well 360, **Correlation Panel**, Knowledge Search, at-formation/closest-approach modes on the map, axe checks in e2e | Correlation panel renders 6 wells < 1 s with evidence links; review round trip; search with citations |
| **F3 Risk & ledger** | B3 | P3a | Mitigation Ledger, `RiskCurve` on Map/Well 360/Correlation hazard strip | Ledger shows the planted ranking; risk curves show n and CI |
| **F4 Real-time** | B4 | P3b | Live Well Monitor, Alerts list/detail, Déjà Vu overlay, WebSocket client with reconnect/stale handling | Replay → alerts appear in the UI ≤ 5 s after the backend emits them (measured); tablet smoothness target met |
| **F5 Copilot & polish** | B5 | P4 | Copilot panel (SSE), Analytics, Offset Risk Brief download, PWA with an offline well pack | Copilot answers with clickable citations; field view usable offline for a cached well (knowledge views only) |
| **F6 Hardening** | B6 | P5 | OIDC PKCE login, role-aware UI, Admin, hidden source maps, bundle budget in CI, usability test (master plan §13.6) | SUS ≥ 70 measured; performance budgets (§10) met and recorded |

### 6.1 F1 task breakdown (next up — ordered)

1. `lib/format/units.ts` + tests sharing fixture values with `backend/app/core/units.py`.
2. `ConfidenceValue`, `EvidenceLink` (with a stub `PageViewer` dialog), `DataTable` (TanStack Table).
3. Route-level code splitting: `React.lazy` per screen; keep the shell in the main chunk.
4. Tile decision (V-F10) + `WellMap` with react-leaflet; update the CSP `img-src` for exactly that host.
5. Well Map page against B1 (`/wells`, `/offsets?mode=SURFACE`), URL-synced state, SYNTHETIC/assumed badges.
6. Ingestion upload tab (`POST /documents`, job polling), with the 3-page fixture shared with backend tests.
7. Mark `map` and `ingest` as `built` in `screens.ts`; update §5 here and in the master plan; add e2e scenarios.

---

## 7. Configuration Reference

| Variable | Where | Default | Meaning |
|---|---|---|---|
| `VITE_API_PROXY_TARGET` | Vite dev server (shell env) | `http://localhost:8000` | Backend the dev server proxies to |
| `VITE_GIT_SHA` | Build time (set from Docker `GIT_SHA` build arg) | `dev` | Shown on System Status |
| `API_UPSTREAM` | nginx container env | `http://api:8000` | Backend the nginx proxy targets (substituted into the template at start) |
| `WEB_PORT` | Compose (`.env`) | `8080` | Host port for the web app (bound to 127.0.0.1) |
| `E2E_BASE_URL` | Playwright | `http://localhost:8080` | Stack under test |
| `CI` | Playwright | unset | Enables 1 retry and the HTML report in CI |
| Docker build args | `frontend/Dockerfile` | `NODE_IMAGE=node:22-alpine`, `NGINX_IMAGE=nginx:1.28-alpine`, `GIT_SHA=dev` | Mirrors / CA-trusting bases (V-F9) |

Per-viewer preferences in localStorage (guarded; not reliable state): `smriti.theme` (`light|dark|system`) and `smriti.mode` (`office|field`); F1 adds `smriti.units`.

---

## 8. Design System

**Tokens (`src/styles/index.css`):** `bg`, `surface`, `surface-2`, `border`, `text`, `text-muted`, `accent`/`accent-contrast`, plus the status pairs `ok`, `warn`, `danger`, `info` (each with a `-bg`). All are defined for light and dark and exposed to Tailwind as `bg-surface`, `text-muted`, `bg-ok-bg`, and so on.

**Planned semantic tokens (F3/F4):**
- Event-type palette: LOSS, KICK, STUCK, TORQUE, CEMENT, OVERP, OTHER — colour-blind-safe and paired with icons.
- Risk scale: sequential, 5 steps.
- Synthetic-data badge colour.

Chart colours follow the same tokens, so charts switch theme with the app.

**Typography:** a system UI font stack (no web-font download, better offline); tabular numbers (`tabular-nums`) for all measurements; 16 px base in office view, 19 px in field view.

**Field view:** larger type, a reduced navigation (Map, Correlation, Live, Alerts, Search, Ledger, System), dark theme recommended for control rooms, and touch targets ≥ 44 px from F4.

---

## 9. Testing Strategy & CI

| Layer | Tooling | Runs | F0 count |
|---|---|---|---|
| Unit / component | Vitest + Testing Library + jsdom; `mockBackend()` fetch table; `renderApp(path)` with the real router | every push (`frontend-checks`) | **21 ✅** |
| Contract | `check:api` (types regenerated = committed), backend export diff, `screens.test.ts` endpoint check | every push | **3 checks ✅** |
| Browser e2e | Playwright (Chromium), desktop 1280×720 + tablet 800×1280 projects, against the Compose stack through nginx | `integration` job | **14 ✅** (7 scenarios × 2) |
| Visual regression | Playwright screenshots of fixed synthetic views | from F2 (correlation panel) | 0 |
| Accessibility | `@axe-core/playwright` on every screen | from F2 | 0 |

**E2E guarantees already enforced:**
- No console errors on any screen (catches CSP violations and runtime errors). The only whitelisted message is the browser's own log line for deliberate 501 probe responses.
- Every screen has an `h1`.
- No horizontal page scroll at 375 px.
- WebSockets work through the proxy.

**Rules:** a bug fix starts with a failing test (both F0 layout bugs above were caught by tests first); no `sleep` in tests (use Playwright auto-waiting); fixtures are shared with backend tests where the same files are involved.

---

## 10. Performance Budgets (targets — measured in F6 unless noted)

| Metric | Budget | F0 measured |
|---|---|---|
| Initial JS (gzip) | ≤ 180 kB for the shell; each screen chunk ≤ 150 kB | **125 kB** (single chunk; `vite build`, 2026-09-28) |
| CSS (gzip) | ≤ 20 kB | **4.1 kB** |
| Largest Contentful Paint (office laptop, LAN) | ≤ 1.5 s | not measured |
| Correlation panel render, 6 wells | ≤ 1 s | F2 |
| Live monitor update cost (tablet) | < 16 ms main-thread per 1 Hz update | F4 |
| Alert shown after the backend emits it | ≤ 1 s (inside the 5 s end-to-end budget) | F4 |

---

## 11. Security

- **F0 ✅:**
  - Strict CSP (`script-src 'self'`, no inline scripts, `frame-ancestors 'none'`, `connect-src 'self' ws: wss:`), `X-Frame-Options: DENY`, `nosniff`, a referrer policy, and `server_tokens off`.
  - Same-origin API (no CORS surface).
  - No secrets in the bundle: the only build-time variable is the git SHA.
  - Port bound to 127.0.0.1.
- **F6:**
  - OIDC Authorization Code + **PKCE** with Keycloak (e.g. `oidc-client-ts`). Access tokens are held **in memory only** (never in localStorage); silent renew; logout.
  - The WebSocket auth token is sent in the first message (per BACKEND_PLAN §4.15).
  - Role-aware navigation (hiding is UX only; the backend enforces roles).
  - Hidden source maps (V-F4).
  - `npm audit` (production dependencies) in CI.
  - Subresource integrity is not needed (everything is same-origin).
- **Content safety:** extracted document text is always rendered as text, never as HTML (`dangerouslySetInnerHTML` is banned; lint rule in F1). Copilot output is rendered through a Markdown renderer with HTML disabled.

---

## 12. Offline Field Mode (F5 design)

- A **PWA** (Workbox via `vite-plugin-pwa`): the app shell is cached, so the field view opens without a network connection.
- **Well pack:** for the active well, cache offsets, correlation JSON, the risk profile, lessons cards, ledger rows and small page thumbnails in IndexedDB (versioned, with a size cap of ~50 MB and an explicit "Download well pack" button with progress).
- **What works offline:** Map (with cached tiles for the pack area), Correlation, Well 360, Lessons, Ledger. **What doesn't:** live monitor, alerts, copilot, new searches. The UI says exactly this in an offline banner (master plan Q&A: "Live alerts need the link to the server near eRTMAC").

---

## 13. Frontend Architecture Decision Log

| ID | Chose | Over | Why |
|---|---|---|---|
| ADR-F1 | React + Vite SPA | Next.js (SSR), Streamlit/Dash | On-prem static hosting behind nginx; no Node server to run at OIL; rich custom visuals (D3 tracks, live charts) that Streamlit can't do well |
| ADR-F2 | Same-origin proxy (nginx / Vite) | CORS + absolute API URLs | No CORS surface, one URL to deploy, same code in dev and prod |
| ADR-F3 | TanStack Query for server state | Redux / Zustand for everything | Caching, polling, retries and invalidation built in; nearly all state is server state |
| ADR-F4 | Types generated from the backend OpenAPI, committed, with CI drift checks | Hand-written types / runtime-only validation | The frontend and backend can't silently disagree; a diff shows up in review |
| ADR-F5 | Tailwind v4 + CSS-variable tokens + shadcn-style components | A component library (MUI/Ant) | Full control of the field/dark theme and density; small CSS; no heavy dependency |
| ADR-F6 | Leaflet (react-leaflet) for maps | Google Maps, Mapbox | No keys or cost, offline tile packs possible; 2D offsets suffice (master plan ADR) |
| ADR-F7 | D3 for depth tracks; ECharts for time series/analytics | One charting library for all | Correlation tracks are bespoke (shared depth axis, flattening) → D3; live strips need fast canvas → ECharts |
| ADR-F8 | Screen registry drives routes + nav + tests | Hand-maintained route list | One place to change; tests guarantee all 10 plan screens exist and use real endpoints |
| ADR-F9 | Planned screens probe real endpoints | Static "coming soon" pages | Shows honest, live build status (501 + phase) and exercises the proxy/contract from day one |
| ADR-F10 | TypeScript 5.9 | TypeScript 6.0 (template default) | Type generator compatibility (V-F1) |
| ADR-F11 | oxlint | ESLint | Template default; fast; sufficient rules; revisit if an a11y rule is missing (V-F5) |
| ADR-F12 | Web app (responsive + PWA) | Native mobile app | Master plan ADR: one codebase for office and field; no app-store deployment inside a PSU network |

---

## 14. Frontend Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| RF1 | The correlation panel (D3) takes longer than planned | Medium | High | Start in F1 on static fixture JSON; ECharts fallback for simple tracks (master plan R10) | UI eng. |
| RF2 | Live strips stutter on rig tablets | Medium | High | Canvas (ECharts), ring buffers, 1 Hz updates, profiling on a mid-range tablet in F4 | UI eng. |
| RF3 | Map tiles unavailable offline or blocked by CSP | Medium | Medium | Self-hosted tile pack; CSP updated for exactly one host (V-F10) | UI + infra |
| RF4 | Contract drift frontend ↔ backend | Low (CI guarded) | Medium | Three drift checks (§2.3) | Both |
| RF5 | Bundle bloat from map/chart libraries | Medium | Medium | Route-level lazy loading from F1; budgets in §10 checked in CI from F6 | UI eng. |
| RF6 | UI overclaims (probability vs similarity, missing evidence) | Medium | High | §3.2 rules; component tests that fail without evidence; docs lead reviews every screen against master plan §24 | UI eng. + docs lead |
| RF7 | Accessibility gaps found late | Medium | Medium | axe in e2e from F2; keyboard review per screen | UI eng. |

---

## 15. Frontend Q&A Preparation

**"Is the UI a mock-up?"**
No. It's a running app in the same Docker stack as the backend. The System Status page is live. Every unbuilt screen shows, live, which backend phase its endpoints are waiting on. We don't show fake screens with invented data.

**"How does it work at a rig with poor connectivity?"**
The field view uses larger type and a reduced navigation now. From F5, it installs as an app and caches a well pack for offline reading. Live alerts still need the connection to the server near eRTMAC, and the UI says so.

**"How do you keep frontend and backend in sync?"**
The frontend's API types are generated from the backend's OpenAPI schema, and CI fails on any drift in either direction.

**"Is it secure enough for OIL's network?"**
- Same-origin only, with a strict Content-Security-Policy and no inline scripts.
- Security headers on every response, and no secrets in the bundle.
- OIDC login with in-memory tokens comes in F6.
- The backend enforces roles; the UI only hides what a role can't use.

**"Why a web app and not a mobile app?"**
One codebase serves office laptops, RTMAC wall screens and rig tablets, with no app-store deployment inside a PSU network. It's responsive and installable as a PWA.

---

## 16. Immediate Next Actions (frontend)

1. **Watch the first GitHub CI run with the new jobs**; fix anything it finds; resolve V-F3.
2. **F1 kickoff:** §6.1 tasks 1–3 (units formatter, evidence components, code splitting). These can start now against fixtures — UI eng.
3. **Tile decision** (V-F10): the self-hosted tile pack option and its size for the demo area — UI eng. + infra.
4. **Correlation panel spike on static JSON** (RF1) — start early; it's the highest-risk UI component.
5. **`docker save`** the node/nginx base images for the finale machine (V-F8).

---

## Appendix A — Frontend File Tree (as built in F0)

```
frontend/
├── Dockerfile                     node build → nginx serve (NODE_IMAGE / NGINX_IMAGE overridable)
├── .dockerignore · .gitignore · .prettierrc.json · .prettierignore
├── nginx/default.conf.template    SPA + proxy (/api, /ws, /healthz, /readyz) + CSP/security headers
├── index.html                     loads /theme-init.js before the app
├── public/ favicon.svg · theme-init.js
├── package.json · package-lock.json
├── tsconfig.json · tsconfig.app.json · tsconfig.node.json
├── vite.config.ts                 dev proxy + Vitest config
├── playwright.config.ts           desktop + tablet projects against :8080
├── e2e/smoke.spec.ts              7 browser scenarios
└── src/
    ├── main.tsx · vite-env.d.ts
    ├── app/        AppShell.tsx · router.tsx · screens.ts · theme.tsx · themeContext.ts
    │               providers.tsx · queryClient.ts · AppShell.test.tsx · screens.test.ts
    ├── components/ BackendStatus.tsx · ui/{Badge,Button,Card}.tsx
    ├── lib/        cn.ts · storage.ts
    │   └── api/    openapi.json (committed contract) · schema.d.ts (generated)
    │               client.ts · hooks.ts · client.test.ts
    ├── pages/      SystemStatus.tsx · PlannedScreen.tsx · NotFound.tsx · SystemStatus.test.tsx
    ├── styles/     index.css (Tailwind + tokens)
    └── test/       setup.ts · utils.tsx (mockBackend, renderApp, fixtures)
```

Related changes outside `frontend/`:
- `backend/app/cli.py` gains the `openapi` command (+ `backend/tests/unit/test_cli.py`).
- `docker-compose.yml` gains the `frontend` service; `.env.example` gains `WEB_PORT`.
- `.github/workflows/ci.yml` gains `frontend-checks`, the contract diff step and the e2e steps.
- `Makefile` gains `web-*` targets and `api-contract`.

## Appendix B — F0 Verification Record (2026-09-28)

| Check | Command | Result |
|---|---|---|
| Type-check | `npm run typecheck` (`tsc -b`) | no errors |
| Lint | `npm run lint` (oxlint, `--deny-warnings`) | clean (after splitting `themeContext.ts` / `queryClient.ts` out for fast refresh) |
| Format | `npm run format:check` | "All matched files use Prettier code style!" |
| Unit/component tests | `npm test` | **4 files, 21 passed** |
| Generated types in sync | `npm run check:api` | exit 0 |
| Backend contract export = committed copy | `uv run python -m app.cli openapi --out /tmp/oa.json && diff` | identical (25 paths / 25 operations) |
| Backend suite after the CLI change | ruff, ruff format, mypy strict, pytest, pytest -m integration | clean · **31 passed** (was 30; + `test_cli.py`) · **5 passed** |
| Production build | `npm run build` | `index.js` 398.88 kB (**125.01 kB gzip**), `index.css` 15.22 kB (**4.12 kB gzip**) |
| Stack up | `docker compose up -d --wait` | api, frontend, postgres, redis, s3, worker **healthy** (migrate exited 0) |
| Routes through nginx | `curl localhost:8080{/,/system,/map,/nope}` | 200 `text/html` (SPA fallback) |
| API via nginx | `/readyz` 200 JSON · `/api/v1/meta` 200 · `/api/v1/wells` **501** JSON | as designed |
| Headers | `curl -I localhost:8080/` | CSP as in §11, `X-Frame-Options: DENY`, `Cache-Control: no-cache` |
| Request-ID pass-through | `curl -H 'X-Request-ID: trace-42' localhost:8080/api/v1/wells` | response `x-request-id: trace-42` |
| Browser e2e | `npm run e2e` (Playwright 1.56.1, Chromium) | **14 passed** (7 scenarios × desktop + tablet) |
| Visual review | Playwright screenshots: System Status (light, 1280), Well Map (dark, 1280), Live Well Monitor (field + dark, 800 wide), System Status (375 wide) | Layouts correct; the 375 px table overflow and the "System" theme label were found here and fixed |

## Appendix C — Document Maintenance Rules

Same as master plan Appendix F and backend plan Appendix C:
- Dated update lines go in the header.
- Correct wrong statements in place with a dated note.
- Update §5 here and `src/app/screens.ts` in the same PR as the code.
- Every "✅" cites a file and a test.
