"""The skeleton must expose every endpoint in master plan §8, each with a 501 envelope.

B2 routes are contract-only in this revision: they validate their inputs (422) and answer
501 with phase B2. The implementers replace the 501 cases with behaviour tests.
"""

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
    ("get", "/api/v1/documents"),
    ("get", "/api/v1/documents/{document_id}/pages/{page_no}/image"),
    ("get", "/api/v1/documents/{document_id}/file"),
    ("post", "/api/v1/documents/{document_id}/reprocess"),
    ("get", "/api/v1/formations"),
    ("get", "/api/v1/meta"),
    ("get", "/api/v1/me"),
    ("get", "/healthz"),
    ("get", "/readyz"),
    # B2 knowledge layer (docs/SPEC_RECONCILIATION.md §2)
    ("get", "/api/v1/events/{event_id}"),
    ("post", "/api/v1/events"),
    ("patch", "/api/v1/events/{event_id}/verify"),
    ("get", "/api/v1/wells/{well_id}/events/timeline"),
    ("get", "/api/v1/correlation/formation-stats"),
    ("get", "/api/v1/wells/{well_id}/trajectory/at-depth"),
    ("post", "/api/v1/wells/{well_id}/trajectory"),
}

# Response schema of every B2 route (the frontend's generated types depend on these names).
B2_RESPONSE_MODELS = {
    ("get", "/api/v1/events"): "EventPage",
    ("get", "/api/v1/events/{event_id}"): "EventDetail",
    ("post", "/api/v1/events"): "EventDetail",
    ("patch", "/api/v1/events/{event_id}/verify"): "EventDetail",
    ("get", "/api/v1/wells/{well_id}/events/timeline"): "EventTimeline",
    ("get", "/api/v1/review-queue"): "ReviewPage",
    ("post", "/api/v1/review-queue/{item_id}"): "ReviewItem",
    ("get", "/api/v1/search"): "SearchResponse",
    ("get", "/api/v1/correlation"): "CorrelationPanel",
    ("get", "/api/v1/correlation/formation-stats"): "FormationStats",
    ("get", "/api/v1/wells/{well_id}/trajectory/at-depth"): "TrajectoryAtDepth",
    ("post", "/api/v1/wells/{well_id}/trajectory"): "TrajectoryOut",
    ("get", "/api/v1/wells/{well_id}/offsets"): "OffsetsOut",
    ("get", "/api/v1/wells/{well_id}"): "WellDetail",
}

EVENT_BODY = {
    "well_id": 3,
    "event_type": "LOSS",
    "severity": "high",
    "md_m": 1850.0,
    "mw_sg": 1.32,
    "params": {"loss_rate_m3_h": 12.5, "total_loss_m3": 40.0},
    "mitigations": [{"action_code": "LCM_PILL_COARSE", "outcome": "success"}],
    "evidence": [{"document_id": 5, "page_no": 2, "span_ids": [101, 102]}],
}
STATIONS = [
    {"md_m": 0, "inc_deg": 0, "azi_deg": 0},
    {"md_m": 500, "inc_deg": 12.5, "azi_deg": 45},
]
SURVEY_BODY = {"stations": STATIONS, "azi_ref": "true"}


def test_openapi_contains_every_planned_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    exposed = {(m, p) for p, ops in paths.items() for m in ops}
    missing = PLANNED_HTTP - exposed
    assert not missing, f"missing endpoints: {sorted(missing)}"


@pytest.mark.parametrize(("method", "path"), sorted(B2_RESPONSE_MODELS))
def test_b2_routes_declare_their_response_model(client: TestClient, method: str, path: str) -> None:
    op = client.get("/openapi.json").json()["paths"][path][method]
    ok = next(v for k, v in op["responses"].items() if k.startswith("2"))
    ref = ok["content"]["application/json"]["schema"]["$ref"]
    assert ref == f"#/components/schemas/{B2_RESPONSE_MODELS[(method, path)]}"
    assert op.get("summary")


