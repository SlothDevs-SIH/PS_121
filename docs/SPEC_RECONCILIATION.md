# SMRITI ↔ Final Spec — Reconciliation Record

**Date:** 2026-09-29 · **Status:** decided; every later phase follows this file.
**Sources reconciled:**
- **SMRITI plans on this branch:** [`SMRITI_MASTER_PLAN.md`](../SMRITI_MASTER_PLAN.md), [`BACKEND_PLAN.md`](BACKEND_PLAN.md), [`FRONTEND_PLAN.md`](FRONTEND_PLAN.md). Phases B0–B1 and F0–F1 ("Part 1") are built and green in CI; **Part 2 (B2 + the frontend revamp) was built on 2026-09-29** (records: BACKEND_PLAN §0.1 / Appendix B3, FRONTEND_PLAN §0.1 / Appendix B3).
- **"Final spec" documents** pushed to `main` on 2026-09-29, copied unchanged into [`docs/spec/`](spec/):
  - [`BACKEND_SPEC.md`](spec/BACKEND_SPEC.md) (NWIS backend blueprint);
  - [`FRONTEND_SPEC.md`](spec/FRONTEND_SPEC.md) (NWIS frontend blueprint, "crazy but professional");
  - [`TECH_STACK.md`](spec/TECH_STACK.md) (stack rationale).

## 1. The rule

1. **Build on the code that exists.**
   - B0/B1/F0/F1 are real, tested and CI-verified. Nothing is rewritten just to match the final spec's folder names or ID types.
   - The final spec's **features, screens, UI stack and design language are adopted** for every phase still to be built.
2. **The honesty principles stay non-negotiable.** These are master plan §2.2/§24 and FRONTEND_PLAN §3.2:
   - no citation, no claim;
   - unverified values dashed;
   - SYNTHETIC badge;
   - similarity ≠ probability;
   - advisory wording.

   The final spec asks for the same things: its guiding principles "Explainable" and "traceable to a source document", and its §11 NFR "every alert traceable… nothing from an LLM presented as ground truth".
3. **Every deviation from either document is written down here or in the phase plans, with the reason.** Nothing is dropped silently.

## 2. Backend: final-spec endpoint → implemented endpoint

All paths are under `/api/v1`. "✅" means built; the phase column says where the rest lands.

| Final spec (BACKEND_SPEC §4) | SMRITI endpoint | Phase |
|---|---|---|
| `POST /auth/login`, `POST /auth/refresh` | same paths | Part 5 (JWT) |
| `GET /auth/me` | `GET /me` | ✅ B0 (dev user); JWT user in Part 5 |
| `GET /wells`, `GET /wells/{id}` | same | ✅ B1; ✅ Well 360 enrichment B2 |
| `GET /wells/nearby-map?bbox=` | `GET /wells?bbox=` (+ `fluid_type=`) | ✅ B2 |
| `GET /wells/{id}/nearby?radius_km=` | `GET /wells/{id}/offsets?radius_km=&mode=SURFACE\|AT_FORMATION\|CLOSEST_APPROACH` | ✅ surface B1; ✅ other modes B2 |
| `GET /wells/{id}/formations` | tops inside `GET /wells/{id}`; dictionary at `GET /formations` | ✅ B1 |
| `POST /wells`, `PATCH /wells/{id}` | admin master-data edit | Part 6 (admin); import stays `app.cli seed` / `import_field` |
| `GET /wells/{id}/trajectory` | same | ✅ B1 |
| `GET /wells/{id}/trajectory/at-depth?md=` | same (`md_m=`) | ✅ B2 |
| `POST /wells/{id}/trajectory` | same (survey upload → minimum curvature) | ✅ B2 |
| `POST /documents/upload` | `POST /documents` | ✅ B1 |
| `GET /documents`, `/documents/{id}`, `/documents/{id}/pages/{n}` | same | ✅ B1 |
| `GET /documents/{id}/download` | `GET /documents/{id}/file` (streamed, same-origin: V-B12) | ✅ B1 |
| `POST /documents/{id}/reprocess` | same | ✅ B1 |
| `GET /events`, `GET /events/{id}`, `POST /events` | same | ✅ B2 |
| `PATCH /events/{id}/verify` | same + `GET /review-queue`, `POST /review-queue/{item_id}` | ✅ B2 |
| `GET /wells/{id}/events/timeline` | same | ✅ B2 |
| `POST /search` | `GET /search?q=&…filters` (GET, so result URLs can be shared) | ✅ B2 |
| `POST /search/ask` | `POST /copilot/chat` (SSE, read-only tools, cited) | Part 5 |
| `GET /correlation?well_ids=&formation=` | `GET /correlation?wells=&align=TVDSS\|FLATTEN_ON_TOP\|FORMATION_RELATIVE&top=` | ✅ B2 |
| `GET /correlation/formation-risk?formation=` | `GET /correlation/formation-stats` | ✅ B2 |
| — (SMRITI S7a) | `GET /wells/{id}/risk-profile` | B3 |
| — (SMRITI S8, USP 2) | `GET /ledger` | B3 |
| `POST /predictions/risk`, `GET /predictions/anomaly`, `GET /predictions/pattern-match`, `POST /predictions/retrain` | same paths | Part 4 |
| `GET /alerts`, `GET /alerts/{id}` | same | Part 4 |
| `PATCH /alerts/{id}/acknowledge`, `PATCH /alerts/{id}/dismiss` | `POST /alerts/{id}/ack`, `POST /alerts/{id}/dismiss`, plus `POST /alerts/{id}/feedback` | Part 4 |
| `GET /wells/{id}/parameters`, `…/parameters/latest` | same | Part 4 |
| `WS /ws/wells/{id}` | `WS /ws/wells/{id}/live` | Part 4 |
| `WS /ws/dashboard` | `WS /ws/alerts` (all alerts the user may see; this is the dashboard feed) | Part 4 |
| — (SMRITI) | `POST /replay`, `GET /reports/offset-brief/{well_id}` | Part 4 / Part 5 |

