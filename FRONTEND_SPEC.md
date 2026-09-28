# NWIS Frontend — Build Specification

This document is a complete blueprint for the NWIS frontend. Hand it to an AI coding agent with the instruction: **"Build the full frontend from this spec."** It covers design system, layout architecture, every page, every animation, theming, state management, and the exact rules that prevent layout glitches — for the stack already chosen:

**React + TypeScript + Vite · Tailwind + shadcn/ui · Framer Motion · MapLibre GL · react-three-fiber (Three.js) · Apache ECharts · cmdk · TanStack Query · Zustand**

---

## 0. Design intent (read this first)

The brief: **"crazy but professional."** That means:
- Motion everywhere something changes state (route change, data arrives, hover, scroll) — never motion for its own sake on static content.
- A dark, data-dense, "mission control" aesthetic by default (drilling ops centers run dark-mode monitors), with a light theme as an alternative, not the default.
- Real information density — this is an engineer's tool, not a marketing site. Flashy chrome, serious content.
- **Zero layout shift.** Every animation must animate `transform`/`opacity` only, never `width`/`height`/`top`/`left` directly (see §7 for the enforced rule set that prevents glitches).

---

## 1. Project structure

```
nwis-frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx                        # router + providers root
│   ├── router.tsx                     # route tree (React Router v6, data routers)
│   │
│   ├── app-shell/
│   │   ├── AppShell.tsx               # persistent layout: sidebar + topbar + content outlet
│   │   ├── Sidebar.tsx
│   │   ├── SidebarNavItem.tsx
│   │   ├── Topbar.tsx                 # breadcrumbs, well-type switcher, command palette trigger, user menu
│   │   ├── CommandPalette.tsx         # cmdk-powered ⌘K search
│   │   └── ThemeSwitcher.tsx
│   │
│   ├── pages/
│   │   ├── landing/
│   │   │   └── LandingPage.tsx        # pre-login hero with scroll animation showcase
│   │   ├── dashboard/
│   │   │   └── DashboardPage.tsx      # field-wide overview, all active wells + alerts feed
│   │   ├── map/
│   │   │   └── MapExplorerPage.tsx    # full-screen MapLibre view, well-type filtered
│   │   ├── well-detail/
│   │   │   ├── WellDetailPage.tsx     # tabbed: Overview / Trajectory / Parameters / Events / Correlation
│   │   │   ├── tabs/
│   │   │   │   ├── OverviewTab.tsx
│   │   │   │   ├── Trajectory3DTab.tsx
│   │   │   │   ├── ParametersTab.tsx
│   │   │   │   ├── EventsTimelineTab.tsx
│   │   │   │   └── CorrelationTab.tsx
│   │   ├── search/
│   │   │   └── KnowledgeSearchPage.tsx  # RAG search / "ask" interface
│   │   ├── alerts/
│   │   │   └── AlertsCenterPage.tsx
│   │   ├── documents/
│   │   │   └── DocumentsLibraryPage.tsx
│   │   └── auth/
│   │       └── LoginPage.tsx
│   │
│   ├── components/
│   │   ├── ui/                        # shadcn/ui generated primitives (button, card, dialog, etc.)
│   │   ├── map/
│   │   │   ├── WellMap.tsx            # MapLibre wrapper, handles flyTo, clustering, pulse markers
│   │   │   ├── WellMarker.tsx
│   │   │   ├── WellTypeLegend.tsx
│   │   │   └── RadiusControl.tsx
│   │   ├── charts/
│   │   │   ├── LiveParameterChart.tsx  # ECharts, WebSocket-fed
│   │   │   ├── CorrelationTrackView.tsx # D3 depth-aligned tracks
│   │   │   └── RiskGaugeChart.tsx
│   │   ├── three/
│   │   │   └── WellboreTrajectory3D.tsx # react-three-fiber scene
│   │   ├── alerts/
│   │   │   ├── AlertCard.tsx
│   │   │   ├── AlertToast.tsx          # live popup on new WS alert
│   │   │   └── AlertExplanationPanel.tsx # SHAP breakdown, expandable
│   │   ├── motion/
│   │   │   ├── PageTransition.tsx      # wraps route outlet
│   │   │   ├── RevealOnScroll.tsx      # generic scroll-in wrapper
│   │   │   ├── StaggerList.tsx
│   │   │   └── AnimatedBackground.tsx  # ambient canvas/gradient layer
│   │   ├── well-type/
│   │   │   ├── WellTypeSwitcher.tsx    # Oil / Water / Gas segmented control
│   │   │   └── WellTypeBadge.tsx
│   │   └── shared/
│   │       ├── EmptyState.tsx
│   │       ├── ErrorBoundary.tsx
│   │       └── SkeletonBlock.tsx
│   │
│   ├── stores/                        # Zustand — client-only UI state
│   │   ├── useThemeStore.ts
│   │   ├── useWellTypeFilterStore.ts   # currently selected well type(s)
│   │   ├── useSidebarStore.ts          # collapsed/expanded
│   │   └── useActiveWellStore.ts
│   │
│   ├── queries/                       # TanStack Query hooks, one file per backend resource
│   │   ├── useWells.ts
│   │   ├── useWellDetail.ts
│   │   ├── useNearbyWells.ts
│   │   ├── useEvents.ts
│   │   ├── useAlerts.ts
│   │   ├── useSearch.ts
│   │   ├── useParameters.ts
│   │   └── useCorrelation.ts
│   │
│   ├── ws/
│   │   ├── useWellSocket.ts           # subscribes to /ws/wells/{id}
│   │   └── useDashboardSocket.ts      # subscribes to /ws/dashboard
│   │
│   ├── lib/
│   │   ├── api-client.ts              # axios/fetch instance, auth header injection
│   │   ├── theme-tokens.ts            # design tokens, see §2
│   │   └── motion-variants.ts         # shared Framer Motion variant objects, see §5
│   │
│   ├── types/                         # TypeScript types mirroring backend Pydantic schemas
│   └── styles/
│       └── globals.css                # Tailwind base + CSS variables for themes
├── index.html
├── tailwind.config.ts
├── vite.config.ts
├── tsconfig.json
└── package.json
```

