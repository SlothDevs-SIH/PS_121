"""B6 metrics: GET /metrics (outside the OpenAPI contract), and every custom metric moves when
its code path runs: ingestion, extraction, scoring, the alert engine and the WebSockets.
The worker's multiprocess mode and the side servers are checked without a stack."""

import asyncio
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.alerts.engine import AlertEngine, Candidate, Decision, Tracked
from app.core import metrics
from app.db.models import Document
from app.db.models.realtime import Alert
from app.extract.drafts import CasingDraft, Line, MudDraft
from app.extract.service import _Writer
from app.ingest import pages as ingest_pages
from app.ingest import service as ingest
from app.stream import service as stream

BACKEND = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 3, 1, 6, tzinfo=UTC)


def _value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


class _FakeSession:
    """Just enough of a SQLAlchemy session for code paths that only add and flush."""

    def __init__(self, get: Any = None) -> None:
        self._get = get
        self.added: list[Any] = []
        self._next_id = 100

    def get(self, _model: Any, _id: int) -> Any:
        return self._get

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", 0) is None:
                self._next_id += 1
                obj.id = self._next_id

    def execute(self, *_: Any, **__: Any) -> None:
        return None

    def scalar(self, *_: Any, **__: Any) -> int:
        return 0  # "no such record yet"


# ─── API ─────────────────────────────────────────────────────────────────────────────────


def test_metrics_endpoint_serves_route_and_custom_metrics(client: TestClient) -> None:
    client.get("/healthz")
    client.get("/api/v1/wells/7/offsets?radius_km=-1")  # 422, by its route template
    client.get("/no/such/path/12345")  # 404, no route
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert (
        'http_requests_total{handler="/api/v1/wells/{well_id}/offsets",method="GET",status="4xx"}'
        in body
    )
    assert 'http_request_duration_seconds_bucket{handler="/api/v1/wells/{well_id}/offsets"' in body
    assert 'handler="none"' in body  # unmatched paths are grouped, not one series per path
    assert "/no/such/path" not in body
    for probe in ("/healthz", "/readyz", "/metrics"):
        assert f'handler="{probe}"' not in body
    for name in (
        "smriti_ingest_pages_total",
        "smriti_ingest_documents_total",
        "smriti_extraction_confidence",
        "smriti_stream_scoring_lag_seconds",
        "smriti_stream_samples_scored_total",
        "smriti_alerts_raised_total",
        "smriti_alert_candidates_suppressed_total",
        "smriti_websocket_clients",
    ):
        assert f"# TYPE {name.removesuffix('_total')}" in body, name
    assert 'smriti_websocket_clients{endpoint="/ws/alerts"} 0.0' in body


def test_metrics_endpoint_is_not_part_of_the_api_contract(client: TestClient) -> None:
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_metrics_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setenv("SMRITI_METRICS_ENABLED", "false")
    assert TestClient(create_app()).get("/metrics").status_code == 404


# ─── Ingestion and extraction (worker) ───────────────────────────────────────────────────


def test_ingestion_counts_pages_by_method_and_documents_by_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def page(no: int, ocr: bool) -> ingest_pages.PageContent:
        line = ingest_pages.Line(f"page {no} text", [0.1, 0.1, 0.9, 0.2], 90.0 if ocr else None)
        return ingest_pages.PageContent(no, 100, 100, b"png", ocr, 90.0 if ocr else None, [line])

    s3 = SimpleNamespace(
        get_object=lambda **_: {"Body": io.BytesIO(b"\x89PNG")}, put_object=lambda **_: None
    )
    monkeypatch.setattr(ingest, "get_s3_client", lambda: s3)
    monkeypatch.setattr(ingest, "extract_image", lambda _: [page(1, True), page(2, True)])
    monkeypatch.setattr(ingest, "extract_pdf", lambda _: [page(1, False)])
    ocr, text = (
        _value("smriti_ingest_pages_total", method="ocr"),
        _value("smriti_ingest_pages_total", method="text"),
    )
    review = _value("smriti_ingest_documents_total", status="needs_review")

    scan = Document(id=1, object_key="k", content_type="image/png", filename="scan.png")
    ingest.process_document(_FakeSession(scan), 1)  # type: ignore[arg-type]
    pdf = Document(id=2, object_key="k", content_type="application/pdf", filename="r.pdf")
    ingest.process_document(_FakeSession(pdf), 2)  # type: ignore[arg-type]

    assert _value("smriti_ingest_pages_total", method="ocr") == ocr + 2
    assert _value("smriti_ingest_pages_total", method="text") == text + 1
    # No well name on these pages: both documents wait for review.
    assert _value("smriti_ingest_documents_total", status="needs_review") == review + 2

    failed = _value("smriti_ingest_documents_total", status="failed")
    ingest.mark_failed(_FakeSession(Document(id=3)), 3, "boom")  # type: ignore[arg-type]
    assert _value("smriti_ingest_documents_total", status="failed") == failed + 1


