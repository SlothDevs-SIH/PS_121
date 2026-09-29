# SMRITI Backend — Master Plan & Build Record

**Team:** Slothdevs · **Solution:** SMRITI (working name) · **Problem Statement:** PS 121 — eRTMAC-NWIS (Oil India Limited)
**Parent document:** [`SMRITI_MASTER_PLAN.md`](../SMRITI_MASTER_PLAN.md). That is the product source of truth; **this** document is the source of truth for the backend. When the two disagree, fix both in the same PR.
**Document date:** 2026-09-28 (v1.0) · **updated 2026-09-28 (v1.1):** frontend F0 landed (V-B4 resolved); new `app.cli openapi` command exports the API contract for the frontend (+1 unit test → 31); CI jobs restructured (`backend-checks`, `frontend-checks`, `integration`).
**Updated 2026-09-29 (v1.2, Part 2):** B2 knowledge layer built on the contract drafted in `f621a3e` (data model, migrations 0005–0006, typed API); §0.2 (numbered §0.1 then), §5, §6, §13, §16 and Appendix B3 record it.
**Updated 2026-09-29 (v1.3, Part 3):** B3 batch intelligence built (offset prior risk, physics indicators, Mitigation Effectiveness Ledger) and evaluated; §0.1 (numbered §0.0 then), the log (V-B19–V-B24), §5, §6, §16 and Appendix B4 record it.
**Updated 2026-09-29 (v1.4, Part 4):** B4 real-time built (stream + replay + WITS0, rig state, classifiers, Déjà Vu, alert engine, WebSockets) and evaluated on SYNTHETIC data; §0.0, the log (V-B25–V-B31), §4.10–4.12, §5, §6, §10, §13 (ADR-B18–B20), §16 and Appendix B5 record it.
**Updated 2026-09-29 (v1.5, Part 5):** B5 built: copilot (rules planner, seven read-only tools, SSE), Offset Risk Brief PDF, analytics, and local JWT auth with RBAC and an append-only audit log (pulled forward from B6); §0.0, the log (V-B30 resolved, V-B32–V-B34), §4.13–4.15, §5, §6, §13 (ADR-B21–B23), §16 and Appendix B6 record it.
**Backend phase:** B0–B4 ✅ (Parts 1–4) · **B5 — Copilot & reports: ✅ COMPLETE (2026-09-29, Part 5)** with the copilot's held-out refusal rate below target (V-B34) and no MLflow profile (V-B29). Next: **B6 — Hardening** (Part 6).

> ⚠️ **Same honesty rule as the master plan and DHRUVA:** a "✅" must point to a file and a test that passed. Every number in §0 was measured in this repository on the date given. Everything from B6 onward is a **plan**.

---

## 0. Where the backend actually stands right now (2026-09-29)

### 0.0 B5 — Copilot, reports, analytics, local auth (built in Part 5, 2026-09-29)

**Everything is measured on the SYNTHETIC field.** The copilot's questions are generated from the synthetic truth, so its scores say it answers *our* records faithfully, not that it understands Oil India's.

**Built and verified** (evidence: Appendix B6):
- **Local auth, RBAC and audit** (`app/core/auth.py`, `users.py`, `audit.py`, migration `0010_auth_audit`):
  - `SMRITI_AUTH_MODE=dev` (default until the F6 login screen), `jwt` (built here) or `oidc` (B6, refused until then).
  - `jwt`: users in `app_user`, passwords hashed with scrypt from the standard library (`scrypt$N$r$p$salt$key`), HS256 tokens (PyJWT, issuer `smriti`, 8 h). The user is re-read from the database on every request, so a disabled account or changed role takes effect at once. A missing user still costs one scrypt check (no timing oracle). `python -m app.cli user-add` creates users.
  - Six roles map to nine permissions (viewer · field_engineer · rtmac_engineer · drilling_engineer · data_steward · admin). Every router needs `read_knowledge`; write and live routes add their own (`ingest`, `review`, `read_risk`, `read_live`, `act_alerts`, `control_replay`, `copilot`, `admin`). WebSockets take `?token=` and close 4401 / 4403.
  - `audit_log` is **append-only** (a trigger rejects UPDATE and DELETE). Logins (and failures), document views and downloads, uploads, review decisions, event creation and verification, alert actions, replay control, copilot queries and brief downloads are recorded with the request id. `GET /api/v1/admin/audit` pages it; `/admin/users` manages users.
- **S10 copilot** (`app/copilot/*`, `POST /api/v1/copilot/chat`, SSE or `?stream=false`):
  - Seven **read-only** tools over the built services (search, events, offset wells, risk profile, ledger, well summary, explain alert). Each tool checks the caller's permission and returns *facts*, each carrying its citations (a report page with its lines, or a database record).
  - The default engine is a **rules planner** (ADR-B21): it extracts wells, formations, event types, hole size, radius and alert ids, then picks tools by intent (handover, ledger, risk, offsets, events, well summary, search). Answers are templates filled from the facts with `[n]` markers, so every sentence traces to a citation.
  - It refuses plainly: an unknown well, an off-topic question, empty tool results, or a search whose best passage covers under half the question's content words ("No record found").
  - `SMRITI_COPILOT_ENGINE=llm` lets an OpenAI-compatible model choose the tools (tool outputs passed as delimited data). Its answer is checked: every `[n]` must exist and every number in a sentence must appear in the facts it cites; otherwise the rules answer is returned. Not evaluated (no model in this sandbox).
  - SSE events: `plan`, `tool` (one per call), `token`, `citations`, `done` (answer, refused, engine, intent, took_ms).
