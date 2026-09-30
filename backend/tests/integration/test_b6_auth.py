"""B6 auth hardening against the real database (jwt mode, in-process): the session cookie
and its CSRF rule, refresh and its cap, revocation by epoch, lockout after failures,
logout, and the WebSocket origin check for cookie sessions."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api.v1.schemas.auth import UserCreate
from app.core.auth import DEV_USER, issue_token
from app.core.config import get_settings
from app.core.users import create_user
from app.db.models.auth import AppUser, AuditLog
from app.db.session import session_scope
from app.main import create_app

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
SECRET = "integration-test-secret-" + "x" * 20
COOKIE = "smriti_session"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SMRITI_AUTH_MODE", "jwt")
    monkeypatch.setenv("SMRITI_JWT_SECRET", SECRET)
    monkeypatch.setenv("SMRITI_LOGIN_RATE_PER_MINUTE", "1000")
    monkeypatch.setenv("SMRITI_LOGIN_MAX_FAILURES", "3")
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


def _login(c: TestClient, name: str, password: str = PASSWORD) -> int:
    return c.post("/api/v1/auth/login", json={"username": name, "password": password}).status_code


def _actions(name: str) -> list[str]:
    with session_scope() as s:
        return list(
            s.scalars(select(AuditLog.action).where(AuditLog.user_id == name).order_by(AuditLog.id))
        )


def test_cookie_session_reads_freely_and_writes_only_with_the_csrf_header(
    client: TestClient,
) -> None:
    name = _user(["field_engineer"])
    r = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie and "path=/" in set_cookie
    assert client.cookies.get(COOKIE)
    assert client.get("/api/v1/me").json()["user_id"] == name  # cookie alone reads
    alerts = client.get("/api/v1/alerts", params={"limit": 1}).json()["items"]
    target = alerts[0]["id"] if alerts else 999999999
    r = client.post(f"/api/v1/alerts/{target}/feedback", json={"verdict": "useful"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_check_failed"
    r = client.post(
        f"/api/v1/alerts/{target}/feedback",
        json={"verdict": "useful"},
        headers={"X-Requested-With": "smriti"},
    )
    assert r.status_code in (201, 404)  # past the CSRF and auth checks


def test_refresh_keeps_the_login_time_and_logout_clears_the_cookie(client: TestClient) -> None:
    name = _user(["viewer"])
    assert _login(client, name) == 200
    first = jwt.decode(client.cookies[COOKIE], options={"verify_signature": False})
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200, r.text
    again = jwt.decode(client.cookies[COOKIE], options={"verify_signature": False})
    assert again["auth_time"] == first["auth_time"]
    # A token whose login was longer ago than session_max_hours cannot be refreshed.
    with session_scope() as s:
        u = s.scalar(select(AppUser).where(AppUser.username == name))
        assert u is not None
        now = datetime.now(tz=UTC)
        old, _ = issue_token(
            get_settings(),
            u.id,
            now=now,
            epoch=u.session_epoch,
            auth_time=now - timedelta(hours=25),
        )
    r = client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {old}"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204 and COOKIE not in client.cookies
    assert client.get("/api/v1/me").status_code == 401
    assert "logout" in _actions(name)


def test_password_change_or_revoke_ends_existing_sessions(client: TestClient) -> None:
    admin, name = _user(["admin"]), _user(["viewer"])
    r = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    victim = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/v1/auth/login", json={"username": admin, "password": PASSWORD})
    boss = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/me", headers=victim).status_code == 200
    users = client.get("/api/v1/users", headers=boss).json()
    uid = next(u["id"] for u in users if u["username"] == name)
    r = client.patch(f"/api/v1/users/{uid}", json={"revoke_sessions": True}, headers=boss)
    assert r.status_code == 200
    r = client.get("/api/v1/me", headers=victim)
    assert r.status_code == 401 and "ended" in r.json()["error"]["message"]
    assert _login(client, name) == 200  # a new login works


def test_repeated_failures_lock_the_account_and_admin_unlocks(client: TestClient) -> None:
    admin, name = _user(["admin"]), _user(["viewer"])
    assert [_login(client, name, "wrong-password") for _ in range(3)] == [401, 401, 401]
    # Locked: even the right password is refused, with the same message.
    r = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["message"] == "Wrong username or password."
    actions = _actions(name)
    assert "account_locked" in actions and actions.count("login_failed") == 4
    r = client.post("/api/v1/auth/login", json={"username": admin, "password": PASSWORD})
    boss = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = next(
        u["id"] for u in client.get("/api/v1/users", headers=boss).json() if u["username"] == name
    )
    listed = client.patch(f"/api/v1/users/{uid}", json={"unlock": True}, headers=boss).json()
    assert listed["locked_until"] is None
    assert _login(client, name) == 200


def test_websocket_takes_the_cookie_only_from_our_own_origin(client: TestClient) -> None:
    name = _user(["field_engineer"])
    assert _login(client, name) == 200
    with client.websocket_connect("/ws/alerts", headers={"origin": "http://testserver"}) as ws:
        assert ws.receive_json()["type"] == "hello"
    with (
        pytest.raises(WebSocketDisconnect) as e,
        client.websocket_connect("/ws/alerts", headers={"origin": "https://evil.example"}) as ws,
    ):
        ws.receive_json()
        ws.receive_json()
    assert e.value.code == 4403
