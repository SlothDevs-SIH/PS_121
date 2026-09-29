"""B5 Offset Risk Brief and analytics against the seeded database, in-process.

The brief's content is checked against the API it summarises (offsets, risk profile); the
analytics totals are recomputed from /events and the alert feedback."""

from collections import Counter
from collections.abc import Iterator

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.auth import CurrentUser, get_current_user
from app.db.models.auth import AuditLog
from app.db.session import session_scope
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _pdf_text(body: bytes) -> str:
    doc = pdfium.PdfDocument(body)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_brief_covers_the_offsets_and_risks_it_summarises(client: TestClient) -> None:
    well = client.get("/api/v1/wells", params={"status": "drilling", "limit": 1}).json()["items"]
    well = well[0] if well else client.get("/api/v1/wells", params={"limit": 1}).json()["items"][0]
    r = client.get(f"/api/v1/reports/offset-brief/{well['id']}", params={"radius_km": 5})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    text = _pdf_text(r.content)
    assert f"Offset Risk Brief: {well['name']}" in text
    assert "SYNTHETIC DATA - NOT OIL INDIA DATA" in text
    assert "not proven to cause" in text
    offsets = client.get(f"/api/v1/wells/{well['id']}/offsets", params={"radius_km": 5}).json()
    drilled = [o["name"] for o in offsets["offsets"] if o["status"] != "planned"]
    assert all(name in text for name in drilled[:25])
    profile = client.get(f"/api/v1/wells/{well['id']}/risk-profile").json()
    for iv in profile["intervals"]:
        if iv["risks"] and iv["risks"][0]["probability"] >= 0.1:
            assert iv["formation"] in text
    with session_scope() as s:
        row = s.scalars(
            select(AuditLog).where(AuditLog.action == "brief_download").order_by(AuditLog.id.desc())
        ).first()
    assert row is not None and row.target_id == str(well["id"])


def test_brief_needs_read_risk() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="v", name="V", roles=["viewer"]
    )
    assert TestClient(app).get("/api/v1/reports/offset-brief/1").status_code == 403


def test_npt_totals_match_the_events_api(client: TestClient) -> None:
    events = client.get("/api/v1/events", params={"limit": 500}).json()["items"]
    by_type = Counter[str]()
    for e in events:
        by_type[e["event_type"]] += e["npt_hours"] or 0
    body = client.get("/api/v1/analytics/npt").json()
    assert body["total_events"] == len(events)
    assert body["total_npt_hours"] == pytest.approx(sum(by_type.values()), abs=0.2)
    for row in body["rows"]:
        assert row["npt_hours"] == pytest.approx(by_type[row["key"]], abs=0.1)
    assert [r["npt_hours"] for r in body["rows"]] == sorted(
        (r["npt_hours"] for r in body["rows"]), reverse=True
    )
    years = client.get("/api/v1/analytics/npt", params={"group_by": "year"}).json()
    assert sum(r["events"] for r in years["rows"]) == len(events)


def test_recurring_rows_respect_min_wells(client: TestClient) -> None:
    body = client.get("/api/v1/analytics/recurring", params={"min_wells": 2}).json()
    for row in body["across_wells"]:
        assert row["wells"] >= 2 and row["events"] >= row["wells"]
        ev = client.get(f"/api/v1/events/{row['event_ids'][0]}").json()
        assert ev["event_type"] == row["event_type"] and ev["formation"] == row["formation"]
    for row in body["within_wells"]:
        assert row["events"] >= 2


def test_alert_precision_counts_the_latest_verdict(client: TestClient) -> None:
    alerts = client.get("/api/v1/alerts", params={"limit": 500}).json()["items"]
    latest = [a["feedback"][-1]["verdict"] for a in alerts if a["feedback"]]
    body = client.get("/api/v1/analytics/alerts").json()
    assert body["alerts"] == len(alerts)
    assert body["precision"]["n"] == len(latest)
    assert body["precision"]["k"] == latest.count("useful")
    if body["precision"]["n"]:
        p = body["precision"]
        assert p["ci90_low"] <= p["mean"] <= p["ci90_high"]
