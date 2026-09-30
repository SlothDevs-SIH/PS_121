"""B6 load test (scripts/loadtest.py) without a stack: the percentile and aggregation maths, the
seeded request plan, and a full run against a fake API on httpx.MockTransport (GET only, every
endpoint at every level, concurrency capped, §9 targets judged)."""

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[2]
N_WELLS = 620  # more than one page of GET /wells (limit 500)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("loadtest", BACKEND / "scripts" / "loadtest.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["loadtest"] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


lt = _load()


class FakeApi:
    """The routes the load test calls. Odd well ids have formation tops, even ones none;
    ``fail`` maps an endpoint path prefix to the status it answers with."""

    def __init__(self, fail: dict[str, int] | None = None, delay_s: float = 0.0) -> None:
        self.fail = fail or {}
        self.delay_s = delay_s
        self.methods: set[str] = set()
        self.paths: list[str] = []
        self.in_flight = 0
        self.peak = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.methods.add(request.method)
        path = request.url.path
        self.paths.append(path)
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.delay_s)
            return self._answer(request, path)
        finally:
            self.in_flight -= 1

    def _answer(self, request: httpx.Request, path: str) -> httpx.Response:
        for prefix, status in self.fail.items():
            if path.startswith(prefix):
                return httpx.Response(status, json={"error": {"code": "boom"}})
        if path == "/api/v1/wells":
            limit = int(request.url.params["limit"])
            offset = int(request.url.params["offset"])
            ids = range(offset + 1, min(offset + limit, N_WELLS) + 1)
            return httpx.Response(200, json={"items": [{"id": i} for i in ids], "total": N_WELLS})
        if path == "/api/v1/formations":
            names = ["Tipam Sandstone", "Barail", "Barail", "Girujan Clay"]
            return httpx.Response(200, json=[{"name": n} for n in names])
        if m := re.fullmatch(r"/api/v1/wells/(\d+)", path):
            tops = ["Tipam Sandstone", "Barail"] if int(m.group(1)) % 2 else []
            return httpx.Response(200, json={"formation_tops": [{"formation": f} for f in tops]})
        return httpx.Response(200, json={})


def _client(api: FakeApi) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(api), base_url="http://smriti.test")


def _corpus(tops: dict[int, tuple[str, ...]] | None = None) -> Any:
    return lt.Corpus(
        well_ids=tuple(range(1, 51)),
        wells_total=50,
        formations=("Barail", "Tipam Sandstone"),
        tops={3: ("Barail",), 7: ("Tipam Sandstone", "Barail")} if tops is None else tops,
    )


def test_percentile_is_nearest_rank() -> None:
    values = [float(v) for v in range(100, 0, -1)]  # unsorted on purpose
    assert lt.percentile(values, 50) == 50
    assert lt.percentile(values, 95) == 95
    assert lt.percentile(values, 99) == 99
    assert lt.percentile(values, 100) == 100
    assert lt.percentile(values, 0) == 1
    # Small samples: p95 of ten values is the largest, never an interpolated smaller one.
    assert lt.percentile([float(v) for v in range(1, 11)], 95) == 10
    assert lt.percentile([7.0], 99) == 7
    with pytest.raises(ValueError):
        lt.percentile([], 50)


def test_summary_times_the_successes_and_counts_errors_by_kind() -> None:
    samples = [lt.Sample("x", float(ms), 200) for ms in range(10, 110, 10)]
    samples += [
        lt.Sample("x", 5.0, 500),
        lt.Sample("x", 30000.0, None, "timeout"),
        lt.Sample("x", 2.0, 422),
        lt.Sample("x", 3.0, 500),
    ]
    s = lt.summarise(samples, wall_s=2.0)
    assert s["requests"] == 14
    assert s["errors"] == 4
    assert s["error_rate"] == round(4 / 14, 4)
    assert s["error_kinds"] == {"422": 1, "500": 2, "timeout": 1}
    assert s["throughput_rps"] == 7.0
    # Failed requests (fast 500s, the 30 s timeout) do not move the latency numbers.
    assert (s["p50_ms"], s["p95_ms"], s["p99_ms"], s["max_ms"]) == (50.0, 100.0, 100.0, 100.0)
    assert s["mean_ms"] == 55.0


def test_summary_without_a_success_has_no_latency() -> None:
    s = lt.summarise([lt.Sample("x", 1.0, 503)] * 3, wall_s=0.5)
    assert s["error_rate"] == 1.0
    assert s["p95_ms"] is None and s["p50_ms"] is None


def test_discovery_pages_the_wells_and_samples_formation_tops() -> None:
    api = FakeApi()

    async def go() -> Any:
        async with _client(api) as client:
            return await lt.discover(client)

    corpus = asyncio.run(go())
    assert corpus.wells_total == N_WELLS
    assert corpus.well_ids == tuple(range(1, N_WELLS + 1))
    assert corpus.formations == ("Barail", "Girujan Clay", "Tipam Sandstone")
    # Tops read for a sample of wells; only wells that have any are kept.
    assert sum(p.startswith("/api/v1/wells/") for p in api.paths) == lt.TOPS_SAMPLE
    assert corpus.tops and all(wid % 2 for wid in corpus.tops)
    assert set(corpus.tops.values()) == {("Tipam Sandstone", "Barail")}


