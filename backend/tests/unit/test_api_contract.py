"""Every endpoint in master plan §8 is exposed; routes of later phases answer a 501 envelope
naming their phase. B2-B4 routes are implemented: here they are checked for their declared
response models and input validation (422); their behaviour (and the WebSockets') is covered
by tests/integration/test_b2.py, test_b3.py and test_b4.py against the seeded stack.
"""

import pytest
from fastapi.testclient import TestClient

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
    # B3 risk and ledger (docs/SPEC_RECONCILIATION.md §6)
    ("get", "/api/v1/wells/{well_id}/cementing-check"),
    # B4 real-time and alerts
    ("get", "/api/v1/alerts/{alert_id}"),
    ("get", "/api/v1/replay"),
    ("get", "/api/v1/stream/status"),
    ("get", "/api/v1/wells/{well_id}/realtime"),
    # B5 auth, users, audit
    ("post", "/api/v1/auth/login"),
    ("get", "/api/v1/users"),
    ("post", "/api/v1/users"),
    ("patch", "/api/v1/users/{user_id}"),
    ("get", "/api/v1/audit"),
    ("get", "/api/v1/analytics/npt"),
    ("get", "/api/v1/analytics/recurring"),
    ("get", "/api/v1/analytics/alerts"),
}

# Response schema of every built route (the frontend's generated types depend on these names).
RESPONSE_MODELS = {
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
    # B3
    ("get", "/api/v1/ledger"): "LedgerResponse",
    ("get", "/api/v1/wells/{well_id}/risk-profile"): "RiskProfile",
    ("get", "/api/v1/wells/{well_id}/cementing-check"): "CementingCheck",
    # B4
    ("get", "/api/v1/alerts"): "AlertPage",
    ("get", "/api/v1/alerts/{alert_id}"): "AlertOut",
    ("post", "/api/v1/alerts/{alert_id}/ack"): "AlertOut",
    ("post", "/api/v1/alerts/{alert_id}/dismiss"): "AlertOut",
    ("post", "/api/v1/alerts/{alert_id}/feedback"): "AlertFeedbackOut",
    ("post", "/api/v1/replay"): "ReplaySessionOut",
    ("get", "/api/v1/stream/status"): "StreamStatus",
    ("get", "/api/v1/wells/{well_id}/realtime"): "RealtimeWindow",
    # B5
    ("get", "/api/v1/me"): "Me",
    ("post", "/api/v1/auth/login"): "TokenOut",
    ("post", "/api/v1/users"): "UserOut",
    ("patch", "/api/v1/users/{user_id}"): "UserOut",
    ("get", "/api/v1/audit"): "AuditPage",
    ("post", "/api/v1/copilot/chat"): "CopilotAnswer",
    ("get", "/api/v1/analytics/npt"): "NptBreakdown",
    ("get", "/api/v1/analytics/recurring"): "RecurringProblems",
    ("get", "/api/v1/analytics/alerts"): "AlertQuality",
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


@pytest.mark.parametrize(("method", "path"), sorted(RESPONSE_MODELS))
def test_built_routes_declare_their_response_model(
    client: TestClient, method: str, path: str
) -> None:
    op = client.get("/openapi.json").json()["paths"][path][method]
    ok = next(v for k, v in op["responses"].items() if k.startswith("2"))
    ref = ok["content"]["application/json"]["schema"]["$ref"]
    assert ref == f"#/components/schemas/{RESPONSE_MODELS[(method, path)]}"
    assert op.get("summary")


def test_not_implemented_envelope_names_its_phase() -> None:
    """Every route is built since B5; the 501 envelope stays for future skeleton routes."""
    from app.core.errors import NotImplementedYetError
    from app.main import create_app

    app = create_app()

    @app.get("/api/v1/_future")
    def _future() -> None:
        raise NotImplementedYetError("Something later", "B7")

    r = TestClient(app).get("/api/v1/_future")
    assert r.status_code == 501, r.text
    err = r.json()["error"]
    assert err["code"] == "not_implemented"
    assert err["details"]["phase"] == "B7"
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
        ("get", "/api/v1/ledger", None),
        ("get", "/api/v1/ledger?event_type=MUD_LOSS", None),
        ("get", "/api/v1/ledger?event_type=LOSS&min_n=0", None),
        ("get", "/api/v1/ledger?event_type=LOSS&severity=extreme", None),
        ("get", "/api/v1/wells/7/risk-profile?radius_km=0", None),
        ("get", "/api/v1/wells/7/risk-profile?sigma_km=51", None),
        ("get", "/api/v1/wells/7/risk-profile?mode=CLOSEST_APPROACH", None),
        ("get", "/api/v1/wells/7/risk-profile?event_type=MUD_LOSS", None),
        ("get", "/api/v1/wells/7/cementing-check", None),
        ("get", "/api/v1/wells/7/cementing-check?shoe_md_m=2000", None),
        ("get", "/api/v1/wells/7/cementing-check?shoe_md_m=2000&slurry_density_sg=3.1", None),
        ("get", "/api/v1/wells/7/cementing-check?shoe_md_m=-1&slurry_density_sg=1.5", None),
        ("post", "/api/v1/replay", {"action": "start"}),
        ("post", "/api/v1/replay", {"well_id": 41, "speed": 0}),
        ("post", "/api/v1/replay", {"well_id": 41, "speed": 5000}),
        ("post", "/api/v1/replay", {"well_id": 41, "action": "rewind"}),
        ("post", "/api/v1/replay", {"well_id": 41, "extra": 1}),
        ("get", "/api/v1/alerts?status=open", None),
        ("get", "/api/v1/alerts?severity=high", None),
        ("get", "/api/v1/alerts?limit=501", None),
        ("post", "/api/v1/alerts/1/dismiss", {"reason": ""}),
        ("post", "/api/v1/alerts/1/dismiss", {}),
        ("post", "/api/v1/alerts/1/feedback", {"verdict": "great"}),
        ("get", "/api/v1/wells/7/realtime?minutes=0", None),
        ("get", "/api/v1/wells/7/realtime?max_points=5", None),
        ("post", "/api/v1/auth/login", {"username": "a"}),
        (
            "post",
            "/api/v1/users",
            {"username": "Bad Name", "name": "x", "password": "p" * 12, "roles": ["viewer"]},
        ),
        (
            "post",
            "/api/v1/users",
            {"username": "bob", "name": "x", "password": "short", "roles": ["viewer"]},
        ),
        (
            "post",
            "/api/v1/users",
            {"username": "bob", "name": "x", "password": "p" * 12, "roles": ["pilot"]},
        ),
        (
            "post",
            "/api/v1/users",
            {"username": "bob", "name": "x", "password": "p" * 12, "roles": []},
        ),
        ("patch", "/api/v1/users/1", {"roles": ["viewer"], "extra": 1}),
        ("get", "/api/v1/audit?limit=0", None),
        ("post", "/api/v1/copilot/chat", {"message": ""}),
        ("get", "/api/v1/analytics/npt?group_by=rig", None),
        ("get", "/api/v1/analytics/npt?event_type=MUD_LOSS", None),
        ("get", "/api/v1/analytics/recurring?min_wells=1", None),
        ("get", "/api/v1/reports/offset-brief/7?radius_km=0", None),
        ("post", "/api/v1/copilot/chat", {"message": "x" * 1001}),
        ("post", "/api/v1/copilot/chat", {"message": "hi", "tools": ["sql"]}),
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
        ("get", "/api/v1/ledger?event_type=LOSS&radius_km=5", None),
    ],
)
def test_contract_rejects_invalid_input(
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