- **Offset Risk Brief** (`app/reports/brief.py`, `GET /api/v1/reports/offset-brief/{well_id}`, fpdf2, ADR-B22): 3 pages in about 0.2 s. It covers the well, its offsets within the radius (table plus a plan view with nearby pads clustered so labels don't collide), the offset prior risk per formation (with a chart and prognosed tops marked), what worked nearby from the ledger (with the observational caveat) and the report pages behind the numbers. "SYNTHETIC DATA - NOT OIL INDIA DATA" is watermarked on every page. **No HTTP route answers 501 any more.**
- **Analytics** (`app/analytics/service.py`): `GET /analytics/npt` (by event type, formation, year, well or field; events without recorded NPT are counted separately, never as zero), `GET /analytics/recurring` (same problem in the same formation across ≥ N wells, and repeats within a well, with event ids for click-through), `GET /analytics/alerts` (precision from the latest verdict per alert, with the ledger's Beta posterior and 90% interval; acknowledgement rate; median time to ack; alerts per 12 h of replayed data).
- **For F4:** `GET /alerts/{id}/dejavu` rebuilds the live 30 minutes behind a Déjà Vu match and the matched segment of the past run-up, as the matcher saw them. The integration test re-runs the matcher on the returned curves and gets the recorded similarity back. Fused alerts now keep each fused candidate's detail, so the match survives fusion. `GET /wells/{id}/realtime?end=` ends the window at an alert's data time.
- **Copilot evaluation** (`scripts/eval_copilot.py` → `eval/results/copilot_synthetic_2026-09-29.json`; 60 questions: 20 lookup, 15 aggregation, 5 ledger, 10 unanswerable, plus a held-out 5 answerable + 5 unanswerable written after the rules were fixed):
  - Lookup correct **1.0**; aggregation exact **1.0**; the ledger answer's top action matches the ledger **1.0** and is the planted best **1.0**.
  - Retrieval Recall@5 **0.45** on raw question text; **0.90** once the planner's well/formation/type filters are applied, which is what the copilot does (§13.3 target 0.85).
  - Citation faithfulness **1.0** over 216 citations (target 0.95); median latency about 19 ms, max 79 ms.
  - Correct refusal **1.0** on the 10 tuned questions but **0.6 on the 5 held-out**, so **13/15 = 0.87 combined, below the 0.90 target** (V-B34). The two misses: "rig cost per day on SYN-ASM-20" (a DDR passage mentions the well and the rig) and a cement-job question routed to cementing events by the word "cement". The held-out set was not used for tuning.
- **Tests:** unit 351 (auth 17, copilot 22, and the updated contract/phase tests); integration `test_b5_auth.py` (4), `test_b5_copilot.py` (5), `test_b5_reports.py` (5) and the Déjà Vu overlay test in `test_b4.py` (now 8).

**Found while building B5:**
1. **The search refused nothing.** Hybrid search always returns *something*, so questions about facts not in the records got confident, irrelevant quotes. The coverage rule (the best passage must cover ≥ 50% of the question's content words) fixed the tuned set; the held-out set shows it is not enough (V-B34).
2. **Planner routing order matters.** "Problems in the 12¼″ section of offset wells" first went to the offsets tool; asking about events now wins over listing offsets, and an unknown well name is checked before anything else (otherwise "SYN-ASM-99" got the generic off-topic refusal).
3. **fpdf2's core fonts are Latin-1.** Σ, ≥ and ¼ printed as "?"; text now passes through a substitution map.
4. **"Alerts per 12 h" from stored samples overstated the rate (18),** because a re-replay replaces a well's samples but keeps earlier alerts; data hours now come from every replay run's published rows (4.5).
5. **Fusion dropped the Déjà Vu match** from fused alerts' detail, so the overlay had nothing to draw; fused sources now keep their detail.

**Not built in B5 (stated, not hidden):** OIDC/Keycloak (B6; `jwt` covers local users); the MLflow profile (V-B29 stays open); an evaluated LLM engine (V-B33); a login screen (F6; `dev` stays the default so the app works without one).

### 0.1 B4 — Real-time (built in Part 4, 2026-09-29)

**Everything real-time here runs on SYNTHETIC data.** The 10-s drilling channels come from our own simulator (`app/synthetic/realtime.py`), which plants each problem type's precursor before the event. So every score below says the pipeline **recovers planted patterns**; none says how it will do on Assam wells (V-B26).

**Built and verified** (evidence: Appendix B5):
- **S12 stream** (`app/stream/*`, compose service `stream`, `python -m app.stream.run`):
  - Sources: CSV replay from object storage (the demo path, 1–2000× speed; pause, resume, stop and speed change while running) and a **WITS0 TCP reader** (tested byte by byte and over a real local socket). WITSML/ETP are not built (V-B27).
  - Every record goes through `channel_mapping` (source + mnemonic → canonical channel + unit; 24 defaults for CSV and WITS0 record 1, seeded). Missing, unreadable or LAS-null values are **flagged, not zeroed**.
  - Redis Streams `rt:{wellbore}` → consumer groups `persist` (batched, idempotent `INSERT … ON CONFLICT DO NOTHING` into the `rt_sample` hypertable) and `score` (writes `rt_score`, pushes frames to `scores:{wellbore}`, alerts to `alerts`). A heartbeat key drives the compose health check.
  - TimescaleDB hypertables `rt_sample`, `rt_score` (1-day chunks, compression after 7 days) are **wide**: one row per timestamp (ADR-B20).
- **Rig state** (`app/risk/rigstate.py`): rules state machine (drilling, reaming, circulating, trip in/out, in slips, stuck, stationary); stuck = overpull ≥ 150 kN over the running string weight, not moving or rotating, for 2 min.
- **S7b classifiers** (`app/risk/features.py`, `realtime_model.py`):
  - 16 features compare the last 2/5/15 min with the hour that ended 15 min earlier, in the same rig state.
  - One histogram gradient-boosted tree per type (LOSS, KICK, STUCK, TORQUE, OVERP, BALLING; scikit-learn, ADR-B18), target "the event starts within 30 min", isotonic calibration on grouped out-of-fold predictions, alert threshold set for ≤ 1 false alarm per 12 h of precursor-free drilling, top drivers by occlusion (not SHAP).
  - Trained on a separate synthetic training field (wells 61–180, 36,669 rows); the seeded wells are never in training. In the stream: 2 consecutive minutes above the threshold raise, below 0.8 × threshold clears.
- **S7d Déjà Vu** (`app/risk/dejavu.py`, `pattern_signature`): MASS (FFT sliding z-normalised distance) over each 90-min signature, the match ending within the last 40 min before the past event; banded DTW (10%) on the 20 best, on each channel's change from its first 5 min in typical-range units, normalised by how much both windows change; similarity = exp(−D/τ), τ calibrated so 1% of precursor-free windows reach 0.8. Own well excluded; hole-size class and drilling share must match. Library: the 99 real-time events of the seeded wells, each linked to its extracted event (for the report pages). NumPy implementation (ADR-B19).
- **Look-ahead** (`app/risk/prior.py`): a drilling well's formations below TD are **prognosed** from its offsets (inverse-distance-squared over the nearest five; weighted spread reported) so the risk profile covers what the bit has not reached. The stream raises LOOKAHEAD when the next formation is ≤ 30 m TVD away and an offset prior there is ≥ 30%.
- **S7c physics on the stream:** return-flow imbalance ≥ 5% over 2 min (hysteresis: 6 samples on, clear below 3%) and pit change ≥ 0.8 m³ in 15 min, using `ThresholdDetector` (V-B23 resolved).
- **S9 alert engine** (`app/alerts/engine.py`, `service.py`): pure rules over **data time**: no evidence → never raised (and `alert.evidence` has a CHECK constraint); same type within 30 m TVD → fused (another source) or dropped (same source); 30-min cooldown after ack/dismiss; ≤ 6 non-critical alerts per 12 h, **kicks exempt**. Evidence = the stream window plus offset/matched events with their report pages; recommendations = the ledger's top actions for that problem nearby, with the observational caveat; latency recorded per alert and per fused source. Lifecycle new → ack → dismissed; feedback useful / not useful / false alarm.
- **API:** `POST/GET /api/v1/replay`, `GET /api/v1/stream/status`, `GET /api/v1/wells/{id}/realtime` (downsampled window + scores + thresholds + stale flag), `GET /api/v1/alerts` (+ `/{id}`), `POST …/ack|dismiss|feedback`; **`WS /ws/wells/{id}/live`** (≤ 1 frame/s, status every 5 s with a stale flag after 30 s without frames) and **`WS /ws/alerts`** (full alert on create and fuse). Risk profile now reports TD (MD, TVDSS) and prognosed intervals.
- **Assets:** `python -m app.cli realtime` (also run by `seed`, 73 s) trains and stores the model bundle, builds the signature library, calibrates τ, and writes the drilling well's replay CSV (oilfield units, standard mnemonics) and its truth file.
- **Evaluations** (all SYNTHETIC; `eval/results/*_synthetic_2026-09-29.json`, commit `0ad33d4`):
  - **Classifiers** (`scripts/eval_realtime.py`), on the 40 seeded wells never seen in training (grouped 5-fold CV on the training field in brackets): PR-AUC LOSS **0.951** (0.957), KICK **1.000** (0.978), STUCK **0.907** (0.911), TORQUE **0.552** (0.532), OVERP **0.972** (0.986), BALLING **0.942** (0.968), against a one-feature physics threshold of 0.944 / 0.999 / 0.362 / 0.143 / 0.443 / 0.885. The ML gain is large for mechanical and overpressure precursors, **small for losses, kicks and balling**, where one flow or ROP feature already separates the planted signal. False alarms 0.09–1.28 per 12 h of precursor-free drilling (per minute-row, before hysteresis); every held-out event caught inside 30 min; median lead 30 min (the horizon's cap) except TORQUE 17 and STUCK 25.5. TORQUE stays weak (PR-AUC 0.55).
  - **Déjà Vu** (`scripts/eval_dejavu.py`), 123 held-out event queries: precision@1 **0.992** at the event start and **0.886** 15 min earlier, against 0.148 (random by type mix) and 0.415 (nearest by depth). An alert (similarity ≥ 0.8) fires for **46%** of queries at the event start (28% 15 min earlier), with **alert precision 1.0**. Out-of-sample false-match rate **1.25%** (4 of 320 precursor-free windows; target 1%). Per type, alert recall is high for BALLING, KICK, OVERP (1.0) and LOSS (0.83) and **low for STUCK 0.18, INSTAB 0.12, TIGHT 0.05, TORQUE 0** (V-B28). Query latency p50 101 ms, p95 138 ms on 99 signatures.
  - **End-to-end replay** (`scripts/eval_replay_alerts.py`, SYN-ASM-41 at 60×, 5.3 h of data in 327 s): **both planted events alerted, no false alerts.** Bit balling: a classifier alert **28 min** before it. Losses: the look-ahead **124 min** before (Tipam prognosed 30 m below the bit, offset prior 36%), then the classifier (26 min before), the physics pit-loss rule (17 min) and Déjà Vu (11 min) fused into the same alert, with 11 evidence items and 3 ledger recommendations. Alert latency (sample published → alert stored): **median 49 ms, max 185 ms** (5 measurements). An earlier run while model training saturated the CPU: same alerts, max **16.4 s**; and above ~900× publishing outruns scoring (the integration test at 1500× saw 4–7 s). One scenario on one well: this demonstrates the pipeline, it does not estimate detection rates (V-B26).
- **Tests:** unit 290 (new: rig state and simulator 6, Déjà Vu 6, mapping/replay 5, WITS0 3 incl. a real socket, alert engine 6 incl. a hypothesis property that no alert exists without evidence and kicks are never budgeted, scorer 3, contract/422 cases); integration `tests/integration/test_b4.py` (7): replay → every row stored and scored, planted losses alerted with evidence, budget/dedupe, both WebSockets push what the API lists, lifecycle rules (409s), replay control, phase registry. Passed on the 40-well field and on CI's 12-well field.

**Found while building B4:**
1. **LightGBM needs the system `libgomp`**, which the slim image lacks (and this sandbox can't apt-install). scikit-learn's histogram GBDT is the same algorithm and bundles its OpenMP (ADR-B18).
2. **Zero-padded smoothing invented precursors.** `np.convolve(mode="same")` pads with zeros, so every window's ends looked like a large drop; Déjà Vu alert recall went 0.09 → 0.49 once the edges were padded with the edge value.
3. **Two quiet windows look alike.** With plain z-normalised shapes, normal drilling matched normal drilling better than events matched events; comparing *changes* in typical-range units and dividing by how much both windows change fixed it.
4. **The simulator first produced no overpull precursors**, because connections are rare at low ROP; stick-slip torque and hookload scatter while drilling were added so the mechanical precursors are visible.
5. **CI's 12-well field put the next formation 306 m below TD**, unreachable in a demo; the replay now sizes ROP to reach the next formation in about 3.5 h and, if that is impossible, plants the losses after 4 h where the bit is (the truth file says which).

**Not built in B4 (stated, not hidden):** no Volve or other real real-time data (V-B25); no WITSML/ETP adapters (V-B27); no TIGHT/INSTAB classifier (Déjà Vu and the physics rules cover them, weakly; V-B28); no MLflow registry (the bundle is a versioned object in S3; V-B29); WebSockets are unauthenticated until B6 (V-B30); data-quality flags cover missing and unreadable values, not stale/flat-lined/unit-jump detection (V-B31).

### 0.2 B3 — Batch intelligence (built in Part 3, 2026-09-29)

**Built and verified** (evidence: Appendix B4):
- **S8 Mitigation Effectiveness Ledger** (`app/ledger/core.py`, `service.py`, `GET /api/v1/ledger`):
  - Outcome rule: a recorded success followed by the same problem in the same well within 50 m TVD and 24 h counts as *partial*; partial and fail count as not working; **unknown outcomes are never counted**, only reported.
  - Beta(1,1) posterior mean and 90% equal-tailed credible interval per action; **ranked only with n ≥ 3** (`min_n` 1–50); the rest are listed as insufficient evidence with their cases.
  - Severity strata, first-choice counts, median NPT and volume, and up to 25 cited cases per action (event, well, formation, recorded vs ledger outcome, report page).
  - Scopes: formation (name or synonym), basin, `well_id` + `radius_km`, severity. Every response carries the outcome rule and the observational caveat ("associated with, not proven to cause; confounding by severity").
- **S7a offset prior risk** (`app/risk/core.py`, `prior.py`, `GET /api/v1/wells/{id}/risk-profile`):
  - Weighted Beta-Binomial per formation × event type, as master plan §Stage 7a states it: w = exp(−d²/2σ²) × similarity × recency; P = (Σw·y + α)/(Σw + α + β); α + β = 2 from the basin base rate; n_eff = (Σw)²/Σw²; 90% credible interval.
  - Similarity 0.5–1.0: × 0.75 for another hole size, × 0.8 for another mud system, × 0.9 for another well type (unknown counts as a match). Recency 1.0 (V-B22).
  - Distances: AT_FORMATION (3D between the two wells' entry points into the formation, falling back to surface distance when an entry point is missing) or SURFACE. Planned wells are never offsets; **the subject well's own events are never used** and the basin base rates exclude it.
  - Base rate floored at 1% (V-B21). Labels read like the master plan's example: "Losses: 40% (17 of 40 offsets, n_eff 36.6, 90% CI 26%–55%)".
- **S7c physics indicators** (`app/physics/indicators.py`): d-exponent (Jorden & Shirley), dc-exponent, Eaton pore pressure (dc form, exponent 1.2), ECD, MSE (Teale), pit gain, flow imbalance, kick/loss rule flags (flow out, SPP, pit volume), drilling break, torque & drag deviation from a per-rig-state rolling baseline and from offsets' values, the increasing-overpull run, and a hysteresis threshold detector. Inputs in canonical SI, converted with `core.units` so the published oilfield constants apply unchanged. A library for now: B4 evaluates it on the stream (V-B23).
- **Cementing checklist** (`GET /api/v1/wells/{id}/cementing-check`): planned slurry density against the mud weights at which offsets lost circulation in the formation at the shoe, and the share of offsets that had losses while cementing there → low / medium / high with the reasons and the evidence events (V-B24).
- **Evaluations** (`scripts/eval_ledger.py`, `scripts/eval_risk_prior.py` → `eval/results/`, commit `bce0acb`, clean seed), both on **SYNTHETIC** data:
  - **Ledger vs planted success rates (master plan §13.7).** On the events and mitigations *extracted* from the seeded field (113 events, 165 mitigations, 17 action/event pairs with n ≥ 5): **Spearman ρ = 0.837** (0.858 with n ≥ 3); within an event type, 14 of 15 action pairs ordered as planted; the best action matches the planted best for 6 of 6 event types; the 90% intervals cover the planted rate for 24 of 24 pairs. Ranking by how often crews used an action (the baseline) gives ρ = −0.10.
  - **Scale check.** The same maths on generator truth for 10 independent fields of the same size (41 wells each, outside the seeded field): ρ from 0.43 to 0.83, **median 0.65, only 2 of 10 fields reach 0.8**; interval coverage 215 of 236 = **91.1%** (nominal 90%). Pooled over the 410 wells: ρ = 0.956. So the method converges, but at one field's worth of records **ρ ≥ 0.8 is met by this seed, not guaranteed** (V-B19).
  - **Offset prior, leave-one-well-out** (40 completed wells, 2,178 well × formation × event-type cells, 113 positive). Brier score: **served weighted estimate 0.0350**; unweighted fraction of offsets (the master plan's baseline) 0.0362; equal weights with the same basin prior 0.0361; formation frequency over the whole field 0.0366; basin base rate 0.0489. The paired bootstrap over wells puts every baseline's difference above zero (e.g. unweighted − weighted: 90% CI 0.0006–0.0018; the weighted estimate is better in 99.8% of resamples). The ablation shows the gain comes from **distance weighting**, not from the prior's smoothing. AT_FORMATION and SURFACE distances score the same here (difference CI straddles 0). σ = 2.5 / 5 / 10 km gives 0.0356 / 0.0350 / 0.0356; the default (radius/2) was fixed before this evaluation and not tuned.
- **Tests:** 42 new unit tests (`test_ledger_core.py` 8 incl. hypothesis, `test_risk_core.py` 6 incl. a shrinkage property, `test_physics.py` 13, contract/422 cases) and `tests/integration/test_b3.py` (8), which recomputes every number through an independent API path: ledger counts from `/events`, posteriors and weights from the listed offsets, base rates from well tops and events (proving the subject's own events are excluded), cementing evidence from `/events/{id}`.

**Found while building B3:**
1. **A Beta posterior's mean can fall outside its own 90% interval.** The shrinkage property test found it: a base rate near 0 gives α ≈ 0.01, and Beta(0.01, β) is so skewed that its mean exceeds its 95th percentile ("P = 0.3%, CI 0–0.1%"). A grid check showed it never happens for α, β ≥ 0.02, hence the 1% floor (V-B21).
2. The master plan lists torque & drag, drilling-break and SPP signatures among the S7c indicators; the first B3 cut had only the headline formulas. They were added with tests before B3 was marked built.

**Not built in B3 (stated, not hidden):**
- Intervals are formations; the 25 m TVDSS bins of §Stage 7a are not built (V-B20). Risk curves are drawn in F3.
- No `risk.recompute_prior` / `ledger.recompute` batch tasks: both are computed per request (26–51 ms on the synthetic field), so there is nothing to precompute yet (V-B22).
- The ledger stratifies by severity but does not adjust for it; confounding by severity is stated in every response, not corrected.

### 0.3 B2 — Knowledge layer (built in Part 2, 2026-09-29)

**Built and verified** (evidence: Appendix B3):
- **S2 extraction** (`app/extract/`), rules first, no LLM needed:
  - `rules.py`: units to SI, event type / subtype / severity, event parameters, 27 mitigation action codes, outcomes, NPT totals. Phrase lists are general drilling vocabulary.
  - `ddr.py`: the DDR time log. It survives OCR damage: punctuation between cells, lost decimals ("05" for 0.5 h, so hours come from the clock times), colons dropped from times, garbled Hrs cells, operations past midnight, and wrapped operation cells whose first line sits *above* the row (regrouped by vertical position).
  - `wcr.py`: casing + cement, mud programme, problem bullets. Each mitigation cites only the lines it spans. An unreadable cell ("YT", "ie)") becomes null with a reason; it is never guessed.
  - `service.py`: depth is voted across text, time-log column and header. TVD/TVDSS are interpolated from the survey, never extrapolated. Formation comes from the text (synonyms, longest match), else the header, else the tops (penalised).
  - Confidence = 0.95 for a text layer or the OCR line confidence, minus named penalties. Below `extract_confidence_threshold` (0.75) a **review item** records the reasons.
  - **One event told by several reports (DDR + WCR) is merged** and cites all of them. A per-well advisory lock stops concurrent workers from creating duplicates.
  - Re-extraction is idempotent and never undoes a human verification.
  - The task chain is ingest → extract → index; CLI `extract` and `index`.
- **Events and review API** (`app/extract/events_service.py`, `review_service.py`):
  - `/events` with every filter and a keyset cursor; `/events/{id}`.
  - Manual entry (evidence spans checked against the cited page); verify / reject.
  - `/wells/{id}/events/timeline`.
  - `/review-queue`: accept, validated correct (per-kind field whitelist; derived depths recomputed) or reject, with 409 on a second decision.
- **S5 search** (`app/search/`):
  - `hash` embedder (offline default, labelled in every response) or Ollama (BGE-M3).
  - Full text + pgvector fused with RRF (k = 60) after filters (well + radius, formation, event type, document type, dates).
  - **Relevance floor:** a lexical hit needs half the query's lexemes; a dense hit needs a minimum cosine (V-B14). Otherwise `no_record_found`.
  - Plain-text snippets with `[start, end)` highlights.
  - Template **lesson cards** grounded in each event's fields (advisory wording; a card never claims a success rate).
- **S6 correlation** (`app/correlation/service.py`): TVDSS / flatten-on-top / formation-relative panels with formation, casing-shoe, cement-top, mud and event tracks (all with evidence). Wells missing a needed top fall back to TVDSS and say why. Formation statistics.
- **S4 proximity** (`app/geo/proximity.py`, `trajectory_service.py`):
  - AT_FORMATION: 3D distance between PostGIS entry points.
  - CLOSEST_APPROACH: paths sampled every 5 m and refined at 0.25 m, optionally inside a TVDSS window.
  - Wells that can't be measured are listed in `excluded` with the reason.
  - Exact minimum-curvature **position at depth** (tangent slerp along the arc).
  - **Survey upload** recomputes the path, entry points and every derived TVDSS.
- **Well 360 enrichment** (`app/normalise/well360.py`): casing with cement, mud, event counts, recent events, document pipeline overview, lesson cards.
- **fluid_type** on the synthetic wells (own RNG stream: 29 oil / 8 gas / 5 water; nothing else changed); `/wells?bbox=&fluid_type=`.
- **Measured** (synthetic ground truth, `eval/results/extraction_synthetic_2026-09-29.json`, commit `9a74d62`, clean stack):
  - **Event P = R = F1 = 1.000** (113/113) on text-layer and OCR'd DDRs alike; event type, formation, date and resolved 100%.
  - Depth error mean 0.16 m (max 0.5 m); NPT error 0.
  - Mitigation action and outcome, in order, 100% (165/165).
  - Casing OD 95.8% (the misses are OCR-garbled cells, left null and sent to review); mud 100%.
  - **This is an upper bound** (V-B15): the synthetic reports use a fixed vocabulary.
  - Latency (best of 5, sandbox): search 24–27 ms; 6-well correlation panel 81–84 ms; `/events?limit=500` 29 ms; AT_FORMATION 18 ms; CLOSEST_APPROACH 0.6 s at 5 km (V-B18).
- **Tests:** **202 unit** (rules, parsers on text-layer and OCR-damaged text, search pieces, exact arc interpolation) and **25 integration**. The integration suite checks evidence spans against the page endpoint, and entry-point distances against independent at-depth positions. It also checks the invariant closest-approach ≤ entry-point distance, the review round trip with 409, and an idempotent survey upload. Ruff and strict mypy clean.

**Real bugs found and fixed while building B2:**
1. **Re-seeding deleted every extracted record.** Master import cleared and recreated each well's wellbore, and events, casing, mud and DDR lines cascade from it. The wellbore is now updated in place (`app/normalise/master_import.py`); extracted data survives a re-seed (verified).
2. **`seed --no-documents` wiped the report list from `truth.json`**, which the extraction eval needs. The list is now carried over.
3. **Write routes returned 201 without committing** (the request session doesn't auto-commit). Found by the integration test; every write route now commits.
4. **"Lost circulation" read as the action "circulate"**, and "Waited on" was missed as WAIT. Both patterns were fixed with unit tests.

**Not done in B2, stated plainly:**
- **No LLM extraction pass.** `extract_llm_enabled` exists but the rules reached F1 1.0 on synthetic reports; the pass is needed for real reports (V-B17).
- **No hand-annotated gold set and no search Recall@5.** Only synthetic ground truth exists; both need real reports (V-B15).
- **Kick subtype** (gas / water / oil) is never written in the synthetic reports, so it stays null. That is the 8% subtype "miss".

### 0.4 B1 — Data foundation (built in Part 1, 2026-09-28)

**Built and verified** (evidence: Appendix B2):
- **Synthetic Upper-Assam-style field** (`app/synthetic/`), seeded and deterministic:
  - 42 wells: 40 completed, 1 drilling (for the Part 4 replay), 1 planned.
  - J, S and vertical profiles, with minimum-curvature surveys.
  - 251 formation tops across 9 formations.
  - Casing and mud programmes.
  - 113 drilling events with mitigations and outcomes drawn from **planted success rates** (the ground truth for the Part 3 ledger).
  - **191 PDF reports** (151 DDRs, 40 WCRs), 30% "scanned" as image-only.
  - The reports vary like a real archive: well-name aliases, formation synonyms, metric and oilfield units, varied phrasing, and a SYNTHETIC watermark on every page.
  - Re-rendering is byte-identical, so re-seeding is idempotent (0 new documents on a second run, verified).
  - Ground truth is written to `s3://smriti-raw/synthetic/truth.json`.
- **Ingestion (S1):**
  - Upload with magic-byte type check, a 50 MB limit and SHA-256 de-duplication.
  - The PDF text layer is read with PDFium, with line bounding boxes; image-only pages are OCR'd with **Tesseract after table-rule removal**.
  - Page PNGs go to object storage; text spans carry normalised bounding boxes.
  - Section-aware chunks.
  - Document classification, well-name and report-date parsing; well linking through alias normalisation, with trigram near-matches queued as `alias_candidate`.
  - A `needs_review` status for unlinked wells or low OCR confidence.
  - An idempotent Celery task with transient-error retries.
- **Master data (S3) and trajectories (S4):**
  - Idempotent import; TVDSS on every station and top.
  - 3D `LINESTRING Z` wellbore paths and formation entry points in UTM 46N.
  - Surface radius search on a GiST index (other proximity modes → B2).
- **API:**
  - `/wells`, `/wells/{id}`, `/wells/{id}/trajectory`, `/wells/{id}/offsets`, `/formations`.
  - `/documents` (upload + list), `/documents/{id}`, `…/pages/{n}` (spans + bounding boxes), `…/pages/{n}/image`, `…/file`, `…/reprocess`.
  - A data-quality score per well.
- **CLI:** `seed` (generate → import → render → ingest, with `--inline` / `--wait`).
- **Measured results:**
  - 191/191 reports processed; 191/191 linked to the right well (including OCR'd and aliased names).
  - Mean OCR confidence 86.3% across 65 OCR'd pages (lowest page 69.6%).
  - 3,838 text spans and 765 chunks.
  - Full seed with inline OCR takes 3 min 26 s on the sandbox CPU.
  - Offset query on **10,000 wells: p50 2.9 ms, p95 14.6 ms** (target < 500 ms; `scripts/perf_offsets.py`).
- **Tests:**
  - **58 unit tests**, including exact closed-form minimum-curvature tests and ingestion-rule tests.
  - **11 integration tests** against the live stack. Among them: offsets checked against an independent haversine distance, and the full upload → worker → evidence round trip.
  - Ruff and strict mypy clean; `alembic check` clean.

**Real bugs found and fixed while building B1** (kept for the record, as DHRUVA's doc does):
1. **SeaweedFS could only store one bucket.** With its defaults (30 GB volumes, slots sized from free disk), the first bucket took every slot, so page images failed with "no free volumes". B0 only ever wrote to one bucket, so it passed. Fixed with 512 MB volumes and 64 slots (`infra/seaweedfs/entrypoint.sh`).
2. **OCR read table rules as characters and dropped whole rows.** Fixed by erasing long horizontal and vertical dark runs before OCR (`app/ingest/imageprep.py`); the scanned table then read perfectly.
3. **OCR artefacts broke well-name parsing** ("SYN ASM 02_"). Stray `_|~` are now stripped from OCR words.
4. **Completion reports took the spud date as their report date.** "Spud date:" matched the generic "Date:" rule; a completion report is now dated by its completion date.
5. **Two reports for the same well and day shared a filename**, so one silently overwrote the other (191 generated, 190 ingested). The report number is now in the filename.
6. **Synthetic PDFs embedded the current time**, so re-seeding would re-ingest everything. Creation dates are now fixed.

**Not done in B1, stated plainly:**
- **No Volve data.** Downloading it needs registration, which isn't possible here. B1's "50+ Volve DDRs" criterion was met with 151 synthetic DDRs + 40 WCRs instead; Volve remains the plan for real data.
- **No LLM classification fallback.** Rules classify every synthetic report correctly; the LLM hook moves to B2 with extraction.
- **No at-formation or closest-approach offset modes** (B2, as planned).

### 0.5 B0 — Skeleton (built earlier on 2026-09-28)

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
| V-B9 | OCR stack differs from the master plan (Docling + PaddleOCR) | Both pull in PyTorch-scale dependencies. PDFium (text layer + boxes) + Tesseract 5 (with our table-rule removal) met the need at 86% mean OCR confidence on the synthetic scans | ADR-B12. Re-evaluate Docling/PaddleOCR against real OIL scans; the page-extraction interface (`app/ingest/pages.py`) is the only thing to swap | ✅ Decided |
| V-B10 | Debian package mirrors are blocked in this development sandbox | Tesseract can't be apt-installed into the image here | `ARG WITH_OCR` (default `true`; CI builds with OCR). Sandbox images build with `WITH_OCR=false` and OCR ran on the host; the containerised OCR path is proven by CI | ✅ Resolved |
| V-B11 | Migration order changed from the plan | `document.well_id` references `well`, so master data must come first | Now `0002_master_data`, `0003_documents`, `0004_trajectory` (§8) | ✅ Resolved |
| V-B12 | Page images are streamed through the API, not by pre-signed URLs | The S3 endpoint (`s3:8333`) isn't reachable from browsers, and same-origin images keep the CSP strict | `GET /documents/{id}/pages/{n}/image` | ✅ Decided |
| V-B13 | Synthetic data only | No Volve access in the sandbox | Master plan §12.5 is unchanged; OIL/Volve data goes through the same `import_field` + upload path | ⏳ Open |
| V-B14 | Dense relevance floor for the `hash` embedder | Short queries against ~1,000-character chunks score low even when relevant. Measured on the synthetic corpus: 13 queries; relevant top-1 ≥ 0.31 for 7 of 8 (0.09 for "high torque", found lexically); irrelevant top-1 ≤ 0.154 | Floor 0.22 for `hash`, 0.45 for `ollama` (`app/search/hybrid.py`). Re-calibrate on real reports and when switching embedder | ✅ Calibrated (synthetic) |
| V-B15 | Extraction F1 measured on synthetic reports, not the master plan §13.1 gold set | The generator's phrasing is a fixed vocabulary, so 1.0 is an upper bound | Quote it only as "on synthetic reports". Build the gold set from review-queue corrections (the `(proposed, correction)` pairs are stored for this) plus annotated real DDRs | ⏳ Open |
| V-B16 | Wellbore recreation on re-seed cascaded away extracted data | Found while building B2 | Fixed: update in place (§0.3 bug 1) | ✅ Resolved |
| V-B17 | LLM extraction pass not built | Rules suffice on synthetic reports | Build it when real reports show the rules' misses; the review queue measures them | ⏳ Open |
| V-B18 | CLOSEST_APPROACH takes ~0.6 s at 5 km (20 candidate wells, numpy sampling) | Acceptable for an interactive request | If slow on real fields: sample only inside the window's bounding box, or pre-filter with `ST_3DDistance` per pair in SQL | ⏳ Watch |
| V-B19 | Ledger ρ ≥ 0.8 is sample-size-limited | Seeded field ρ = 0.837, but 10 same-size fields give median 0.65 (2 of 10 ≥ 0.8); 410 wells give 0.956 | Quote the seeded number **with** the scale check. Real value depends on how many recorded outcomes OIL's archive yields; the credible intervals already show the uncertainty to users | ⏳ Stated |
| V-B20 | Risk intervals are formations, not 25 m TVDSS bins | §Stage 7a allows either; formations are what offsets share reliably | Add TVDSS bins inside thick formations if F3's risk curves need finer steps | ⏳ Open |
| V-B21 | Base rate floored at 1% (not the raw rate) | Keeps α, β ≥ 0.02 so the posterior mean stays inside its own 90% interval (property test + grid check) | A never-seen event type starts at a 1% prior; documented in the response's `method` text | ✅ Decided |
| V-B22 | Recency factor fixed at 1.0; no batch recompute tasks | Synthetic wells span 2008–2027 with no practice change to model; per-request computation is 26–51 ms | Add a decay once real data shows practices changing; add Celery recompute only if requests get slow | ✅ Decided |
| V-B23 | Physics indicators not yet on a live stream | They are pure functions with textbook tests; B4 brings the stream | Done in B4: flow imbalance and pit change run on the stream with hysteresis and raise PHYSICS alerts | ✅ Resolved 2026-09-29 |
| V-B24 | Cementing checklist uses offset loss mud weights as the fracture-gradient evidence | No LOT/FIT or fracture-gradient data in the synthetic field; centraliser/standoff/excess checks need data we don't extract | Advisory flags only; add FG/LOT and job-design checks when those fields are extracted | ⚠️ Limited |
| V-B25 | B4 exit criterion names "a Volve well"; only the synthetic drilling well was replayed | No Volve access in the sandbox (V-B13) | The CSV replay and channel mapping take any well log with a TIME column; replay a Volve well when the data is available | ⏳ Open |
| V-B26 | Real-time models trained and scored on planted synthetic precursors | No real 10-s drilling data here | Every number is quoted as "recovers planted patterns". Retrain on OIL/Volve real-time data with labels from extracted events (the pipeline and grouped CV are ready) | ⚠️ Stated |
| V-B27 | WITSML 1.4.1.x and ETP adapters not built | WITS0 and CSV cover the demo and many rigs; WITSML needs a store to test against | Add when OIL confirms its eRTMAC feed (the publisher takes any record source) | ⏳ Open |
| V-B28 | Weak on TIGHT/TORQUE/INSTAB/STUCK pattern matching | Déjà Vu alert recall 0–0.18 for these; TORQUE classifier PR-AUC 0.55 | Mechanical precursors are spiky and shape-poor at 30-s resolution; the STUCK classifier (0.91) carries stuck pipe. Revisit with real torque/hookload data (a torque-oscillation channel was tried and reverted: it fitted our own simulator) | ⚠️ Stated |
| V-B29 | Model bundle in S3, not an MLflow registry | One versioned artefact (`models/realtime/rt-hgb-v1.joblib` + metrics JSON) is enough for one model family | MLflow profile in B5 as planned | ⏳ B5 |
| V-B30 | WebSockets unauthenticated | Dev auth everywhere until B6 | B5: in `jwt` mode the token goes in `?token=` (browsers can't set WebSocket headers), `read_live` required, closes 4401/4403 (`routes/ws.py`, integration `test_b5_auth.py`) | ✅ Resolved 2026-09-29 (jwt mode) |
| V-B31 | Stream data-quality flags limited to missing / unreadable / unmapped | Stale, flat-lined and unit-jump detection not built | The live view already flags a stale stream; add per-channel checks with the Live Monitor (F4) | ⏳ Open |
| V-B32 | Local JWT auth, not OIDC | No Keycloak in this sandbox; the roles, permissions, audit log and WebSocket rules are the same either way | `oidc` mode (validate the IdP's tokens, map realm roles) in B6; `dev` stays the default until the F6 login screen | ⏳ B6 |
| V-B33 | LLM copilot engine not evaluated | No model server here; the rules engine is the default and is what the numbers measure | Extend `scripts/eval_copilot.py` (rules-only today) to the LLM engine and run it against OIL's approved model; its answers are already checked for citations and numbers, with a rules fallback | ⏳ Open |
| V-B34 | Copilot correct-refusal below target on held-out questions | 1.0 on the 10 tuned, 0.6 on the 5 held-out (13/15 = 0.87 vs 0.90) | Not tuned on the held-out set. Needs a question classifier or an entailment check between question and passage; re-measure on real questions from engineers | ⚠️ Stated |

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

> **As built (Part 4):** CSV replay + WITS0 reader, `channel_mapping`, wide `rt_sample`/`rt_score` hypertables (no separate `rig_state` table: the state is a column of `rt_score`), `MAXLEN ~20k` per wellbore stream, `GET /stream/status`. WITSML/ETP not built (V-B27); data-quality flags limited (V-B31). See §0.0.

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

> **As built (Part 4):** scikit-learn histogram GBDT instead of LightGBM (ADR-B18), bundle in S3 instead of MLflow (V-B29), occlusion drivers instead of SHAP, scoring every minute of data; Déjà Vu in NumPy (ADR-B19) every 3 min of data, 2 consecutive hits. The designed tests below exist (`test_dejavu.py`, `test_scorer.py`); the latency target is met with room (0.10 s p50 per Déjà Vu query, 14 ms per classifier cycle). See §0.0.

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

> **As built (Part 4):** every rule below, over data time; budget = 6 non-critical per rolling 12 h (the "per shift" of the design); lifecycle new → ack → dismissed (actioned/closed are in the schema, not yet exposed). See §0.0.

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

### 4.13 `copilot` — S10 (B5) — ✅ built: see §0.0 (a rules planner by default, ADR-B21)

- **Responsibilities:** an LLM agent with the fixed read-only tools of master plan §Stage 10, each tool calling a service function (never SQL). SSE token streaming. Answers must cite; the prompt-injection defence treats tool outputs as delimited data.
- **Endpoint:** `POST /api/v1/copilot/chat` (SSE).
- **Tests:** the tool-call contract per tool; "no record found" for empty tool results; a document containing an injected instruction is not followed (a red-team fixture).

### 4.14 Reports (B5) — ✅ built with fpdf2, not WeasyPrint (ADR-B22): see §0.0

`GET /api/v1/reports/offset-brief/{well_id}` renders HTML with a Jinja2 template and converts it to PDF with WeasyPrint. The brief contains the map snapshot, the offsets table, the risk-by-depth chart (server-side SVG) and citations.

### 4.15 Auth, RBAC, audit (B6) — RBAC, audit and local JWT built early in B5 (ADR-B23, §0.0); OIDC remains B6

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
| 6 | Full §8 API contract mounted (501 + phase) | B0 | ✅ | `app/api/v1/routes/*` · `test_openapi_contains_every_planned_endpoint`, 501 tests for the B5 routes (the B0 WebSocket 501 tests were replaced by B4's live tests) |
| 7 | `/api/v1/meta`, `/api/v1/me`, component registry | B0 | ✅ | `routes/system.py`, `core/phases.py` · `test_meta_auth.py` (5) |
| 8 | Dev auth with prod refusal | B0 | ✅ (local JWT added in B5, row 27b) | `app/core/auth.py` · `test_auth_refuses_unconfigured_modes` |
| 9 | Unit conversions (Appendix D) | B0 | ✅ | `app/core/units.py` · `test_units.py` (3, incl. hypothesis) |
| 10 | SQLAlchemy engine/session + Base naming convention | B0 | ✅ | `app/db/session.py`, `app/db/base.py` |
| 11 | Alembic + migration `0001` (extensions) | B0 | ✅ | `app/db/migrations/versions/0001_extensions.py` · integration `test_required_extensions_installed_and_migration_at_head` |
| 12 | S3 client + bucket bootstrap | B0 | ✅ | `app/storage/s3.py` · integration `test_object_storage_round_trip` |
| 13 | Celery app + `system.ping` + worker health check | B0 | ✅ | `app/workers/celery_app.py` · integration `test_celery_worker_round_trip`, compose health check |
| 14 | CLI `bootstrap` (idempotent) / `check --worker` / `openapi` (contract export, added with F0) | B0 | ✅ | `app/cli.py` · run twice (Appendix B); `tests/unit/test_cli.py` |
| 15 | Dockerfile (non-root, health check, `PYTHON_IMAGE` arg) | B0 | ✅ | `backend/Dockerfile` |
| 16 | docker-compose (6 services, health-gated startup) | B0 | ✅ | `docker-compose.yml` · `docker compose up -d --wait` all healthy |
| 17 | CI workflow (checks + compose integration) | B0 | ✅ | `.github/workflows/ci.yml` · [run #1](https://github.com/SlothDevs-SIH/PS_121/actions/runs/36460112777) green |
| 18 | S1 ingestion (upload, PDFium text layer, Tesseract OCR + rule removal, spans/bbox, page images, chunks, classification, well linking, Celery task) | B1 | ✅ | `app/ingest/*` · `test_ingest_rules.py` (19), integration `test_upload_process_and_page_evidence` |
| 19 | S3 normalisation + master data tables (import, TVDSS, formations, alias resolution, data-quality score) | B1 | ✅ | `app/normalise/*`, migrations 0002–0004 · integration `test_trajectory_and_well_detail` |
| 20 | S4 min-curvature + surface offsets | B1 | ✅ | `app/geo/*` · `test_mincurv.py` (8, closed-form), integration `test_surface_offsets_match_independent_distance`, `scripts/perf_offsets.py` |
| 21 | S4 at-formation + closest-approach, position at depth, survey upload | B2 | ✅ | `app/geo/proximity.py`, `trajectory_service.py`, `mincurv.interpolate_at_md` · `test_mincurv.py` (arc-exact interpolation), integration `test_at_formation_matches_independent_positions_and_bounds_closest_approach`, `test_trajectory_at_depth_and_idempotent_survey_upload` |
| 22 | S2 extraction + review queue + DDR parser | B2 | ✅ | `app/extract/*` · `test_extract_rules.py` (51), `test_extract_parsers.py` (8), integration `test_review_queue_accept_then_conflict`; `eval/results/extraction_synthetic_2026-09-29.json` |
| 23 | S5 search + lessons cards | B2 | ✅ | `app/search/*` · `test_search_units.py` (6), integration `test_hybrid_search_cites_passages_and_says_when_nothing_is_found` |
| 24 | S6 correlation + formation stats | B2 | ✅ | `app/correlation/service.py` · integration `test_correlation_alignments`, `test_formation_stats` |
| 24a | Events API (filters, cursor, manual entry, verify/reject, timeline) | B2 | ✅ | `app/extract/events_service.py` · integration `test_event_cursor_pages_cover_the_list_once_in_order`, `test_manual_event_verify_and_reject`, `test_timeline_counts_and_npt_lines` |
| 24b | Well 360 enrichment, `fluid_type`, map bbox filter | B2 | ✅ | `app/normalise/well360.py` · integration `test_well_360_enrichment`, `test_well_detail_and_offsets_have_b2_fields` |
| 25 | S8 Mitigation Effectiveness Ledger | B3 | ✅ | `app/ledger/*`, `routes/knowledge.py` · `test_ledger_core.py` (8), integration `test_ledger_recounts_from_the_events_api`, `test_ledger_rates_ranking_and_cases`, `test_ledger_scopes`; `eval/results/ledger_synthetic_2026-09-29.json` |
| 25a | S7a offset prior risk | B3 | ✅ | `app/risk/*`, `routes/wells.py` · `test_risk_core.py` (6), integration `test_risk_profile_recomputes_from_its_offsets_and_excludes_the_subject`, `test_base_rates_exclude_the_subject_well`, `test_risk_profile_modes_and_planned_well`; `eval/results/risk_prior_synthetic_2026-09-29.json` |
| 25b | S7c physics indicators + cementing checklist | B3 | ✅ (live on the stream since B4, row 25b′) | `app/physics/indicators.py` · `test_physics.py` (13), integration `test_cementing_check_reads_offsets_in_the_shoe_formation` |
| 25b′ | S7c physics on the stream (imbalance, pit change) | B4 | ✅ | `app/stream/scorer.py` · `test_scorer.py` (3) |
| 26 | S12 stream: CSV replay + WITS0, channel mapping, persist/score groups, `stream` service | B4 | ⚠️ no WITSML/ETP (V-B27) | `app/stream/*`, migration 0007 · `test_stream_mapping.py` (5), `test_wits0.py` (3), integration `test_every_row_is_stored_and_scored`, `test_replay_control_rules` |
| 26a | Rig state + S7b classifiers | B4 | ⚠️ synthetic training only (V-B26) | `app/risk/rigstate.py`, `features.py`, `realtime_model.py` · `test_realtime_foundation.py` (6); `eval/results/realtime_synthetic_2026-09-29.json` |
| 26b | S7d Déjà Vu | B4 | ⚠️ weak on mechanical types (V-B28) | `app/risk/dejavu.py`, migration 0008 · `test_dejavu.py` (6); `eval/results/dejavu_synthetic_2026-09-29.json` |
| 26c | S9 alert engine + lifecycle + feedback | B4 | ✅ | `app/alerts/*`, migration 0009 · `test_alert_engine.py` (6 incl. property), integration `test_planted_losses_are_alerted_with_evidence`, `test_budget_and_dedupe_hold`, `test_alert_lifecycle`; `eval/results/replay_alerts_synthetic_2026-09-29.json` |
| 26d | WebSockets `/ws/wells/{id}/live`, `/ws/alerts` | B4 | ⚠️ unauthenticated until B6 (V-B30) | `app/api/v1/routes/ws.py` · integration `test_websockets_pushed_frames_and_alerts`, e2e `smoke.spec.ts` (through nginx) |
| 26e | Look-ahead: prognosed tops below a drilling well's TD | B4 | ✅ | `app/risk/prior.py` · `test_stream_mapping.py::test_prognosed_top_weights_near_offsets`, `test_scorer.py` |
| 27 | S10 copilot (rules planner, 7 read-only tools, SSE, optional LLM engine) | B5 | ⚠️ refusal 0.87 < 0.90 (V-B34); LLM engine not evaluated (V-B33) | `app/copilot/*` · `test_copilot.py` (22), integration `test_b5_copilot.py` (5); `eval/results/copilot_synthetic_2026-09-29.json` |
| 27a | Offset Risk Brief PDF + analytics (NPT, recurring, alert quality) | B5 | ✅ | `app/reports/brief.py`, `app/analytics/service.py` · integration `test_b5_reports.py` (5), `test_stack.py::test_built_endpoint_through_real_server` |
| 27b | Local JWT auth, RBAC (6 roles, 9 permissions), append-only audit log, WS token | B5 | ⚠️ OIDC in B6 (V-B32) | `app/core/auth.py`, `users.py`, `audit.py`, migration 0010 · `test_auth.py` (17), integration `test_b5_auth.py` (4) |
| 27c | Alert Déjà Vu overlay + window by end time (for F4) | B5 | ✅ | `app/alerts/overlay.py` · integration `test_b4.py::test_alert_evidence_windows_and_dejavu_overlay` |
| 28 | OIDC, digests pinned, perf & security hardening | B6 | 📋 | §4.15, §12 |
| 29 | Synthetic field generator + `seed` CLI (ground truth for later phases) | B1 | ✅ | `app/synthetic/*`, `app/cli.py seed` · determinism check (byte-identical re-render), re-seed = 0 new documents |

---

## 6. Phase Plan (backend)

Backend phases map onto master plan §18 (P0–P5). Durations assume ~7 weeks to finale-ready; compress proportionally once V4 (deadlines) is known.

| Phase | Master plan | When | Scope | Exit criteria (all must be true) |
|---|---|---|---|---|
| **B0 Skeleton** | P0 | Days 1–3 | Platform, Compose, migrations, CI, API contract | ✅ **Met 2026-09-28**, including a green GitHub CI run — see Appendix B |
| **B1 Data foundation** | P1 | W1–W2 | S1 ingestion; S3 master data & datums; S4 min-curvature + surface offsets; migrations 0002–0004; OCR worker image | ✅ **Met 2026-09-28** with one substitution: 151 synthetic DDRs + 40 WCRs (58 DDRs and 7 WCRs scanned) instead of Volve DDRs (V-B13). Endpoints return real data; min-curvature closed-form tests pass; offsets p95 14.6 ms on 10k wells. See §0.4 and Appendix B2 |
| **B2 Knowledge layer** | P2 | W2–W3 | S2 extraction + review queue + DDR parser; S5 search; S6 correlation; S4 other proximity modes; LLM service; migrations 0005–0006 | ✅ **Met 2026-09-29 (Part 2) with two gaps stated:** event F1 measured and saved, but on synthetic ground truth, not a gold set (V-B15); search Recall@5 **not measured** (needs labelled queries on real reports); correlation JSON for all 3 modes ✅; review round trip ✅. LLM pass deferred (V-B17). See §0.3 and Appendix B3 |
| **B3 Batch intelligence** | P3 (first half) | W3–W4 | S7a prior, S7c physics, S8 ledger | ✅ **Met 2026-09-29 (Part 3):** risk-profile endpoint live and beating every baseline on leave-one-well-out Brier; physics formula tests pass; ledger ρ = 0.837 on the seeded field (≥ 0.8), **with the caveat that same-size fields give a median of 0.65** (V-B19). See §0.2 and Appendix B4 |
| **B4 Real-time** | P3 (second half) | W4–W5 | S12 stream + replay; rig state; S7b scoring; S7d Déjà Vu; S9 alerts; WebSockets; migrations 0007–0009 | ✅ **Met 2026-09-29 (Part 4) for the synthetic well only:** the replay raises the planted alerts over the WebSocket (integration + 60× eval); alert latency max 185 ms at 60× on a quiet machine (16.4 s once under full CPU load: the p95 ≤ 5 s target holds only with CPU headroom and below ~900×); every alert has evidence (hypothesis property test + DB constraint). **Not met: no Volve well replayed** (V-B25). See §0.1 and Appendix B5 |
| **B5 Copilot & reports** | P4 | W5–W6 | S10 copilot (SSE); Offset Risk Brief PDF; MLflow profile | ✅ **Met 2026-09-29 (Part 5) with gaps stated:** a 60-question set answered with citations measured (faithfulness 1.0 on 216 citations); refusal rate measured (0.87 combined, **below the 0.90 target**, V-B34); the PDF renders (3 pages, integration-tested). Local JWT auth, RBAC and the audit log were pulled forward from B6. **Not met: MLflow profile** (V-B29). See §0.0 and Appendix B6 |
| **B6 Hardening** | P5 | W6–W7 | OIDC/RBAC/audit; image digests pinned; Prometheus metrics + Grafana; load test; security review; backups script | All master plan §9 targets measured and recorded in `eval/results/`; `SMRITI_AUTH_MODE=oidc` works end-to-end; no critical findings open |

### 6.1 B1 task breakdown — ✅ all done 2026-09-28 (items 3 and 5 changed: see V-B9, V-B12)

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
| `SMRITI_MAX_UPLOAD_MB` | `50` | B1 | Per-file upload limit (413 above it) |
| `SMRITI_OCR_NEEDS_REVIEW_BELOW` | `60.0` | B1 | Mean OCR confidence (0–100) below which a document goes to `needs_review` |
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
| `0002_master_data` ✅ | B1 | `field`, `formation`, `well`, `wellbore` (with `path_geom`), `formation_top` (with `entry_point`) |
| `0003_documents` ✅ | B1 | `document`, `page`, `text_span`, `chunk` (no embedding yet), `alias_candidate` |
| `0004_trajectory` ✅ | B1 | `survey_station`; GiST indexes on `well.surface_loc`, `wellbore.path_geom`, `formation_top.entry_point`; trigram index on `well.canonical_name` |
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

## 10. Real-Time Pipeline (B4 design; built in Part 4)

> **As built:** the diagram holds with these changes: adapters = CSV replay and WITS0; samples are wide rows (one per timestamp, ADR-B20), idempotent on (wellbore_id, ts); classifiers every minute of data and Déjà Vu every 3 min of data (the design's 10–30 s would recompute near-identical features); look-ahead every minute. Backpressure skipping is **not** built: at 60× the consumer keeps up (≈ 90 samples/s scored on one core), and the live view shows a stale flag instead.

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
| ADR-B6 | ~~Separate OCR/LLM worker image (B1)~~ **One image, OCR optional (`WITH_OCR`)** — revised 2026-09-28 | Separate worker image | With Tesseract instead of Docling/PaddleOCR/torch (ADR-B12), OCR adds tens of MB, not GBs; one image is simpler. An LLM worker image is still planned for B2 |
| ADR-B7 | One PostgreSQL with extensions | Separate vector/time-series/graph stores | Master plan ADR; fewer systems; SQL joins across geo + vector + time-series |
| ADR-B8 | Redis Streams for real-time (B4) | Kafka in the demo | Same consumer-group semantics; fewer moving parts; Kafka is the production answer |
| ADR-B9 | Skeleton routes return 501 with the phase | Leaving routes undefined | The frontend builds against the real contract now; the contract test prevents drift; the status stays honest |
| ADR-B10 | `/readyz` checks extensions and buckets, not just connectivity | Plain TCP pings | "Connected but not migrated" is the most common broken state; the probe says exactly what to run |
| ADR-B11 | Dev auth refused in `prod` | Trusting configuration | Fail closed: a misconfigured pilot can't silently run without auth |
| ADR-B12 | PDFium text layer + Tesseract 5 with table-rule removal | Docling + PaddleOCR | Much smaller dependency footprint (no PyTorch); measured 86% mean OCR confidence and 100% well linking on the synthetic scans; swappable behind `app/ingest/pages.py` |
| ADR-B13 | Synthetic field generator with planted ground truth | Hand-made fixtures | Every later phase needs realistic structure with *known* answers (events, mitigation success rates); generated deterministically from one seed |
| ADR-B14 | Rules-first extraction; LLM only as a later second pass | LLM-first extraction | Deterministic, explainable, unit-testable, offline, milliseconds per report. Every rule-based record cites its spans, and the confidence penalties say exactly why a record needs review |
| ADR-B15 | `hash` embedder as the offline default; Ollama BGE-M3 when configured | Always requiring a model server | Search must work air-gapped and in CI. The embedder's name is in every response, so nobody mistakes lexical hashing for semantics |
| ADR-B16 | Merge one event across reports (same well + type, ±15 m, ±3 days) | One event per report | Counting a DDR and its WCR summary twice would double every statistic and the ledger (Part 3). The merged event cites every report |
| ADR-B17 | Template lesson cards | LLM-written cards | Every sentence traces to extracted fields. A card describes one event and points to the ledger for rates. An LLM rewrite can come later as `generated_by` |
| ADR-B18 | scikit-learn `HistGradientBoostingClassifier` for S7b | LightGBM (the master plan's choice) | Same histogram-GBDT algorithm; LightGBM's wheel needs the system `libgomp`, absent from the slim image and not installable in the build sandbox. sklearn bundles its OpenMP. Revisit if model size or speed needs LightGBM's extras |
| ADR-B19 | MASS and banded DTW in NumPy | `stumpy` + `tslearn` | ~60 lines, no numba/JIT warm-up in the stream service, exact control of the z-normalisation floors and the deviation representation that fixed quiet-window matches (§0.1 finding 3). p95 query 138 ms on 99 signatures |
| ADR-B20 | Wide `rt_sample` (one row per wellbore and timestamp, a column per channel) | Narrow (one row per channel), as §10 first drew it | 12× fewer rows; the live view and the scorer read whole timestamps; TimescaleDB compresses the columns. New channels need a migration, acceptable for a fixed canonical set |
| ADR-B21 | Rules planner + templated answers as the default copilot engine | An LLM agent as the only engine | Deterministic, testable, and every sentence traces to a cited fact; no model is needed to demo or evaluate it. The LLM engine sits behind the same tools with a citation and number check and falls back to the rules |
| ADR-B22 | fpdf2 for the Offset Risk Brief | Jinja2 + WeasyPrint (§4.14) | Pure Python, no Pango/Cairo system libraries in the slim image, ~0.2 s per brief. Core fonts are Latin-1, handled by a substitution map |
| ADR-B23 | Local users (scrypt) + HS256 JWT before OIDC | Waiting for Keycloak in B6 | RBAC, the audit log and WebSocket auth could be built and tested now; the permission checks don't change when OIDC replaces the token issuer |

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

*(Updated 2026-09-29 after Part 5. B0–B5 are done.)*

1. **B6 (Part 6):** OIDC mode (V-B32), image digests (V-B3), Prometheus metrics, load test, security review, backups; the F6 login screen lets `jwt`/`oidc` become the default.
2. **Copilot refusals (V-B34):** a question-vs-passage entailment check; re-measure on real engineers' questions. Evaluate the LLM engine on OIL's approved model (V-B33).
3. **Real real-time data (V-B25, V-B26):** replay a Volve well through the CSV path; retrain S7b and rebuild the Déjà Vu library on real channels; re-measure every number in §0.1.
4. **Gold set (V-B15):** export the review queue's `(proposed, correction)` pairs, then add annotated real DDRs when data arrives.
5. **Save the pinned images** (`docker save`) for the finale machine (RB5) — Infra.

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

## Appendix B2 — B1 Verification Record (2026-09-28)

Clean run: images rebuilt, every volume wiped (`docker compose down -v`), stack up, full seed.

| Check | Command | Result |
|---|---|---|
| Full seed | `uv run python -m app.cli seed --inline` (OCR on the host; see V-B10) | 42 wells, 9 formations, 251 tops; **191 reports, 191 new, all `processed`**; 3 min 26 s |
| Re-seed | same command again | `191 selected, 0 new` (idempotent) |
| Well linking | SQL over `document` | **0 of 191** unlinked |
| OCR quality | SQL over `page` | 65 OCR'd pages, **mean confidence 86.3%**, lowest 69.6% |
| Extracted content | SQL | 3,838 text spans with bboxes · 765 chunks |
| Unit tests | `uv run pytest` | **58 passed** |
| Integration tests | `uv run pytest -m integration` | **11 passed** |
| Lint / types / migrations | ruff, ruff format, `mypy --strict`, `alembic check` | clean · "No new upgrade operations detected" |
| Offsets performance | `uv run python scripts/perf_offsets.py` | 10,000 wells, 200 queries: **p50 2.9 ms, p95 14.6 ms**, max 51 ms; GiST index used |
| Contract | `app.cli openapi` vs committed `frontend/src/lib/api/openapi.json` | identical |
| Worker round trip | `docker compose exec worker python -m app.cli check --worker` | exit 0 |

## Appendix B3 — B2 Verification Record (2026-09-29)

Clean run: every volume wiped (`docker compose down -v`), stack up, full seed with extraction and indexing.

| Check | Command | Result |
|---|---|---|
| Full seed | `uv run python -m app.cli seed --inline` (ingest → extract → index; OCR on the host, V-B10) | 42 wells; **191 reports processed, 191 extracted, 191 indexed**; 3 min 33 s |
| Extracted records | SQL | 113 events (merged across DDR + WCR), 165 mitigations, 572 DDR lines, 120 casing strings + cement jobs, 120 mud intervals, 14 review items, 765 embedded chunks |
| Extraction vs synthetic truth | `uv run python scripts/eval_extraction.py` | Event **P = R = F1 = 1.000**; scanned and text-layer DDRs both 1.000; type, formation, date, resolved 100%; subtype 92.1% (kick subtype never written); severity 88.5% (TIGHT/TORQUE severity is random in the generator); depth error mean 0.16 m; mitigations 100%; casing OD 95.8%; mud 100% → `eval/results/extraction_synthetic_2026-09-29.json` (commit `9a74d62`) |
| Re-extraction | `app.cli extract --all` twice | same 113 events and 14 review items (idempotent) |
| Re-seed keeps extracted data | `app.cli seed --no-documents` | 113 events and 120 casing strings still present (V-B16) |
| Unit tests | `uv run pytest` | **202 passed** |
| Integration tests | `uv run pytest -m integration` (run twice: tests tolerate their own earlier writes) | **25 passed** |
| Lint / types | ruff, ruff format, `mypy --strict` | clean |
| Latency (best of 5) | `curl` against the API container | search 24–27 ms · 6-well correlation 81–84 ms · events (500) 29 ms · AT_FORMATION 18 ms · CLOSEST_APPROACH 611 ms (5 km) |
| Contract | `app.cli openapi` → `frontend/src/lib/api/openapi.json`, `npm run gen:api` | regenerated and committed; frontend typecheck clean |

## Appendix B4 — B3 Verification Record (2026-09-29)

Clean run at commit `bce0acb`: images rebuilt, every volume wiped (`docker compose down -v`), stack up, full seed with extraction and indexing.

| Check | Command | Result |
|---|---|---|
| Full seed | `uv run python -m app.cli seed --inline` | 191 reports processed, extracted and indexed; 3 min 34 s |
| Extraction (unchanged) | `scripts/eval_extraction.py` | event P = R = F1 = 1.000 on synthetic reports (V-B15) |
| Ledger vs planted rates | `scripts/eval_ledger.py` | ρ = 0.837 (n ≥ 5, 17 pairs); coverage 24/24; scale check median ρ 0.65 (2 of 10 fields ≥ 0.8), coverage 91.1%, pooled ρ 0.956 → `eval/results/ledger_synthetic_2026-09-29.json` |
| Offset prior, leave-one-well-out | `scripts/eval_risk_prior.py` | Brier weighted 0.0350 < unweighted offsets 0.0362 < formation frequency 0.0366 < base rate 0.0489; paired bootstrap CIs exclude 0 → `eval/results/risk_prior_synthetic_2026-09-29.json` |
| Unit tests | `uv run pytest` | **244 passed** |
| Integration tests | `uv run pytest -m integration` | **33 passed** (incl. `test_b3.py` 8) |
| Lint / types | ruff, ruff format, `mypy --strict` | clean |
| Latency (sandbox, via nginx) | `curl` | ledger (LOSS, all wells) 26 ms · risk profile of the planned well (6 formations, ~40 offsets) 50 ms · cementing check 38 ms |
| CI | GitHub Actions on `f7ba585` (B3) and `bce0acb` (F2) | all three jobs green |

## Appendix B5 — B4 Verification Record (2026-09-29)

Clean run at commit `0ad33d4`: images rebuilt, every volume wiped (`docker compose down -v`), stack up (7 services incl. `stream`, all healthy), full seed with OCR on the host (V-B10).

| Check | Command | Result |
|---|---|---|
| Full seed + real-time assets | `uv run python -m app.cli seed --inline` | 191 reports processed; model bundle trained (36,669 rows), 99 signatures (99 linked to extracted events), τ = 1.073, replay file for SYN-ASM-41; 5 min 0 s in total |
| Classifiers | `scripts/eval_realtime.py` | held-out PR-AUC LOSS 0.951 · KICK 1.000 · STUCK 0.907 · TORQUE 0.552 · OVERP 0.972 · BALLING 0.942; training 26 s → `eval/results/realtime_synthetic_2026-09-29.json` |
| Déjà Vu | `scripts/eval_dejavu.py` | precision@1 0.992 (random 0.148, depth 0.415); alert recall 0.463, precision 1.0; false-match 1.25% → `eval/results/dejavu_synthetic_2026-09-29.json` |
| End-to-end replay at 60× | `scripts/eval_replay_alerts.py --speed 60` | planted balling alerted 28 min ahead, losses 124 min ahead (look-ahead) then fused with ML/physics/Déjà Vu; 0 false alerts; latency median 49 ms, max 185 ms (under CPU load: max 16.4 s, recorded in the same file) → `eval/results/replay_alerts_synthetic_2026-09-29.json` |
| Unit tests | `uv run pytest` | **290 passed** |
| Integration tests | `uv run pytest -m integration` | **40 passed** (incl. `test_b4.py` 7); also 40 passed on a 12-well CI-size field |
| Browser e2e | `npx playwright test` | **56 passed**, 2 skipped (incl. `part4.spec.ts`, axe in 3 themes) |
| Lint / types | ruff, ruff format, `mypy --strict` | clean |
| CI | GitHub Actions on `f744792` (B4) and `0ad33d4` (F3) | B4: backend and frontend jobs green, integration red on one Part 3 test pinned to phase "B3" (fixed in `0ad33d4`); `0ad33d4`: all three jobs green |

## Appendix C — Document Maintenance Rules

Same as master plan Appendix F:
- Dated update lines go in the header.
- Correct wrong statements in place with a dated note.
- Update §5 and `app/core/phases.py` in the same PR as the code.
- Every "✅" cites a file and a test.