def test_extraction_observes_the_confidence_of_each_record() -> None:
    ctx = SimpleNamespace(wellbore_id=5, depth_refs=lambda _md: (None, None))
    doc = Document(id=9)
    writer = _Writer(_FakeSession(), doc, ctx, None, threshold=0.75)  # type: ignore[arg-type]
    before = {k: _value("smriti_extraction_confidence_count", kind=k) for k in ("mud", "casing")}
    low = _value("smriti_extraction_confidence_bucket", kind="mud", le="0.6")

    scanned = [Line(span_id=1, page_no=3, text="mud 1.30 sg", conf=55.0)]  # OCR at 55 %
    writer.mud(MudDraft(1000, 1500, 12.25, "WBM", 1.3, scanned))
    writer.casing(CasingDraft(9.625, 12.25, 1500, 900, "full", [Line(2, 3, "9 5/8 casing")]))

    assert _value("smriti_extraction_confidence_count", kind="mud") == before["mud"] + 1
    assert _value("smriti_extraction_confidence_bucket", kind="mud", le="0.6") == low + 1
    assert _value("smriti_extraction_confidence_count", kind="casing") == before["casing"] + 1
    assert writer.reviews == 1  # the OCR'd mud interval, below the 0.75 threshold


# ─── Stream service: scoring lag and alerts ──────────────────────────────────────────────


def _candidate(**over: Any) -> Candidate:
    base: dict[str, Any] = {
        "alert_type": "ANOMALY_ML",
        "event_type": "LOSS",
        "severity": "warning",
        "score": 0.8,
        "score_kind": "probability",
        "t_data": T0,
        "title": "Losses likely",
        "message": "m",
        "tvdss_m": 1800.0,
        "evidence": [{"kind": "indicator", "name": "flow_imbalance_pct"}],
    }
    return Candidate(**{**base, **over})


def _live() -> Any:
    scorer = SimpleNamespace(ctx=SimpleNamespace(wellbore_id=5))
    return stream._Live(session_id=1, well_id=7, scorer=scorer, engine=AlertEngine())  # type: ignore[arg-type]


def test_alert_engine_outcomes_are_counted_by_type_severity_and_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stream, "_enrich", lambda _s, ev: ev)
    monkeypatch.setattr(stream, "recommendations", lambda *_: ([], None))
    created = ("ANOMALY_ML", "warning", "created")
    fused = ("PHYSICS", "critical", "fused")

    def raised(key: tuple[str, str, str]) -> float:
        t, sev, action = key
        return _value("smriti_alerts_raised_total", alert_type=t, severity=sev, action=action)

    base = {k: raised(k) for k in (created, fused)}
    budget = _value("smriti_alert_candidates_suppressed_total", reason="budget")
    live = _live()

    assert stream.store_candidate(
        _FakeSession(), live, _candidate(), Decision("create", "new"), time.time()
    ) == (101, "created")
    alert = Alert(
        id=101, severity="warning", sources=["ANOMALY_ML"], evidence=[], drivers=[], detail={}
    )
    target = Tracked(101, "LOSS", 1800.0, T0, {"ANOMALY_ML"}, "warning", False)
    c = _candidate(alert_type="PHYSICS", severity="critical")
    assert stream.store_candidate(
        _FakeSession(alert), live, c, Decision("fuse", "agrees", target), time.time()
    ) == (101, "fused")
    assert (
        stream.store_candidate(
            _FakeSession(), live, _candidate(), Decision("suppress", "budget"), time.time()
        )
        is None
    )

    assert raised(created) == base[created] + 1
    assert raised(fused) == base[fused] + 1
    assert _value("smriti_alert_candidates_suppressed_total", reason="budget") == budget + 1


def test_scoring_sets_the_lag_from_publish_to_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[_FakeSession]:
        yield _FakeSession()

    monkeypatch.setattr(stream, "session_scope", scope)
    frame = SimpleNamespace(
        rig_state="DRILLING",
        bit_depth_m=1500.0,
        formation=None,
        indicators={},
        scores=None,
        dejavu=None,
        to_json=lambda: {"ts": T0.isoformat()},
    )
    live = _live()
    live.scorer.push = lambda _ts, _v: (frame, [])
    live.scorer.latest_scores = {}
    xadds: list[str] = []
    consumer = stream.Consumer(SimpleNamespace(xadd=lambda key, *_a, **_k: xadds.append(key)))  # type: ignore[arg-type]
    consumer.live[5] = live
    scored = _value("smriti_stream_samples_scored_total")

    now = time.time()
    msgs = [
        (f"{i}-0", {"sid": "1", "ts": T0.isoformat(), "v": json.dumps({}), "pub": str(now - lag)})
        for i, lag in enumerate((9.0, 2.5))
    ]
    consumer._score(5, msgs)

    lag = _value("smriti_stream_scoring_lag_seconds")
    assert 2.5 <= lag < 5  # the newest sample of the batch, not the oldest
    assert _value("smriti_stream_samples_scored_total") == scored + 2
    assert xadds == ["scores:5", "scores:5"]


