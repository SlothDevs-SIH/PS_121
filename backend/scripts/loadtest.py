"""Load-test the read-only API against the master plan §9 latency targets (backend plan B6).

Discovers the corpus through the API (wells, formations), builds a seeded request plan per
endpoint and fires it at a few concurrency levels. Per endpoint and level: p50/p95/p99, max,
throughput and error rate. The targeted endpoints are compared with §9:

- ``offsets_radius`` (``GET /wells/{id}/offsets``, SURFACE): radius query ≤ 500 ms p95 on
  ≤ 10,000 wells;
- ``search_hybrid`` (``GET /search``): hybrid search ≤ 1.5 s p95.

The rest (at-formation offsets, correlation panel, offset prior risk, ledger, analytics) are
measured without a target. GET only: nothing is written (the Offset Risk Brief is left out
because its download is audited). Each endpoint is measured on its own, one level at a time,
after a few unmeasured warm-up requests.

Honesty note: this is the SYNTHETIC corpus on one developer machine, not a production
cluster; the radius target's 10,000-well scale is measured by scripts/perf_offsets.py.

Needs a running API (dev auth, or ``--token`` / SMRITI_LOADTEST_TOKEN for jwt/oidc):

    cd backend && uv run python scripts/loadtest.py [--base-url URL] [--levels 1,4,16] [--requests 60]
"""

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"
API = "/api/v1"
SEED = 121
LEVELS = (1, 4, 16)
REQUESTS = 60
WARMUP = 3
TIMEOUT_S = 30.0
# Master plan §9 (p95, milliseconds).
TARGETS_P95_MS = {"offsets_radius": 500.0, "search_hybrid": 1500.0}
TOPS_SAMPLE = 20  # wells whose formation tops are read for the at-formation requests
RADII_KM = (1.0, 5.0, 10.0, 20.0)  # as scripts/perf_offsets.py
# Route (under /api/v1) of each measured endpoint, for the report.
ROUTES = {
    "offsets_radius": "GET /wells/{well_id}/offsets?mode=SURFACE",
    "offsets_at_formation": "GET /wells/{well_id}/offsets?mode=AT_FORMATION",
    "search_hybrid": "GET /search",
    "correlation": "GET /correlation?align=TVDSS",
    "risk_profile": "GET /wells/{well_id}/risk-profile",
    "ledger": "GET /ledger",
    "analytics_npt": "GET /analytics/npt",
    "analytics_recurring": "GET /analytics/recurring",
}
EVENT_TYPES = ("LOSS", "STUCK", "KICK", "TIGHT", "TORQUE", "GAS")
GROUP_BY = ("event_type", "formation", "year", "well", "field")
# Free-text questions an engineer types into search; {f} is a formation of the corpus.
QUERIES = (
    "lost circulation in the {f}",
    "stuck pipe while tripping out",
    "gas kick {f}",
    "mud losses cured with LCM pill",
    "tight hole and overpull, reaming",
    "high torque {f}",
    "cement job losses while displacing",
    "wellbore instability cavings",
    "differential sticking {f}",
    "bit balling in clay",
)


@dataclass(frozen=True)
class Request:
    endpoint: str
    path: str
    params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Sample:
    endpoint: str
    ms: float
    status: int | None  # None: no response (timeout, connection error)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


