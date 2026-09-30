"""Prometheus metrics (B6): every SMRITI metric is defined here, in the default registry.

The API serves them at ``GET /metrics`` (not in the OpenAPI document, not proxied by the web
app's nginx); the Celery worker and the stream service, which are separate processes, serve
theirs with :func:`serve` on ``SMRITI_WORKER_METRICS_PORT`` / ``SMRITI_STREAM_METRICS_PORT``.
The worker's pool children write to files that its main process aggregates (prometheus_client
multiprocess mode, set up in ``app.workers.celery_app``).

Labels are low-cardinality only (a route template, a record kind, an alert type): never a
well, document or user id. Grafana's dashboard is ``infra/grafana/dashboards/``.
"""

import logging
import os
from wsgiref.simple_server import WSGIServer

from fastapi import FastAPI
from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    multiprocess,
    start_http_server,
)
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info

log = logging.getLogger("smriti.metrics")

MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"
# Not in the route-latency histograms or counters: the scrape itself and the probes.
UNMEASURED_ROUTES = ("/metrics", "/healthz", "/readyz")
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

# ─── API (HTTP) ────────────────────────────────────────────────────────────────────────────
# Same names and labels as the instrumentator's defaults, with buckets fine enough for a p95
# per route (the defaults are 0.1 / 0.5 / 1 s) and one set of objects shared by every app
# instance (tests build many).

HTTP_REQUESTS = Counter(
    "http_requests",
    "HTTP requests by method, status class and route template.",
    ["method", "status", "handler"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency to the first response byte, by method and route template.",
    ["method", "handler"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ─── Ingestion and extraction (worker) ─────────────────────────────────────────────────────

PAGES_INGESTED = Counter(
    "smriti_ingest_pages",
    "Report pages ingested; method=ocr for scanned pages read by Tesseract, else text.",
    ["method"],
)
DOCUMENTS_INGESTED = Counter(
    "smriti_ingest_documents",
    "Documents through ingestion, by outcome (processed, needs_review, failed).",
    ["status"],
)
EXTRACTION_CONFIDENCE = Histogram(
    "smriti_extraction_confidence",
    "Confidence (0..1) of each extracted record, by kind (event, mitigation, casing, mud).",
    ["kind"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)

# ─── Real time (stream service, API WebSockets) ────────────────────────────────────────────

SCORING_LAG = Gauge(
    "smriti_stream_scoring_lag_seconds",
    "Wall time from publishing a sample to scoring it, for the latest scored batch.",
)
SAMPLES_SCORED = Counter("smriti_stream_samples_scored", "Real-time samples scored.")
ALERTS_RAISED = Counter(
    "smriti_alerts_raised",
    "Alerts from the alert engine by source type and severity; action=created or fused.",
    ["alert_type", "severity", "action"],
)
ALERTS_SUPPRESSED = Counter(
    "smriti_alert_candidates_suppressed",
    "Alert candidates the engine held back, by reason (duplicate, cooldown, budget, ...).",
    ["reason"],
)
WS_CLIENTS = Gauge(
    "smriti_websocket_clients",
    "Open, authorised WebSocket connections by endpoint.",
    ["endpoint"],
    multiprocess_mode="livesum",
)
WS_LIVE = "/ws/wells/{well_id}/live"
WS_ALERTS = "/ws/alerts"

# Children that always exist, so dashboards show 0 rather than "no data".
for _method in ("text", "ocr"):
    PAGES_INGESTED.labels(method=_method)
for _endpoint in (WS_LIVE, WS_ALERTS):
    WS_CLIENTS.labels(endpoint=_endpoint)


def record_pages(ocr_flags: list[bool]) -> None:
    """One ingested document's pages (``True`` = the page needed OCR)."""
    ocr = sum(ocr_flags)
    PAGES_INGESTED.labels(method="ocr").inc(ocr)
    PAGES_INGESTED.labels(method="text").inc(len(ocr_flags) - ocr)


def _http_instrumentation(info: Info) -> None:
    method = info.method if info.method in _METHODS else "OTHER"
    HTTP_REQUESTS.labels(method, info.modified_status, info.modified_handler).inc()
    HTTP_LATENCY.labels(method, info.modified_handler).observe(
        info.modified_duration_without_streaming or info.modified_duration
    )


def instrument_api(app: FastAPI) -> None:
    """Count and time requests by route template and serve ``GET /metrics`` (not in OpenAPI).

    Paths no route matches are grouped as ``handler="none"``, so a scan cannot mint series.
    """
    Instrumentator(
        should_group_status_codes=True,
        should_group_untemplated=True,
        excluded_handlers=[f"^{p}$" for p in UNMEASURED_ROUTES],
    ).add(_http_instrumentation).instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )


def registry_for_process() -> CollectorRegistry:
    """This process's registry, or an aggregate of every process's files in multiprocess mode."""
    path = os.environ.get(MULTIPROC_ENV)
    if not path:
        return REGISTRY
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry, path=path)  # type: ignore[no-untyped-call]
    return registry


def serve(port: int, addr: str = "0.0.0.0") -> WSGIServer | None:  # noqa: S104 (in-container)
    """Serve this process's metrics on ``addr:port`` from a daemon thread.

    Never raises: if the port is taken (or not allowed) it logs and the process carries on
    without metrics, which must never stop ingestion or scoring.
    """
    try:
        server, _ = start_http_server(port, addr=addr, registry=registry_for_process())
    except OSError as exc:
        log.warning("metrics not served: cannot listen on %s:%s (%s)", addr, port, exc)
        return None
    log.info("metrics on :%s/metrics", port)
    return server