---

## 2. Design system & themes

### 2.1 Themes (switchable, persisted in localStorage via `useThemeStore`)

| Theme | Feel | Base colors |
|---|---|---|
| **Deep Rig** (default) | Dark ops-center | `--bg: #0A0E14`, `--surface: #131826`, `--surface-2: #1B2233`, `--text: #E6EAF2`, `--accent: #FF6B35` (rig-orange), `--accent-2: #00D9C0` (teal, for water/normal states) |
| **Daylight Field** | Light, printable, office use | `--bg: #F7F8FA`, `--surface: #FFFFFF`, `--surface-2: #EEF1F6`, `--text: #101522`, `--accent: #D9480F`, `--accent-2: #0EA5A0` |
| **Command Blue** (optional 3rd) | Dark, blue-forward, alternate to orange | `--bg: #05080F`, `--accent: #3B82F6` |

Implement as CSS variables on `:root[data-theme="..."]`, consumed by Tailwind via `theme.extend.colors` referencing `var(--...)`. **Never hardcode hex colors in components** — always reference the token so theme switching costs zero component changes.

### 2.2 Well-type color coding (used consistently in map, badges, charts, sidebar counts)

| Well type | Color | Marker icon |
|---|---|---|
| Oil | `--well-oil: #FF6B35` | droplet, filled |
| Gas | `--well-gas: #F2C94C` | flame outline |
| Water | `--well-water: #00B4D8` | droplet, outline |

### 2.3 Typography
- Font: **Geist** or **Inter**, self-hosted (`@fontsource`) — never system default.
- Numeric/monospace readouts (depths, live parameter values): **JetBrains Mono** or **Geist Mono**, tabular-nums, so live-updating numbers don't jitter in width.

