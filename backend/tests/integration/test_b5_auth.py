"""B5 auth against the real database: jwt mode in-process (the compose stack runs dev mode).

Login → token → role-checked routes → the audit log; deactivation takes effect on the next
request; the audit log refuses updates; WebSockets need ``?token=``.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from starlette.websockets import WebSocketDisconnect

from app.api.v1.schemas.auth import UserCreate
from app.core.auth import DEV_USER
from app.core.config import get_settings
from app.core.users import create_user
from app.db.models.auth import AuditLog
from app.db.session import session_scope
from app.main import create_app

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def jwt_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SMRITI_AUTH_MODE", "jwt")
    monkeypatch.setenv("SMRITI_JWT_SECRET", "integration-test-secret-" + "x" * 20)
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _user(roles: list[str]) -> str:
    name = f"it-{uuid.uuid4().hex[:10]}"
    with session_scope() as s:
        create_user(
            s,
            UserCreate.model_validate(
                {"username": name, "name": name, "password": PASSWORD, "roles": roles}
            ),
            DEV_USER,
        )
    return name


def _login(c: TestClient, username: str) -> dict[str, str]:
    r = c.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _audit(user_id: str) -> list[AuditLog]:
    with session_scope() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.id))
        return list(rows)


def test_login_roles_and_audit(jwt_client: TestClient) -> None:
    field = _user(["field_engineer"])
    bad = jwt_client.post("/api/v1/auth/login", json={"username": field, "password": "nope"})
    assert (
        bad.status_code == 401 and bad.json()["error"]["message"] == "Wrong username or password."
    )
    h = _login(jwt_client, field)
    me = jwt_client.get("/api/v1/me", headers=h).json()
    assert me["user_id"] == field and me["auth_mode"] == "jwt"
    assert "act_alerts" in me["permissions"] and "read_risk" not in me["permissions"]
    assert jwt_client.get("/api/v1/wells", headers=h).status_code == 200
    assert jwt_client.get("/api/v1/alerts", headers=h).status_code == 200
    assert jwt_client.get("/api/v1/ledger?event_type=LOSS", headers=h).status_code == 403
    assert jwt_client.post("/api/v1/replay", headers=h, json={"well_id": 1}).status_code == 403
    doc = jwt_client.get("/api/v1/documents", headers=h).json()["items"][0]["id"]
    assert jwt_client.get(f"/api/v1/documents/{doc}", headers=h).status_code == 200
    actions = [(a.action, a.target_id) for a in _audit(field)]
    assert ("login_failed", field) in actions
    assert ("login", None) not in actions and any(a == "login" for a, _ in actions)
    assert ("document_view", str(doc)) in actions


def test_deactivation_applies_at_once_and_admin_sees_the_audit(jwt_client: TestClient) -> None:
    admin, viewer = _user(["admin"]), _user(["viewer"])
    ha, hv = _login(jwt_client, admin), _login(jwt_client, viewer)
    assert jwt_client.get("/api/v1/users", headers=hv).status_code == 403
    users = jwt_client.get("/api/v1/users", headers=ha).json()
    vid = next(u["id"] for u in users if u["username"] == viewer)
    r = jwt_client.patch(f"/api/v1/users/{vid}", headers=ha, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    assert jwt_client.get("/api/v1/wells", headers=hv).status_code == 401  # same token, now dead
    page = jwt_client.get("/api/v1/audit", headers=ha, params={"user_id": admin}).json()
    assert [e["action"] for e in page["items"]][:1] == ["user_update"]
    assert page["items"][0]["detail"] == {"active": False}
    dup = jwt_client.post(
        "/api/v1/users",
        headers=ha,
        json={"username": viewer, "name": "x", "password": PASSWORD, "roles": ["viewer"]},
    )
    assert dup.status_code == 409


def test_audit_log_is_append_only() -> None:
    with pytest.raises(Exception, match="append-only"), session_scope() as s:
        s.execute(
            text("UPDATE audit_log SET action = 'x' WHERE id = (SELECT max(id) FROM audit_log)")
        )


def test_websockets_need_a_token_with_read_live(jwt_client: TestClient) -> None:
    for path in ("/ws/alerts", "/ws/wells/1/live"):
        with jwt_client.websocket_connect(path) as ws:
            assert ws.receive_json()["error"]["code"] == 4401
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4401
    token = _login(jwt_client, _user(["viewer"]))["Authorization"][7:]
    with jwt_client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        assert ws.receive_json()["error"]["code"] == 4403
    token = _login(jwt_client, _user(["field_engineer"]))["Authorization"][7:]
    with jwt_client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        assert ws.receive_json()["type"] == "hello"