# ─── WebSockets (API) ────────────────────────────────────────────────────────────────────


class _IdleRedis:
    async def xread(self, *_: Any, block: int = 0, **__: Any) -> list[Any]:
        await asyncio.sleep(0.01)
        return []

    async def aclose(self) -> None:
        return None


def test_websocket_clients_gauge_follows_connections(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.routes import ws

    monkeypatch.setattr(ws, "_authorise", lambda _token: None)
    monkeypatch.setattr(ws, "_redis", _IdleRedis)
    monkeypatch.setattr(ws, "_wellbore_and_session", lambda _well: (5, None))
    alerts0 = _value("smriti_websocket_clients", endpoint=metrics.WS_ALERTS)
    live0 = _value("smriti_websocket_clients", endpoint=metrics.WS_LIVE)

    with client.websocket_connect("/ws/alerts") as a:
        assert a.receive_json()["type"] == "hello"
        assert _value("smriti_websocket_clients", endpoint=metrics.WS_ALERTS) == alerts0 + 1
        with client.websocket_connect("/ws/wells/3/live") as w:
            assert w.receive_json()["type"] == "hello"
            assert _value("smriti_websocket_clients", endpoint=metrics.WS_LIVE) == live0 + 1
    assert _value("smriti_websocket_clients", endpoint=metrics.WS_ALERTS) == alerts0
    assert _value("smriti_websocket_clients", endpoint=metrics.WS_LIVE) == live0


def test_refused_websocket_is_not_counted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.routes import ws

    monkeypatch.setattr(ws, "_authorise", lambda _token: ws.WS_UNAUTHENTICATED)
    before = _value("smriti_websocket_clients", endpoint=metrics.WS_ALERTS)
    with client.websocket_connect("/ws/alerts") as a:
        assert a.receive_json()["type"] == "error"
        assert _value("smriti_websocket_clients", endpoint=metrics.WS_ALERTS) == before


# ─── Worker and stream: their own metrics servers ────────────────────────────────────────


def _taken_port() -> socket.socket:
    """A listening socket no one else may bind (Windows' SO_REUSEADDR would allow it)."""
    s = socket.socket()
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s


def test_side_process_serves_metrics_and_survives_a_taken_port() -> None:
    with _taken_port() as blocker:
        taken = blocker.getsockname()[1]
        assert metrics.serve(taken, addr="127.0.0.1") is None  # logged, not raised
    server = metrics.serve(0, addr="127.0.0.1")  # any free port
    assert server is not None
    try:
        url = f"http://127.0.0.1:{server.server_port}/metrics"
        with urllib.request.urlopen(url, timeout=5) as r:
            assert b"smriti_stream_scoring_lag_seconds" in r.read()
    finally:
        server.shutdown()
        server.server_close()


_WORKER = """
import os
from app.workers.celery_app import celery_app
celery_app.loader.import_default_modules()  # what `celery worker` does before forking
from prometheus_client import values
from app.core import metrics
metrics.record_pages([True, True, False])
print(os.environ["PROMETHEUS_MULTIPROC_DIR"], values.ValueClass.__name__)
"""
# A pool child inherits the main process's environment and imports; it only records.
_CHILD = """
from app.core import metrics
metrics.record_pages([True, True, False])
"""


def _python(script: str, env: dict[str, str]) -> list[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout.split()


def test_worker_children_write_metrics_the_main_process_aggregates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Processes write files; the worker's registry adds them up (no fork on every OS, so
    separate processes stand in for the pool's children)."""
    stale = tmp_path / "counter_1.db"
    stale.write_bytes(b"left over from the last run")
    env = {**os.environ, "SMRITI_ENV": "test", "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    path, value_class = _python(_WORKER, env)
    assert path == str(tmp_path)
    assert value_class == "MmapedValue"  # file-backed values, not the in-memory MutexValue
    assert not stale.exists()
    _python(_CHILD, env)

    monkeypatch.setenv(metrics.MULTIPROC_ENV, str(tmp_path))
    registry = metrics.registry_for_process()
    assert registry.get_sample_value("smriti_ingest_pages_total", {"method": "ocr"}) == 4
    assert registry.get_sample_value("smriti_ingest_pages_total", {"method": "text"}) == 2