## 3. Data model differences (kept on purpose)

- **IDs:** the final spec uses UUIDs. We keep integer surrogate keys (BACKEND_PLAN §3.1); documents are also addressable by SHA-256. Changing key types would rewrite B1 for no user-visible gain.
- **Tables:** the final spec's `wells`, `well_trajectories`, `formations`, `document_pages` and `document_chunks` already exist as:
  - `well` + `wellbore`;
  - `survey_station` + `wellbore.path_geom`;
  - `formation` + `formation_top`;
  - `page` + `text_span`;
  - `chunk`.

  New tables follow master plan §6: `event`, `event_evidence`, `mitigation`, `casing_string`, `cement_job`, `mud_interval`, `ddr_operation`, `review_item`, real-time tables, `alert`, `alert_feedback`, `app_user`, `audit_log`, `ml_model`.
- **Oil / gas / water separation** (FRONTEND_SPEC §8):
  - Our `well.well_type` already means purpose (exploration / development / appraisal).
  - Fluid goes in a **new column `well.fluid_type`** (`oil | gas | water`), exposed by the API and used by the well-type switcher.
  - The synthetic field assigns fluids deterministically: mostly oil, some gas, a few water-injection/supply wells. **All synthetic.**
- **Event types:** the final spec's `mud_loss, kick, stuck_pipe, fishing, npt, torque_spike, overpressure, cementing_issue, other` map onto the master-plan taxonomy:
  - `LOSS, KICK, STUCK, FISH, OTHER_NPT/WAIT/EQUIP, TORQUE, OVERP, CEMENT, …`;
  - plus `TIGHT, INSTAB, BALLING, GAS, CASING`, which the final spec folds into `other`.
- **Severity:** final-spec `minor/moderate/severe` = our `low/medium/high`.
- **Well status:** final-spec `active` = our `drilling`.
- **Drilling parameters:** the final spec uses a wide hypertable (`drilling_parameters`); SMRITI uses a long table (`rt_sample`). B4 chooses and records the choice (ADR). Both are TimescaleDB hypertables with windowed queries only (final spec §11).

## 4. Backend stack substitutions

| Final spec | Built / to be built | Why |
|---|---|---|
| MinIO | SeaweedFS behind the S3 API (boto3) | MinIO's image was unpullable on 2026-09-28; plain S3 keeps it a configuration swap (ADR-B5) |
| Docling + PaddleOCR (+TrOCR) | PDFium text layer + Tesseract with table-rule removal | No PyTorch in the image; 86.3% mean OCR confidence and 100% well linking measured; swappable behind `app/ingest/pages.py` (ADR-B12) |
| LlamaIndex | Retrieval written directly in `app/search`: PostgreSQL full-text + pgvector + RRF + metadata filters + citations | Same capabilities with one less framework. LlamaIndex's PGVectorStore imposes its own table layout |
| BGE-M3 (1024-d) | Pluggable embedder with a `VECTOR(1024)` column: `ollama` provider serving `bge-m3`, or a deterministic `hash` provider (1024-d feature hashing) for CI/offline | BGE-M3 needs a model server; CI and air-gapped laptops still get working search. Recall is reported per provider |
| bge-reranker | Optional reranker endpoint; default off | Needs a GPU/model server; RRF alone is measured and reported |
| instructor / Outlines + spaCy | Rules-first extraction (regex + formation dictionary). Optional LLM pass via an OpenAI-compatible/Ollama endpoint with JSON-schema output + Pydantic validation + span grounding | Rules run everywhere, including CI; the LLM pass is measured separately when a model is available (master plan §13.1 ablation) |
| tsfresh | Hand-written rolling-window features (mean / std / slope / deviation from baseline) | The planned features are simple; tsfresh is heavy and slow |
| XGBoost/LightGBM + SHAP | Gradient-boosted trees with native TreeSHAP contributions (`pred_contrib`) | Same explanations without the `shap` package's numba/llvmlite stack; B4 records the final pick |
| PyOD, stumpy, tslearn | Used if they install cleanly under Python 3.11 + uv; otherwise NumPy implementations (ECOD, MASS, banded DTW) with tests | B4 records the decision |
| Kafka | Redis Streams | Both documents choose Redis Streams for the demo; Kafka stays the production path |
| Keycloak | Local JWT auth (`SMRITI_AUTH_MODE=jwt`) + RBAC + audit (Part 5); OIDC/Keycloak remains optional | A working login and role checks without running an identity server |
| MLflow, Prometheus/Grafana | Optional Compose profiles / metrics endpoint in hardening | Not needed to demo the product |