def test_plan_is_seeded_and_covers_every_endpoint() -> None:
    corpus = _corpus()
    plan = lt.build_plan(corpus, 40)
    assert plan == lt.build_plan(corpus, 40)  # the same requests on every run
    assert plan != lt.build_plan(corpus, 40, seed=7)
    assert set(plan) == set(lt.ROUTES)
    assert set(lt.TARGETS_P95_MS) <= set(plan)
    assert all(len(reqs) == 40 for reqs in plan.values())
    for name, reqs in plan.items():
        assert all(r.endpoint == name and r.path.startswith("/api/v1/") for r in reqs)

    radii = [dict(r.params)["radius_km"] for r in plan["offsets_radius"][:4]]
    assert radii == ["1.0", "5.0", "10.0", "20.0"]
    assert all(dict(r.params)["mode"] == "SURFACE" for r in plan["offsets_radius"])

    # AT_FORMATION asks only for a formation the subject well has a top in.
    for r in plan["offsets_at_formation"]:
        wid = int(r.path.split("/")[4])
        assert dict(r.params)["formation"] in corpus.tops[wid]

    searches = [dict(r.params) for r in plan["search_hybrid"]]
    assert all(p["q"] for p in searches)
    assert any("well_id" in p for p in searches) and any("well_id" not in p for p in searches)
    assert all(("radius_km" in p) == ("well_id" in p) for p in searches)  # the API's rule

    for r in plan["correlation"]:
        wells = [v for k, v in r.params if k == "wells"]
        assert 3 <= len(wells) <= 5 and len(set(wells)) == len(wells)

    assert all(dict(r.params)["event_type"] in lt.EVENT_TYPES for r in plan["ledger"])


def test_plan_skips_at_formation_when_no_well_has_tops() -> None:
    plan = lt.build_plan(_corpus(tops={}), 5)
    assert "offsets_at_formation" not in plan
    assert "offsets_radius" in plan


def test_targets_pass_only_within_the_p95_and_without_errors() -> None:
    ok = {"p95_ms": 120.0, "errors": 0, "error_rate": 0.0}
    rows = lt.compare(
        {
            "offsets_radius": {"1": ok, "16": {"p95_ms": 640.0, "errors": 0, "error_rate": 0.0}},
            "search_hybrid": {"1": {"p95_ms": 900.0, "errors": 1, "error_rate": 0.02}},
            "ledger": {"1": ok},  # no §9 target
        }
    )
    verdicts = {(r["endpoint"], r["concurrency"]): r["pass"] for r in rows}
    assert verdicts == {
        ("offsets_radius", 1): True,
        ("offsets_radius", 16): False,
        ("search_hybrid", 1): False,
    }
    assert {r["target_p95_ms"] for r in rows} == {500.0, 1500.0}


def test_a_run_is_read_only_and_measures_every_endpoint_at_every_level() -> None:
    api = FakeApi(fail={"/api/v1/search": 503}, delay_s=0.002)

    async def go() -> dict[str, Any]:
        async with _client(api) as client:
            return await lt.measure(client, levels=(1, 4), n=12, warmup=2)

    body = asyncio.run(go())
    assert api.methods == {"GET"}
    assert api.peak <= 4  # never more in flight than the highest level
    assert api.peak == 4  # ... and the level is really reached
    assert body["corpus"]["wells_total"] == N_WELLS
    assert set(body["endpoints"]) == set(lt.ROUTES)
    for name, entry in body["endpoints"].items():
        assert entry["route"] == lt.ROUTES[name]
        assert set(entry["results"]) == {"1", "4"}
        assert all(level["requests"] == 12 for level in entry["results"].values())
    # 2 warm-up + 12 per level (x2) for each of the eight endpoints, after the discovery calls.
    measured = [p for p in api.paths if p not in ("/api/v1/wells", "/api/v1/formations")]
    assert len(measured) == lt.TOPS_SAMPLE + len(lt.ROUTES) * (2 + 2 * 12)

    search = body["endpoints"]["search_hybrid"]["results"]["4"]
    assert search["error_rate"] == 1.0 and search["error_kinds"] == {"503": 12}
    radius = body["endpoints"]["offsets_radius"]["results"]["1"]
    assert radius["errors"] == 0 and radius["p95_ms"] is not None
    verdicts = {(t["endpoint"], t["concurrency"]): t["pass"] for t in body["targets"]}
    assert verdicts == {
        ("offsets_radius", 1): True,
        ("offsets_radius", 4): True,
        ("search_hybrid", 1): False,
        ("search_hybrid", 4): False,
    }


def test_timeouts_and_connection_errors_count_as_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("k") == "slow":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("refused", request=request)

    async def go() -> list[Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reqs = [lt.Request("x", "http://smriti.test/a", (("k", k),)) for k in ("slow", "no")]
            samples, _ = await lt.run_level(client, reqs, 2)
            return samples

    samples = asyncio.run(go())
    assert sorted(s.error for s in samples) == ["ConnectError", "timeout"]
    assert not any(s.ok for s in samples)


def test_main_writes_the_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeApi()
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(api), **kw)
    )
    out = tmp_path / "loadtest.json"
    lt.main(["--levels", "1,2", "--requests", "3", "--warmup", "1", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["what"].startswith("Read-only API latency")
    assert report["levels"] == [1, 2]
    assert report["auth"] == "none (dev mode)"
    assert report["corpus"]["wells_total"] == N_WELLS
    assert {t["endpoint"] for t in report["targets"]} == set(lt.TARGETS_P95_MS)
    assert all(t["pass"] for t in report["targets"])
    assert report["notes"]


def test_main_rejects_non_positive_levels() -> None:
    with pytest.raises(SystemExit):
        lt.main(["--levels", "0,4"])