### 2.4 Elevation & glow
- Cards use subtle `box-shadow` + 1px border (`--surface-2`), not heavy drop shadows.
- Active/live elements (a well currently drilling, an active alert) get a soft animated glow (`box-shadow` pulsing via Framer `animate` loop) in the well-type or alert-severity color — this is a major contributor to the "crazy but professional" feel without being gimmicky.

---

## 3. App shell layout (persistent across all authenticated pages)

```
┌──────────────────────────────────────────────────────────────┐
│ Topbar: breadcrumb · WellTypeSwitcher · ⌘K search · theme · user│
├───────────┬──────────────────────────────────────────────────┤
│           │                                                     │
│  Sidebar  │                  Route Outlet                       │
│ (collaps- │            (AnimatePresence-wrapped page)           │
│  ible)    │                                                     │
│           │                                                     │
└───────────┴──────────────────────────────────────────────────┘
```

### 3.1 Sidebar (`Sidebar.tsx`)
- Collapsible: full (240px, icon+label) ↔ rail (72px, icon only). Width change animates via `transform: scaleX` trick or a Framer `width` animation **guarded by `layout` prop** (see §7 — width animations need special handling to avoid reflow jank).
- Sections, top to bottom:
  1. **Dashboard** (home icon)
  2. **Map Explorer** (map icon)
  3. **Wells** — expandable group, sub-items generated per well type:
     - Oil Wells (count badge)
     - Gas Wells (count badge)
     - Water Wells (count badge)
  4. **Knowledge Search** (search/sparkle icon)
  5. **Alerts Center** (bell icon, live unread-count badge that pulses on new alert)
  6. **Documents Library** (file icon)
  7. — divider —
  8. Settings, Help
- Each `SidebarNavItem` has: icon micro-bounce on hover (`whileHover={{ scale: 1.08 }}`), active-route indicator as a `layoutId="sidebar-active-pill"` Framer element that **slides** between items instead of popping — this is the single highest-impact "premium app" motion detail.
- Badge counts pull from `useWells()` grouped by `well_type`, live-updated via the dashboard WebSocket.

### 3.2 Topbar
- `WellTypeSwitcher`: segmented control (Oil / Gas / Water / All) — sets `useWellTypeFilterStore`, which every page (map, dashboard, wells list) reads to filter its data. Switching animates the active segment with a sliding pill (same `layoutId` pattern as sidebar).
- `CommandPalette` trigger (`⌘K` or click) — opens `cmdk` modal for jumping to any well, document, or page instantly. Fuzzy search across well names/UWI.
- Theme switcher: icon button cycling themes, with a **circular reveal transition** (`clip-path` animated via Framer or the View Transitions API) sweeping the new theme in from the click point — a flashy but cheap-to-build effect.

---

## 4. Pages, in detail

