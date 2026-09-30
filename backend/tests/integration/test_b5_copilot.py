"""B5 copilot against the seeded database, in-process: SSE event order, citations that
resolve to real report pages, role-scoped tools, "no record" answers, and the audit row."""

import json
from collections.abc import Iterator

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


def _ask(c: TestClient, message: str, **kw: object) -> dict[str, object]:
    r = c.post("/api/v1/copilot/chat?stream=false", json={"message": message, **kw})
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_sse_stream_has_plan_tools_tokens_citations_done(client: TestClient) -> None:
    with client.stream(
        "POST", "/api/v1/copilot/chat", json={"message": "What worked for losses in the Tipam?"}
    ) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [
        (block.split("\n")[0].removeprefix("event: "), json.loads(block.split("data: ", 1)[1]))
        for block in body.strip().split("\n\n")
    ]
    kinds = [k for k, _ in events]
    assert kinds[0] == "plan" and kinds[-2:] == ["citations", "done"]
    assert "tool" in kinds and "token" in kinds
    assert events[0][1]["intent"] == "ledger"


def test_ledger_answer_cites_real_pages(client: TestClient) -> None:
    a = _ask(client, "What worked for losses?")
    assert a["intent"] == "ledger"
    ranked = client.get("/api/v1/ledger", params={"event_type": "LOSS"}).json()["ranked"]
    if not ranked:  # a small (CI) field: too few outcomes, and the answer must say so
        assert a["refused"] and "Too few recorded outcomes" in str(a["answer"])
        return
    assert not a["refused"]
    assert ranked[0]["action_label"] in str(a["answer"]).split("\n")[1]
    lines = str(a["answer"]).strip().split("\n")
    assert all("[" in line for line in lines[1:-1])  # every claim cites
    assert "not proven to cause" in lines[-1]  # the ledger caveat travels with the answer
    pages = [c for c in a["citations"] if c["kind"] == "page"]  # type: ignore[union-attr]
    assert pages
    for c in pages[:4]:
        r = client.get(f"/api/v1/documents/{c['document_id']}/pages/{c['page_no']}")
        assert r.status_code == 200


def test_events_answer_matches_the_events_api(client: TestClient) -> None:
    a = _ask(client, "Which wells had kicks in the Kopili?")
    listed = client.get("/api/v1/events", params={"event_type": "KICK", "formation": "Kopili"})
    wells = {e["well_name"] for e in listed.json()["items"]}
    first = str(a["answer"]).split("\n")[0]
    if not wells:
        assert a["refused"] and first.startswith("No record found")
        return
    assert all(w in first for w in wells)


def test_no_record_and_off_topic(client: TestClient) -> None:
    assert _ask(client, "What happened on SYN-ASM-99?")["refused"]
    assert _ask(client, "What is the oil price today?")["refused"]
    a = _ask(client, "Who was the company man on SYN-ASM-05?")
    assert a["refused"] and str(a["answer"]).startswith("No record found")


def test_questions_about_facts_the_reports_never_hold_are_refused(client: TestClient) -> None:
    """Part 7 (V-B34): the scope check names the missing word and calls no tool, whatever
    the intent (this question names a well, so it used to get that well's summary)."""
    a = _ask(client, "What was the rig cost per day on SYN-ASM-20?")
    assert a["refused"] and "never mention" in str(a["answer"]) and "cost" in str(a["answer"])
    assert a["tools"] == []
    b = _ask(client, "Which reports mention a pipe release pill?")
    assert not b["refused"] and b["citations"]


def test_tools_are_scoped_to_the_role_and_the_query_is_audited() -> None:
    app = create_app()
    viewer = CurrentUser(user_id="copilot-viewer-it", name="V", roles=["viewer"])
    app.dependency_overrides[get_current_user] = lambda: viewer
    with TestClient(app) as c:
        a = _ask(c, "What worked for losses in the Tipam?")
    assert a["refused"] and "does not allow" in str(a["answer"])
    assert a["tools"][0]["denied"] is True  # type: ignore[index]
    with session_scope() as s:
        row = s.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == "copilot-viewer-it", AuditLog.action == "copilot_query")
            .order_by(AuditLog.id.desc())
        ).first()
    assert row is not None and row.detail["question"] == "What worked for losses in the Tipam?"
    assert row.detail["refused"] is True