**Roles.** The final spec lists 4 roles (`field_engineer, office_engineer, admin, viewer`); the master plan §16 lists 6. We implement the master plan's 6 roles:
- `viewer`, `field_engineer`, `rtmac_engineer`, `drilling_engineer`, `data_steward`, `admin`.
- The final spec's `office_engineer` = `drilling_engineer` + `data_steward`.
- The permission matrix of BACKEND_SPEC §8 is applied through that mapping.

## 5. Frontend: adopted from FRONTEND_SPEC

**Libraries**
- Framer Motion (`motion`);
- **MapLibre GL** (replaces Leaflet: fly-to, clustering, pulse markers);
- react-three-fiber + drei (3D wellbore);
- Apache ECharts (live curves), D3 (correlation tracks);
- cmdk (⌘K palette);
- Zustand (UI-only state);
- self-hosted fonts via `@fontsource` (Inter + JetBrains Mono, CSP-safe).

Kept from the existing app: React/TS/Vite, Tailwind 4 + shadcn-style components, TanStack Query and the generated OpenAPI types.

**Design system**
- Themes: **Deep Rig** (dark, default), **Daylight Field** (light), **Command Blue**. Tokens are CSS variables and are never hard-coded in components.
- Well-type colours: oil `#FF6B35`, gas `#F2C94C`, water `#00B4D8`.
- Fixed z-index scale.
- The §7 anti-layout-glitch rules are **enforced**: transform/opacity only, `layout` for height, reserved space, stable keys.

**Screens:** the union of both documents.

| Page | Final spec | Master plan §10 | Part |
|---|---|---|---|
| Landing + Login | §4.1 | — | 6 |
| Dashboard | §4.2 | — | ✅ shell in 2, live in 5 |
| Map Explorer | §4.3 | 1 Well Map | ✅ MapLibre in 2, proximity modes in 3 |
| Well Detail (Overview / Trajectory 3D / Parameters / Events / Correlation / Documents) | §4.4 | 2 Well 360 | 3; Parameters tab in 5 |
| Correlation Panel | §4.4 tab | 3 | 3 |
| Knowledge Search + Ask | §4.5 | 6 | search in 3, Ask/copilot in 6 |
| Alerts Center + detail | §4.6 | 5 | 5 |
| Live Well Monitor | — | 4 | 5 |
| Mitigation Ledger (USP 2) | — | 7 | 4 |
| Documents Library + Review queue | §4.7 | 8 | ✅ revamp in 2, review queue in 3 |
| Analytics | — | 9 | 6 |
| Admin | — | 10 | 6 |
| System Status | — | supporting | ✅ F0 |

**Kept from SMRITI:**
- field ↔ office view;
- metric/oilfield units toggle;
- EvidenceLink / PageViewer on every fact;
- SYNTHETIC badge;
- strict same-origin CSP (MapLibre runs with its CSP worker build);
- the screen registry;
- no raw hex in components.

## 6. Delivery plan (replaces the "paused after Part 1" note)

| Part | Backend | Frontend |
|---|---|---|
| 2 ✅ | **B2** knowledge layer: extraction + DDR time log + review queue + events API; hybrid search + lessons cards; correlation (3 alignments + formation stats); at-formation and closest-approach offsets; Well 360 enrichment; `fluid_type` | Design-system revamp (themes, motion, collapsible sidebar, top bar with well-type switcher, ⌘K palette), MapLibre map, Documents Library revamp, Dashboard shell |
| 3 ✅ | **B3** offset prior risk, physics indicators, Mitigation Effectiveness Ledger (evaluated: `eval/results/`) | **F2** Well Detail (incl. 3D trajectory), Correlation Panel, Knowledge Search, Review queue, map proximity modes, axe checks |
| 4 | **B4** replay stream, real-time tables, rig state, classifiers, anomaly, Déjà Vu, alert engine, WebSockets | **F3** Mitigation Ledger, risk curves |
| 5 | **B5** copilot (SSE), Offset Risk Brief, analytics endpoints; JWT auth + RBAC + audit | **F4** Live Well Monitor, Alerts Center, Déjà Vu overlay, live dashboard |
| 6 | Hardening | **F5/F6** copilot panel, Analytics, Login/Landing, Admin, role-aware UI, PWA well pack |

**Verification**
- Database-backed behaviour (migrations, integration tests, seeded end-to-end tests) is verified in GitHub CI: the `integration` job builds the stack, seeds a synthetic field and runs pytest integration plus Playwright.
- Pure logic is verified by unit tests locally and in CI.
- The honesty rule applies unchanged: every "✅" cites a file and a test that passed.