@pytest.mark.parametrize(
    ("method", "url", "body", "phase"),
    [
        # B2: the contract exists; implementers replace these with behaviour tests.
        ("get", "/api/v1/events", None, "B2"),
        (
            "get",
            "/api/v1/events?event_type=LOSS&event_type=STUCK&formation=Barail&well_id=3"
            "&radius_km=5&tvdss_from_m=1000&tvdss_to_m=2500&date_from=2019-01-01"
            "&date_to=2020-12-31&verified=true&min_confidence=0.75&limit=20&cursor=abc",
            None,
            "B2",
        ),
        ("get", "/api/v1/events/42", None, "B2"),
        ("post", "/api/v1/events", EVENT_BODY, "B2"),
        ("patch", "/api/v1/events/42/verify", {"verified": True}, "B2"),
        ("patch", "/api/v1/events/42/verify", {"verified": False, "status": "rejected"}, "B2"),
        ("get", "/api/v1/wells/7/events/timeline", None, "B2"),
        ("get", "/api/v1/review-queue", None, "B2"),
        (
            "get",
            "/api/v1/review-queue?status=accepted&kind=event&document_id=4&limit=10",
            None,
            "B2",
        ),
        ("post", "/api/v1/review-queue/9", {"action": "accept"}, "B2"),
        ("post", "/api/v1/review-queue/9", {"action": "correct", "fields": {"md_m": 1850}}, "B2"),
        ("post", "/api/v1/review-queue/9", {"action": "reject", "reason": "not an event"}, "B2"),
        ("get", "/api/v1/search?q=lost%20circulation", None, "B2"),
        (
            "get",
            "/api/v1/search?q=losses&well_id=3&radius_km=10&formation=Tipam&event_type=LOSS"
            "&doc_type=DDR&date_from=2019-01-01&date_to=2020-01-01&limit=50",
            None,
            "B2",
        ),
        ("get", "/api/v1/correlation?wells=1&wells=2&align=TVDSS", None, "B2"),
        ("get", "/api/v1/correlation?wells=1&wells=2&align=FLATTEN_ON_TOP&top=Barail", None, "B2"),
        ("get", "/api/v1/correlation?wells=1&align=FORMATION_RELATIVE", None, "B2"),
        ("get", "/api/v1/correlation/formation-stats?wells=1&wells=2", None, "B2"),
        ("get", "/api/v1/correlation/formation-stats?well_id=1&radius_km=5", None, "B2"),
        ("get", "/api/v1/wells?bbox=94.9,27.1,95.4,27.6", None, "B2"),
        ("get", "/api/v1/wells?fluid_type=gas", None, "B2"),
        ("get", "/api/v1/wells/7/trajectory/at-depth?md_m=1234.5", None, "B2"),
        ("post", "/api/v1/wells/7/trajectory", SURVEY_BODY, "B2"),
        (
            "post",
            "/api/v1/wells/7/trajectory",
            {"stations": STATIONS, "azi_ref": "magnetic", "correction_deg": -0.8},
            "B2",
        ),
        (
            "get",
            "/api/v1/wells/7/offsets?radius_km=5&mode=AT_FORMATION&formation=Barail",
            None,
            "B2",
        ),
        ("get", "/api/v1/wells/7/offsets?mode=AT_FORMATION", None, "B2"),
        (
            "get",
            "/api/v1/wells/7/offsets?mode=CLOSEST_APPROACH&tvdss_from_m=1000&tvdss_to_m=2000",
            None,
            "B2",
        ),
        ("get", "/api/v1/wells/7/offsets?mode=CLOSEST_APPROACH", None, "B2"),
        # Later phases
        ("get", "/api/v1/wells/7/risk-profile", None, "B3"),
        ("get", "/api/v1/ledger?event_type=LOSS", None, "B3"),
        ("get", "/api/v1/alerts", None, "B4"),
        ("post", "/api/v1/replay", None, "B4"),
        ("post", "/api/v1/copilot/chat", None, "B5"),
    ],
)
def test_skeleton_routes_return_501_with_phase(
    client: TestClient, method: str, url: str, body: object, phase: str
) -> None:
    r = client.request(method, url, json=body)
    assert r.status_code == 501, r.text
    err = r.json()["error"]
    assert err["code"] == "not_implemented"
    assert err["details"]["phase"] == phase
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_validation_uses_error_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/wells/7/offsets?radius_km=-1")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        # field-level rules (FastAPI / Pydantic)
        ("get", "/api/v1/events?event_type=MUD_LOSS", None),
        ("get", "/api/v1/events?min_confidence=1.5", None),
        ("get", "/api/v1/events?limit=501", None),
        ("get", "/api/v1/search", None),
        ("get", "/api/v1/search?q=", None),
        ("get", "/api/v1/search?q=x&limit=51", None),
        ("get", "/api/v1/correlation", None),
        ("get", "/api/v1/correlation?" + "&".join(f"wells={i}" for i in range(21)), None),
        ("get", "/api/v1/correlation?wells=1&align=DEPTH", None),
        ("get", "/api/v1/review-queue?status=done", None),
        ("get", "/api/v1/review-queue?kind=formation", None),
        ("get", "/api/v1/wells?fluid_type=steam", None),
        ("get", "/api/v1/wells/7/trajectory/at-depth", None),
        ("get", "/api/v1/wells/7/trajectory/at-depth?md_m=-5", None),
        ("post", "/api/v1/events", {**EVENT_BODY, "event_type": "mud_loss"}),
        ("post", "/api/v1/events", {**EVENT_BODY, "params": {"loss_rate_bbl_h": 3}}),
        ("post", "/api/v1/events", {**EVENT_BODY, "mw_sg": 11.0}),
        ("post", "/api/v1/events", {**EVENT_BODY, "unknown_field": 1}),
        (
            "post",
            "/api/v1/events",
            {**EVENT_BODY, "mitigations": [{"action_code": "PRAY", "outcome": "success"}]},
        ),
        (
            "post",
            "/api/v1/events",
            {**EVENT_BODY, "t_start": "2020-01-02T10:00:00Z", "t_end": "2020-01-02T09:00:00Z"},
        ),
        ("patch", "/api/v1/events/42/verify", {"verified": True, "status": "deleted"}),
        ("post", "/api/v1/review-queue/9", {"action": "approve"}),
        ("post", "/api/v1/review-queue/9", {"action": "correct", "fields": {}}),
        ("post", "/api/v1/review-queue/9", {"action": "reject"}),
        ("post", "/api/v1/wells/7/trajectory", {"stations": STATIONS[:1]}),
        ("post", "/api/v1/wells/7/trajectory", {"stations": list(reversed(STATIONS))}),
        ("post", "/api/v1/wells/7/trajectory", {**SURVEY_BODY, "azi_ref": "magnetic"}),
        (
            "post",
            "/api/v1/wells/7/trajectory",
            {"stations": [*STATIONS, {"md_m": 900, "inc_deg": 10, "azi_deg": 360}]},
        ),
        # cross-parameter rules (app.api.v1.params)
        ("get", "/api/v1/events?radius_km=5", None),
        ("get", "/api/v1/events?tvdss_from_m=2000&tvdss_to_m=1000", None),
        ("get", "/api/v1/events?date_from=2021-01-01&date_to=2020-01-01", None),
        ("get", "/api/v1/search?q=x&radius_km=5", None),
        ("get", "/api/v1/search?q=x&date_from=2021-01-01&date_to=2020-01-01", None),
        ("get", "/api/v1/correlation?wells=1&align=FLATTEN_ON_TOP", None),
        ("get", "/api/v1/correlation/formation-stats", None),
        ("get", "/api/v1/correlation/formation-stats?wells=1&well_id=2", None),
        ("get", "/api/v1/correlation/formation-stats?wells=1&radius_km=5", None),
        ("get", "/api/v1/wells?bbox=1,2,3", None),
        ("get", "/api/v1/wells?bbox=95.4,27.1,94.9,27.6", None),
        ("get", "/api/v1/wells?bbox=a,b,c,d", None),
        ("get", "/api/v1/wells?bbox=0,-91,1,1", None),
        ("get", "/api/v1/wells/7/offsets?mode=CLOSEST_APPROACH&tvdss_from_m=9&tvdss_to_m=1", None),
    ],
)
def test_b2_contract_rejects_invalid_input(
    client: TestClient, method: str, url: str, body: object
) -> None:
    r = client.request(method, url, json=body)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"]["errors"]


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