### 4.1 Landing / Login (`LandingPage.tsx`, `LoginPage.tsx`)
- Full-viewport hero: `AnimatedBackground` component — a subtly animated gradient mesh or slow-drifting particle field (tsparticles, low density, low opacity) behind the NWIS title.
- As the user scrolls the landing page (if there's marketing content above the login form), each section uses `RevealOnScroll` (fade-up + slight scale, triggered by `whileInView`, `viewport={{ once: true, margin: "-100px" }}`).
- Parallax: background layer moves slower than foreground content on scroll (`useScroll` + `useTransform` from Framer Motion, mapping scroll progress to a `y` translate on the background layer only — never on layout-affecting properties).
- Login form: `shadcn/ui` Card with a glassmorphism surface (`backdrop-blur`, translucent `--surface`), floating-label inputs, submit button with a loading-spinner morph state.

### 4.2 Dashboard (`DashboardPage.tsx`)
- Grid of KPI cards at top (active wells, open alerts, wells drilling today, avg risk score) — each card's number **counts up** on mount (Framer `animate` from 0 to value, or a small `useCountUp` hook) instead of appearing instantly.
- Below: two-column layout —
  - Left: mini `WellMap` (non-interactive-ish overview, click to go full map) showing all wells color-coded by type, active-drilling wells pulsing.
  - Right: live `AlertsFeed` — `StaggerList` of `AlertCard`s, newest alert slides in from the top with a highlight flash when pushed via WebSocket.
- Bottom: `LiveParameterChart` strip for whichever well the user most recently viewed (or the highest-risk active well by default).

### 4.3 Map Explorer (`MapExplorerPage.tsx`) — the centerpiece
- Full-bleed `WellMap` (MapLibre GL), sidebar collapses to rail automatically on entering this page (more map real estate), restores on leaving.
- `WellTypeLegend` floating bottom-left, toggle visibility per type (checkbox chips in well-type colors).
- `RadiusControl` floating top-left: when a well is selected, a draggable radius circle (PostGIS `ST_DWithin` radius, default e.g. 10 km) appears around it; dragging the handle live-updates `useNearbyWells(wellId, radiusKm)` and re-renders nearby-well markers with a **ripple animation** emanating from the center well each time the radius changes.
- Clicking a well marker: camera does a `flyTo` (MapLibre's built-in eased pan+zoom — this alone makes the map feel expensive) to center it, and a side panel slides in (Framer `x` transform from off-screen, `AnimatePresence`) showing a well summary card with a "View Full Details →" button routing to `WellDetailPage`.
- Markers: base marker uses well-type color and icon; wells currently drilling get a **CSS/Framer pulse ring** (`animate: { scale: [1, 1.6], opacity: [0.6, 0] }`, `repeat: Infinity`) — an expanding ring behind the pin, very "live ops" looking, cheap to implement, no layout impact since it's an absolutely-positioned decorative element.
- Marker clustering at low zoom (MapLibre's built-in cluster support) so 500 wells don't turn into visual noise; clusters show well-type composition as a small stacked-color ring.

### 4.4 Well Detail (`WellDetailPage.tsx`)
- Header: well name, UWI, status badge (with well-type color), quick stats row.
- Tab bar (`Overview / Trajectory / Parameters / Events / Correlation`) — active tab indicator uses the same sliding `layoutId` pill pattern as the sidebar, for visual consistency across the app.
- Tab content is swapped via `AnimatePresence mode="wait"` with a fade+slight-slide transition — **never** an instant swap, but also never longer than ~200ms so it doesn't feel sluggish when the user is tab-flicking.
- **Trajectory3DTab**: `WellboreTrajectory3D` (react-three-fiber) — renders the wellbore path as a 3D tube/line from `useWellDetail`'s trajectory data, camera auto-orbits slowly when idle (`useFrame` incrementing rotation), user can drag to override (OrbitControls-equivalent, r128-safe — no `CapsuleGeometry`/r142+ APIs). Offset wells within radius can be toggled on/off as additional translucent paths in the same scene, color-coded by well type, for visual "these wells are near this one" comparison.
- **ParametersTab**: multiple `LiveParameterChart` panels (ROP, torque, SPP, gas units) stacked, all sharing a synced depth/time cursor (hovering one highlights the same x-position on all — implement via a shared Zustand "hover cursor" value, not prop drilling). If the well is currently active, charts subscribe to `useWellSocket` and animate new points in (ECharts handles this natively with smooth transitions when you push new data).
- **EventsTimelineTab**: vertical timeline (custom component, not a library) — each historical event is a card positioned along a depth axis, severity shown by left-border color/thickness, clicking expands the card (height auto-animate using Framer's `layout` prop, which handles the surrounding elements reflowing smoothly instead of jumping — the correct way to animate height without glitching, see §7).
- **CorrelationTab**: `CorrelationTrackView` (D3) — depth-aligned vertical tracks, one per selected offset well, each showing formation bands + event markers at their true depth, synced with the trajectory view.

### 4.5 Knowledge Search (`KnowledgeSearchPage.tsx`)
- Large centered search input (Perplexity/Linear-search-style), well-type and formation filter chips beneath it.
- Results stream in as cards (`StaggerList`), each showing the matched excerpt, source document + page (click opens `DocumentsLibraryPage` deep-linked to that page), and a relevance score bar that fills in on mount.
- "Ask" mode toggle: switches from raw search results to a chat-style RAG answer with inline citation chips that, on hover, show a small popover preview of the source excerpt.

### 4.6 Alerts Center (`AlertsCenterPage.tsx`)
- Filterable list (by well type, severity, status) of `AlertCard`s.
- Each card expandable into `AlertExplanationPanel`: SHAP bar chart of contributing features, the matched offset-well event with a "View that well" link, and pattern-similarity score shown as a small sparkline overlay of current-vs-historical curve.
- New alerts arriving via `useDashboardSocket` trigger both a list insertion (stagger-in) **and** a corner `AlertToast` popup (auto-dismiss after ~6s or on click), for visibility even when the user isn't on this page.

### 4.7 Documents Library (`DocumentsLibraryPage.tsx`)
- Grid/list toggle of document cards (thumbnail of first page, type badge, processing-status indicator: pending/processing spinner/done/needs-review flag).
- Drag-and-drop upload zone at top — dropping a file shows an animated upload progress ring, then a processing-status timeline (Uploaded → OCR → Extraction → Embedded) that updates live by polling `GET /documents/{id}` or listening on a WS channel.

---

## 5. Motion system (`lib/motion-variants.ts`)

Centralize reusable Framer Motion variants so every component behaves consistently:

```ts
export const pageTransition = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] }
};

export const revealOnScroll = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.5, ease: "easeOut" }
};

export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.06 } }
};

export const staggerItem = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 }
};

export const activePillTransition = { type: "spring", stiffness: 500, damping: 40 };
```

Rules for the build agent:
- `PageTransition.tsx` wraps the router outlet with `AnimatePresence mode="wait"` + `pageTransition`.
- `RevealOnScroll.tsx` is a thin wrapper applying `revealOnScroll` to `children` — used for landing-page sections and any long scrollable content list.
- Sliding active-tab/nav indicators always use a single shared `layoutId` **per switcher instance** (unique string per component instance, not globally shared, or unrelated indicators will visually "jump" between each other).
- Loading states always use `SkeletonBlock` (shimmer animation, matched to the exact dimensions of the content it replaces) — never a layout that pops from 0-height to full content height.

---

## 6. State & data layer

- **TanStack Query** for all server state (wells, events, documents, search, alerts, parameters history). Standard config: `staleTime` a few seconds for frequently-changing resources (alerts), a few minutes for static ones (well metadata, documents).
- **Zustand** for pure client/UI state only: theme, sidebar collapsed state, active well-type filter, shared chart hover-cursor. Never duplicate server data into Zustand.
- **WebSocket hooks** (`useWellSocket`, `useDashboardSocket`) own their own connection lifecycle (connect on mount, reconnect with backoff on drop, clean up on unmount) and push incoming messages into the relevant TanStack Query cache via `queryClient.setQueryData` (for parameter ticks) or trigger a toast + `queryClient.invalidateQueries` (for new alerts) — this keeps WS data flowing through the same cache the REST-fetched data lives in, so components don't need to know whether data came from a fetch or a socket.

---

## 7. Anti-layout-glitch rules (enforced, non-negotiable)

These are the rules that most commonly cause hackathon frontends to look janky under time pressure. State them explicitly to the build agent:

1. **Animate only `transform` and `opacity`.** Never animate `width`, `height`, `top`, `left`, `margin`, or `padding` directly — these trigger layout recalculation and cause visible jank, especially on lower-end demo laptops/projectors.
2. **Height changes use Framer's `layout` prop**, not manual height animation. Wrap the parent in `<motion.div layout>` and Framer computes the FLIP transform automatically, so expanding an event card or an accordion reflows smoothly instead of jumping.
3. **Reserve space before content loads.** Every async section (charts, map, images) has a fixed or aspect-ratio-locked container (`aspect-[16/9]`, explicit `min-height`) with a `SkeletonBlock` inside, so content arriving doesn't shift anything below it.
4. **Sidebar width changes** use a fixed-width outer container with an inner `motion.div` that scales/translates, or CSS `grid-template-columns` transitioned via a CSS transition (which the browser can composite) rather than a JS-animated `width` on every frame.
5. **Fonts are preloaded** (`<link rel="preload" as="font">` or `@fontsource` static import) to prevent FOUT-driven text reflow.
6. **Charts (ECharts) are given explicit container dimensions** before initialization — never let ECharts compute size from an animating parent; resize only via a debounced `ResizeObserver`, not on every animation frame.
7. **The map (MapLibre) container has a fixed size before `Map()` is instantiated** — mounting it inside an already-animating flex/grid container causes the canvas to misjudge its size; mount after the layout transition settles, or call `map.resize()` on transition end.
8. **`AnimatePresence` always has a stable, unique `key`** on route/tab children — missing or duplicate keys are the most common cause of elements animating in from the wrong position or not exiting cleanly.
9. **z-index scale is fixed and documented** (e.g. base content `0`, sticky topbar `20`, sidebar `30`, dropdowns/popovers `40`, modals `50`, toasts `60`) — defined once in `theme-tokens.ts`, never ad-hoc per component, to avoid overlap bugs between the map, panels and toasts.
10. **Test every animated component at both themes and both collapsed/expanded sidebar states** before considering it done — most glitches only show up in one combination.

---

## 8. Well-type separation — where it shows up

"Oil / Water / Gas" isn't just a filter — it should be visible and consistent everywhere:
- Sidebar: separate collapsible groups with live counts.
- Topbar: global `WellTypeSwitcher` filters map, dashboard, and lists simultaneously (shared Zustand state).
- Map: color + icon per type, legend toggle.
- Well Detail header: colored badge next to well name.
- Charts/correlation views: offset wells rendered in their type color, so a mixed-type correlation view is still legible at a glance.
- Command palette results: type icon shown next to each well result.

Backend note for the build agent: this assumes `wells.well_type` (`oil | gas | water`) exists as a column — confirm it's added to the `wells` table in the backend schema (it wasn't in the original backend spec's `wells` table and should be added as `well_type TEXT CHECK (well_type IN ('oil','gas','water'))`).

---

## 9. Responsiveness

- Primary target: desktop/laptop (this is an ops-center and office tool) and large tablet for field use.
- Sidebar auto-collapses to icon rail below `lg` breakpoint; below `md`, it becomes an off-canvas drawer triggered from the topbar.
- Map Explorer and Well Detail's 3D/correlation tabs are desktop-first — show a "best viewed on a larger screen" `EmptyState` politely on very small viewports rather than cramming a broken layout in.
- All grid layouts use Tailwind's responsive grid classes with defined breakpoints tested at 1280px (typical laptop), 1920px (projector/monitor), and 768px (tablet) — the three realistic demo environments.

---

## 10. Build order (recommended sequence for the coding agent)

1. `theme-tokens.ts`, Tailwind config, both themes wired, `ThemeSwitcher` working on a blank page — get theming right before building on top of it.
2. `AppShell` + `Sidebar` + `Topbar` with static (non-live) nav — confirm the shell has zero layout glitches at every collapse/theme combination first.
3. `PageTransition`, routing, and the motion-variants file — wire page transitions between two placeholder pages.
4. `WellMap` + `WellTypeSwitcher` + `WellTypeLegend`, fed by `useWells()` — this is the highest-visibility feature, prioritize it.
5. `DashboardPage` KPI cards + count-up + mini map + alerts feed skeletons (with mocked data if backend isn't ready yet).
6. `WellDetailPage` shell + tabs + `OverviewTab` (simplest tab first).
7. `LiveParameterChart` + `useWellSocket`, tested against `streaming/producer_sim.py` from the backend.
8. `Trajectory3DTab` (react-three-fiber) — isolate this, it's the most likely to need iteration.
9. `EventsTimelineTab`, `CorrelationTab`.
10. `KnowledgeSearchPage`, `AlertsCenterPage`, `DocumentsLibraryPage`.
11. `CommandPalette` (cmdk) last — it's a cross-cutting feature that needs every other route/entity to exist first.
12. Final pass: run through the §7 anti-glitch checklist on every screen, both themes, three viewport sizes.
