"""B5 auth: password hashing, tokens, the role → permission matrix, route permissions."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.auth import (
    PERMISSIONS,
    ROLE_PERMISSIONS,
    ROLES,
    CurrentUser,
    NotAuthenticatedError,
    get_current_user,
    hash_password,
    issue_token,
    user_id_from_token,
    verify_password,
)
from app.core.config import Settings, get_settings
from app.main import create_app

SECRET = "x" * 40


def test_scrypt_hash_round_trip_and_salt() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$") and "correct" not in h
    assert verify_password("correct horse battery", h)
    assert not verify_password("correct horse batterY", h)
    assert hash_password("same") != hash_password("same")  # salted
    assert not verify_password("x", "not-a-hash")


def test_tokens_expire_and_cannot_be_forged() -> None:
    s = Settings(auth_mode="jwt", jwt_secret=SECRET, jwt_ttl_minutes=60)
    tok, exp = issue_token(s, 7)
    assert user_id_from_token(s, tok) == 7
    assert exp > datetime.now(tz=UTC)
    old, _ = issue_token(s, 7, now=datetime.now(tz=UTC) - timedelta(hours=2))
    with pytest.raises(NotAuthenticatedError, match="expired"):
        user_id_from_token(s, old)
    other = Settings(auth_mode="jwt", jwt_secret="y" * 40)
    with pytest.raises(NotAuthenticatedError, match="Invalid"):
        user_id_from_token(other, tok)
    with pytest.raises(NotAuthenticatedError):
        user_id_from_token(s, tok[:-2] + "aa")


def test_short_secret_is_refused() -> None:
    from app.core.auth import AuthNotConfiguredError

    with pytest.raises(AuthNotConfiguredError):
        issue_token(Settings(auth_mode="jwt", jwt_secret="short"), 1)


def test_permission_matrix_follows_master_plan_16() -> None:
    assert set(ROLE_PERMISSIONS) == set(ROLES)
    assert ROLE_PERMISSIONS["admin"] == frozenset(PERMISSIONS)
    for role, perms in ROLE_PERMISSIONS.items():
        assert {"read_knowledge", "copilot"} <= perms, role
    viewer = ROLE_PERMISSIONS["viewer"]
    assert not viewer & {"read_live", "act_alerts", "read_risk", "ingest", "review", "admin"}
    assert {"read_live", "act_alerts"} <= ROLE_PERMISSIONS["field_engineer"]
    assert "control_replay" not in ROLE_PERMISSIONS["field_engineer"]
    assert "control_replay" in ROLE_PERMISSIONS["rtmac_engineer"]
    assert "read_risk" in ROLE_PERMISSIONS["drilling_engineer"]
    assert {"ingest", "review"} <= ROLE_PERMISSIONS["data_steward"]
    both = CurrentUser(user_id="u", name="U", roles=["field_engineer", "drilling_engineer"])
    assert both.can("read_risk") and both.can("act_alerts") and not both.can("admin")


@pytest.mark.parametrize(
    ("role", "method", "url", "body"),
    [
        ("viewer", "post", "/api/v1/alerts/1/ack", None),
        ("viewer", "get", "/api/v1/alerts", None),
        ("viewer", "get", "/api/v1/ledger?event_type=LOSS", None),
        ("viewer", "get", "/api/v1/wells/1/risk-profile", None),
        ("viewer", "post", "/api/v1/review-queue/1", {"action": "accept"}),
        ("viewer", "get", "/api/v1/users", None),
        ("field_engineer", "post", "/api/v1/replay", {"well_id": 1}),
        ("field_engineer", "get", "/api/v1/ledger?event_type=LOSS", None),
        ("drilling_engineer", "post", "/api/v1/alerts/1/ack", None),
        ("data_steward", "get", "/api/v1/audit", None),
    ],
)
def test_routes_refuse_roles_without_the_permission(
    role: str, method: str, url: str, body: object
) -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="u",
        name="U",
        roles=[role],  # type: ignore[list-item]
    )
    r = TestClient(app).request(method, url, json=body)
    assert r.status_code == 403, r.text
    err = r.json()["error"]
    assert err["code"] == "forbidden" and err["details"]["roles"] == [role]


def test_jwt_mode_without_a_token_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMRITI_AUTH_MODE", "jwt")
    monkeypatch.setenv("SMRITI_JWT_SECRET", SECRET)
    get_settings.cache_clear()
    c = TestClient(create_app())
    for url in ("/api/v1/me", "/api/v1/wells", "/api/v1/alerts"):
        r = c.get(url)
        assert r.status_code == 401, url
        assert r.json()["error"]["code"] == "not_authenticated"
    r = c.get("/api/v1/wells", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401
    assert c.get("/healthz").status_code == 200  # health stays public
    assert c.get("/api/v1/meta").status_code == 200


def test_login_is_refused_outside_jwt_mode(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"username": "a", "password": "b"})
    assert r.status_code == 409
    assert r.json()["error"]["details"]["auth_mode"] == "dev"


def test_me_lists_permissions_in_dev_mode(client: TestClient) -> None:
    body = client.get("/api/v1/me").json()
    assert body["auth_mode"] == "dev"
    assert set(body["permissions"]) == set(PERMISSIONS)