@dataclass(frozen=True)
class Corpus:
    well_ids: tuple[int, ...]
    wells_total: int
    formations: tuple[str, ...]
    # Formation tops of a sample of wells (AT_FORMATION needs a top on the subject well).
    tops: dict[int, tuple[str, ...]]


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (the smallest value with at least p % of the values at or
    below it): conservative on small samples, never interpolates below a real value."""
    if not values:
        raise ValueError("percentile of no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def summarise(samples: Sequence[Sample], wall_s: float) -> dict[str, Any]:
    """Latency percentiles over the successful requests; errors counted by kind."""
    ok = [s.ms for s in samples if s.ok]
    errors = Counter(s.error or str(s.status) for s in samples if not s.ok)
    n = len(samples)
    out: dict[str, Any] = {
        "requests": n,
        "errors": sum(errors.values()),
        "error_rate": round(sum(errors.values()) / n, 4) if n else None,
        "error_kinds": dict(sorted(errors.items())),
        "throughput_rps": round(n / wall_s, 1) if wall_s > 0 else None,
    }
    if ok:
        out |= {
            "p50_ms": round(percentile(ok, 50), 1),
            "p95_ms": round(percentile(ok, 95), 1),
            "p99_ms": round(percentile(ok, 99), 1),
            "max_ms": round(max(ok), 1),
            "mean_ms": round(statistics.fmean(ok), 1),
        }
    else:
        out |= dict.fromkeys(("p50_ms", "p95_ms", "p99_ms", "max_ms", "mean_ms"))
    return out


async def discover(client: httpx.AsyncClient, seed: int = SEED) -> Corpus:
    """Every well id (paged), the formation names and the tops of a seeded sample of wells,
    through the API itself."""
    ids: list[int] = []
    total = 0
    while True:
        r = await client.get(f"{API}/wells", params={"limit": 500, "offset": len(ids)})
        r.raise_for_status()
        body = r.json()
        total = body["total"]
        ids += [w["id"] for w in body["items"]]
        if not body["items"] or len(ids) >= total:
            break
    r = await client.get(f"{API}/formations")
    r.raise_for_status()
    formations = sorted({f["name"] for f in r.json()})
    if len(ids) < 2:
        raise SystemExit("the API has fewer than 2 wells: seed the stack first")
    rnd = random.Random(seed)  # noqa: S311 (sampling wells, not cryptography)
    tops: dict[int, tuple[str, ...]] = {}
    for wid in sorted(rnd.sample(ids, min(TOPS_SAMPLE, len(ids)))):
        r = await client.get(f"{API}/wells/{wid}")
        r.raise_for_status()
        if names := tuple(t["formation"] for t in r.json()["formation_tops"]):
            tops[wid] = names
    return Corpus(tuple(ids), total, tuple(formations), tops)


def build_plan(corpus: Corpus, n: int, seed: int = SEED) -> dict[str, list[Request]]:
    """``n`` requests per endpoint, drawn with a fixed seed so every run asks the same."""
    rnd = random.Random(seed)  # noqa: S311 (sampling requests, not cryptography)
    wells = corpus.well_ids
    forms = corpus.formations or ("",)
    with_tops = sorted(corpus.tops)

    def well() -> int:
        return rnd.choice(wells)

    def query() -> str:
        return rnd.choice(QUERIES).format(f=rnd.choice(forms)).strip()

    def search(i: int) -> Request:
        params = [("q", query()), ("limit", "10")]
        if i % 3 == 2:  # a third filtered to one well's neighbourhood, as the Well 360 does
            params += [("well_id", str(well())), ("radius_km", "10")]
        return Request("search_hybrid", f"{API}/search", tuple(params))

    def correlation() -> Request:
        panel = rnd.sample(wells, min(len(wells), rnd.randint(3, 5)))
        return Request(
            "correlation",
            f"{API}/correlation",
            (*(("wells", str(w)) for w in panel), ("align", "TVDSS")),
        )

    def at_formation() -> Request:
        wid = rnd.choice(with_tops)
        return Request(
            "offsets_at_formation",
            f"{API}/wells/{wid}/offsets",
            (
                ("radius_km", "10"),
                ("mode", "AT_FORMATION"),
                ("formation", rnd.choice(corpus.tops[wid])),
            ),
        )

    def ledger(i: int) -> Request:
        params = [("event_type", rnd.choice(EVENT_TYPES))]
        if i % 2 and corpus.formations:
            params.append(("formation", rnd.choice(corpus.formations)))
        return Request("ledger", f"{API}/ledger", tuple(params))

    makers: dict[str, Callable[[int], Request]] = {
        "offsets_radius": lambda i: Request(
            "offsets_radius",
            f"{API}/wells/{well()}/offsets",
            (("radius_km", str(RADII_KM[i % len(RADII_KM)])), ("mode", "SURFACE")),
        ),
        "offsets_at_formation": lambda i: at_formation(),
        "search_hybrid": search,
        "correlation": lambda i: correlation(),
        "risk_profile": lambda i: Request("risk_profile", f"{API}/wells/{well()}/risk-profile"),
        "ledger": ledger,
        "analytics_npt": lambda i: Request(
            "analytics_npt", f"{API}/analytics/npt", (("group_by", GROUP_BY[i % len(GROUP_BY)]),)
        ),
        "analytics_recurring": lambda i: Request(
            "analytics_recurring", f"{API}/analytics/recurring"
        ),
    }
    if not with_tops:
        del makers["offsets_at_formation"]
    return {name: [make(i) for i in range(n)] for name, make in makers.items()}


async def fire(client: httpx.AsyncClient, req: Request) -> Sample:
    t = time.perf_counter()
    try:
        r = await client.get(req.path, params=list(req.params))
        await r.aread()
    except httpx.TimeoutException:
        return Sample(req.endpoint, (time.perf_counter() - t) * 1000, None, "timeout")
    except httpx.HTTPError as e:
        return Sample(req.endpoint, (time.perf_counter() - t) * 1000, None, type(e).__name__)
    return Sample(req.endpoint, (time.perf_counter() - t) * 1000, r.status_code)


async def run_level(
    client: httpx.AsyncClient, requests: Sequence[Request], concurrency: int
) -> tuple[list[Sample], float]:
    """All ``requests`` with at most ``concurrency`` in flight; (samples, wall seconds)."""
    queue: asyncio.Queue[Request] = asyncio.Queue()
    for req in requests:
        queue.put_nowait(req)
    samples: list[Sample] = []

    async def worker() -> None:
        while not queue.empty():
            samples.append(await fire(client, queue.get_nowait()))

    t = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(max(1, min(concurrency, len(requests))))))
    return samples, time.perf_counter() - t


def compare(results: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Each §9 target at each level: pass when p95 is within it and nothing failed."""
    rows = []
    for endpoint, target in TARGETS_P95_MS.items():
        for level, stats in results.get(endpoint, {}).items():
            p95 = stats["p95_ms"]
            rows.append(
                {
                    "endpoint": endpoint,
                    "concurrency": int(level),
                    "target_p95_ms": target,
                    "measured_p95_ms": p95,
                    "error_rate": stats["error_rate"],
                    "pass": p95 is not None and p95 <= target and stats["errors"] == 0,
                }
            )
    return rows


