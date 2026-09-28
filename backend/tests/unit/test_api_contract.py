"""The skeleton must expose every endpoint in master plan §8, each with a 501 envelope."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.v1.routes.ws import WS_NOT_IMPLEMENTED

PLANNED_HTTP = {
    ("post", "/api/v1/documents"),
    ("get", "/api/v1/documents/{document_id}"),
    ("get", "/api/v1/documents/{document_id}/pages/{page_no}"),
    ("get", "/api/v1/review-queue"),
    ("post", "/api/v1/review-queue/{item_id}"),
    ("get", "/api/v1/wells"),
    ("get", "/api/v1/wells/{well_id}"),
    ("get", "/api/v1/wells/{well_id}/offsets"),
    ("get", "/api/v1/wells/{well_id}/trajectory"),
    ("get", "/api/v1/correlation"),
    ("get", "/api/v1/wells/{well_id}/risk-profile"),
    ("get", "/api/v1/events"),
    ("get", "/api/v1/search"),
    ("get", "/api/v1/ledger"),
    ("post", "/api/v1/copilot/chat"),
    ("get", "/api/v1/alerts"),
    ("post", "/api/v1/alerts/{alert_id}/ack"),
    ("post", "/api/v1/alerts/{alert_id}/dismiss"),
    ("post", "/api/v1/alerts/{alert_id}/feedback"),
    ("post", "/api/v1/replay"),
    ("get", "/api/v1/reports/offset-brief/{well_id}"),
    ("get", "/api/v1/meta"),
    ("get", "/api/v1/me"),
    ("get", "/healthz"),
    ("get", "/readyz"),
}


def test_openapi_contains_every_planned_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    exposed = {(m, p) for p, ops in paths.items() for m in ops}
    missing = PLANNED_HTTP - exposed
    assert not missing, f"missing endpoints: {sorted(missing)}"


@pytest.mark.parametrize(
    ("method", "url", "phase"),
    [
        ("get", "/api/v1/wells", "B1"),
        ("get", "/api/v1/wells/7/offsets?radius_km=5&mode=AT_FORMATION&formation=Barail", "B1"),
        ("get", "/api/v1/search?q=lost%20circulation", "B2"),
        ("get", "/api/v1/correlation?wells=1&wells=2&align=FLATTEN_ON_TOP", "B2"),
        ("get", "/api/v1/wells/7/risk-profile", "B3"),
        ("get", "/api/v1/ledger?event_type=LOSS", "B3"),
        ("get", "/api/v1/alerts", "B4"),
        ("post", "/api/v1/replay", "B4"),
        ("post", "/api/v1/copilot/chat", "B5"),
    ],
)
def test_skeleton_routes_return_501_with_phase(
    client: TestClient, method: str, url: str, phase: str
) -> None:
    r = client.request(method, url)
    assert r.status_code == 501
    err = r.json()["error"]
    assert err["code"] == "not_implemented"
    assert err["details"]["phase"] == phase
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_validation_uses_error_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/wells/7/offsets?radius_km=-1")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_request_id_is_echoed_or_generated(client: TestClient) -> None:
    assert (
        client.get("/healthz", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )
    generated = client.get("/healthz").headers["X-Request-ID"]
    assert len(generated) == 32


@pytest.mark.parametrize("path", ["/ws/alerts", "/ws/wells/3/live"])
def test_websockets_close_with_not_implemented(client: TestClient, path: str) -> None:
    with client.websocket_connect(path) as ws:
        assert ws.receive_json()["error"]["code"] == "not_implemented"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == WS_NOT_IMPLEMENTED