async def measure(
    client: httpx.AsyncClient,
    levels: Sequence[int] = LEVELS,
    n: int = REQUESTS,
    warmup: int = WARMUP,
    seed: int = SEED,
) -> dict[str, Any]:
    corpus = await discover(client, seed)
    plan = build_plan(corpus, n + warmup, seed)
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for endpoint, reqs in plan.items():
        for req in reqs[:warmup]:  # connection pool, query plans and caches warmed, not counted
            await fire(client, req)
        for level in levels:
            samples, wall = await run_level(client, reqs[warmup:], level)
            results.setdefault(endpoint, {})[str(level)] = summarise(samples, wall)
            s = results[endpoint][str(level)]
            print(
                f"{endpoint:22} c={level:<3} p50 {s['p50_ms']} ms  p95 {s['p95_ms']} ms  "
                f"p99 {s['p99_ms']} ms  errors {s['errors']}/{s['requests']}",
                file=sys.stderr,
            )
    return {
        "corpus": {
            "wells_total": corpus.wells_total,
            "formations": len(corpus.formations),
            "wells_with_tops_sampled": len(corpus.tops),
        },
        "levels": list(levels),
        "requests_per_endpoint_per_level": n,
        "warmup_per_endpoint": warmup,
        "seed": seed,
        "endpoints": {name: {"route": ROUTES[name], "results": results[name]} for name in plan},
        "targets": compare(results),
    }


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--base-url", default=os.environ.get("SMRITI_LOADTEST_URL", "http://127.0.0.1:8000")
    )
    ap.add_argument(
        "--token", default=os.environ.get("SMRITI_LOADTEST_TOKEN"), help="Bearer token (jwt/oidc)"
    )
    ap.add_argument(
        "--levels", default=",".join(map(str, LEVELS)), help="concurrency levels, e.g. 1,4,16"
    )
    ap.add_argument(
        "--requests", type=int, default=REQUESTS, help="measured requests per endpoint and level"
    )
    ap.add_argument("--warmup", type=int, default=WARMUP)
    ap.add_argument(
        "--out", type=Path, default=None, help="default eval/results/loadtest_synthetic_<date>.json"
    )
    args = ap.parse_args(argv)
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    if not levels or min(levels) < 1 or args.requests < 1:
        ap.error("levels and --requests must be positive")
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    limits = httpx.Limits(max_connections=max(levels), max_keepalive_connections=max(levels))

    async def go() -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=args.base_url, headers=headers, timeout=TIMEOUT_S, limits=limits
        ) as client:
            return await measure(client, levels, args.requests, args.warmup)

    t = time.perf_counter()
    body = asyncio.run(go())
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result: dict[str, Any] = {
        "what": "Read-only API latency under concurrent load on the SYNTHETIC corpus "
        "(master plan §9 targets)",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "base_url": args.base_url,
        "auth": "bearer" if args.token else "none (dev mode)",
        "duration_s": round(time.perf_counter() - t, 1),
        **body,
        "notes": [
            "SYNTHETIC corpus on one developer machine (API, database and client on the same "
            "host, single uvicorn process); not a production capacity figure.",
            "Percentiles are nearest-rank over the successful requests; latency is measured "
            "by the client, from send to the last byte of the body. With fewer than 100 "
            "requests per level, p99 is the slowest request.",
            "Each endpoint is measured alone at each level (no mixed traffic); a target passes "
            "only with p95 within it and no failed request.",
            "The radius target is stated for <= 10,000 wells; this corpus has "
            f"{body['corpus']['wells_total']} (scripts/perf_offsets.py measures 10,000).",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = args.out or OUT_DIR / f"loadtest_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for row in result["targets"]:
        verdict = "PASS" if row["pass"] else "FAIL"
        print(
            f"{verdict} {row['endpoint']} c={row['concurrency']}: p95 {row['measured_p95_ms']} ms "
            f"(target {row['target_p95_ms']:.0f} ms)",
            file=sys.stderr,
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
