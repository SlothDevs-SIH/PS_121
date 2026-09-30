"""B6 auth hardening: session length cap, cookie + CSRF rule, OIDC token verification
(with a locally generated key standing in for the provider), the rate limiter."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import oidc, ratelimit
from app.core.auth import (
    CsrfError,
    NotAuthenticatedError,
    decode_token,
    get_current_user,
    issue_token,
    user_for_token,
)
from app.core.config import Settings, get_settings
from app.core.errors import RateLimitedError
from app.db.session import get_session
from app.main import create_app

SECRET = "x" * 40
ISSUER = "https://idp.example/realms/oil"


def _jwt_settings(**kw: Any) -> Settings:
    return Settings(**{"auth_mode": "jwt", "jwt_secret": SECRET, **kw})


def test_refreshed_tokens_never_outlive_the_session_cap() -> None:
    s = _jwt_settings(jwt_ttl_minutes=480, session_max_hours=10)
    login = datetime(2026, 9, 30, 0, 0, tzinfo=UTC)
    _, exp1 = issue_token(s, 7, now=login)
    assert exp1 == login + timedelta(hours=8)
    # A refresh at hour 7 carries the original login time: capped at 10 h, not 15 h.
    tok, exp2 = issue_token(s, 7, now=login + timedelta(hours=7), auth_time=login, epoch=3)
    assert exp2 == login + timedelta(hours=10)
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert claims["ep"] == 3 and claims["auth_time"] == int(login.timestamp())


def test_a_token_signed_with_another_secret_or_expired_is_refused() -> None:
    s = _jwt_settings()
    other = _jwt_settings(jwt_secret="y" * 40)
    tok, _ = issue_token(other, 1)
    with pytest.raises(NotAuthenticatedError):
        decode_token(s, tok)
    old, _ = issue_token(s, 1, now=datetime.now(tz=UTC) - timedelta(days=2))
    with pytest.raises(NotAuthenticatedError, match="expired"):
        decode_token(s, old)


class _Req:
    def __init__(self, method: str, headers: dict[str, str], cookies: dict[str, str]) -> None:
        self.method = method
        self.headers = headers
        self.cookies = cookies


def test_cookie_writes_need_the_csrf_header_bearer_writes_do_not() -> None:
    s = _jwt_settings()
    cookie = {s.session_cookie_name: "t"}
    with pytest.raises(CsrfError):
        get_current_user(_Req("POST", {}, cookie), s, None)  # type: ignore[arg-type]
    # With the header, or on a GET, or with a bearer token, the CSRF rule passes and the
    # token check runs (and fails here: "t" is not a token).
    for req in (
        _Req("POST", {"x-requested-with": "smriti"}, cookie),
        _Req("GET", {}, cookie),
        _Req("POST", {"authorization": "Bearer t"}, {}),
    ):
        with pytest.raises(NotAuthenticatedError):
            get_current_user(req, s, None)  # type: ignore[arg-type]


# ─── OIDC ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def keys() -> tuple[Any, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _oidc_settings(**kw: Any) -> Settings:
    return Settings(  # type: ignore[call-arg]
        auth_mode="oidc",
        oidc_issuer=ISSUER,
        oidc_audience="smriti-api",
        oidc_role_map={"rtmac": "rtmac_engineer"},
        **kw,
    )


def _idp_token(private: Any, **over: Any) -> str:
    now = datetime.now(tz=UTC)
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": ["smriti-api", "account"],
        "sub": "f3a1",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "preferred_username": "priya",
        "name": "Priya Das",
        "realm_access": {"roles": ["rtmac", "viewer", "offline_access"]},
    }
    claims.update(over)
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "k1"})


def test_oidc_token_is_verified_and_roles_mapped(keys: tuple[Any, Any]) -> None:
    private, public = keys
    s = _oidc_settings()
    claims = oidc.verify(s, _idp_token(private), signing_key=public)
    assert claims["preferred_username"] == "priya"
    roles = oidc.map_roles(
        oidc.claim(claims, s.oidc_roles_claim), s.oidc_role_map, ("viewer", "rtmac_engineer")
    )
    assert roles == ["rtmac_engineer", "viewer"]  # unknown "offline_access" dropped


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://evil.example/realms/oil"},
        {"aud": "another-app"},
        {"exp": datetime.now(tz=UTC) - timedelta(minutes=5)},
    ],
)
def test_oidc_rejects_wrong_issuer_audience_or_expired(
    keys: tuple[Any, Any], override: dict[str, Any]
) -> None:
    private, public = keys
    with pytest.raises(oidc.OidcError):
        oidc.verify(_oidc_settings(), _idp_token(private, **override), signing_key=public)


def test_oidc_rejects_symmetric_and_unsigned_tokens(keys: tuple[Any, Any]) -> None:
    _, public = keys
    s = _oidc_settings()
    now = datetime.now(tz=UTC)
    body = {"iss": ISSUER, "aud": "smriti-api", "sub": "x", "exp": now + timedelta(minutes=5)}
    unsigned = jwt.encode(body, None, algorithm="none")
    with pytest.raises(oidc.OidcError):
        oidc.verify(s, unsigned, signing_key=public)
    # The classic confusion attack: HS256 "signed" with the public key's bytes.
    hs = jwt.encode(body, "public-key-bytes-as-an-hmac-secret-0000", algorithm="HS256")
    with pytest.raises(oidc.OidcError):
        oidc.verify(s, hs, signing_key=public)


def test_oidc_user_is_built_from_claims(
    keys: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    private, public = keys
    real = oidc.verify
    monkeypatch.setattr(oidc, "verify", lambda s, t: real(s, t, signing_key=public))
    user = user_for_token(_oidc_settings(), None, _idp_token(private))  # type: ignore[arg-type]
    assert (user.user_id, user.name) == ("priya", "Priya Das")
    assert user.can("control_replay") and not user.can("admin")
    with pytest.raises(NotAuthenticatedError):
        user_for_token(_oidc_settings(), None, "not-a-jwt")  # type: ignore[arg-type]


def test_claim_paths() -> None:
    c = {"a": {"b": ["x"]}, "roles": "admin"}
    assert oidc.claim(c, "a.b") == ["x"] and oidc.claim(c, "a.c") is None
    assert oidc.claim(c, "roles.x") is None
    assert oidc.map_roles("admin", {}, ("admin",)) == ["admin"]
    assert oidc.map_roles(None, {}, ("admin",)) == []


# ─── Rate limiter ─────────────────────────────────────────────────────────────


class MemoryCounter:
    def __init__(self) -> None:
        self.n: dict[str, int] = {}

    def incr(self, name: str) -> int:
        self.n[name] = self.n.get(name, 0) + 1
        return self.n[name]

    def expire(self, name: str, time: int) -> bool:
        return True

    def ttl(self, name: str) -> int:
        return 42


def test_rate_limit_allows_the_limit_then_429_with_retry_after() -> None:
    c = MemoryCounter()
    for _ in range(3):
        ratelimit.hit("login:1.2.3.4", 3, counter=c)
    with pytest.raises(RateLimitedError) as e:
        ratelimit.hit("login:1.2.3.4", 3, counter=c)
    assert e.value.status_code == 429 and e.value.headers == {"Retry-After": "42"}
    ratelimit.hit("login:5.6.7.8", 3, counter=c)  # other clients unaffected


def test_rate_limit_fails_open_when_redis_is_down() -> None:
    import redis

    class Down(MemoryCounter):
        def incr(self, name: str) -> int:
            raise redis.ConnectionError("down")

    ratelimit.hit("copilot:x", 1, counter=Down())
    ratelimit.hit("copilot:x", 1, counter=Down())  # no exception: allowed


class _NoUsers:
    """A session with no users: every login fails with 401 before any real database."""

    def scalar(self, *_: Any) -> None:
        return None

    def add(self, *_: Any) -> None: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


def test_login_is_rate_limited_per_address() -> None:
    c = MemoryCounter()
    ratelimit.set_counter(c)
    try:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: _jwt_settings(login_rate_per_minute=2)
        app.dependency_overrides[get_session] = lambda: _NoUsers()
        client = TestClient(app)
        body = {"username": "nobody", "password": "wrong"}
        codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(3)]
    finally:
        ratelimit.set_counter(None)
    assert codes == [401, 401, 429]


def test_auth_config_is_public_and_names_the_provider() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _oidc_settings(
        oidc_public_issuer="http://localhost:8180/realms/oil"
    )
    r = TestClient(app).get("/api/v1/auth/config")
    assert r.status_code == 200
    assert r.json() == {
        "auth_mode": "oidc",
        "oidc": {
            "issuer": "http://localhost:8180/realms/oil",
            "client_id": "smriti-web",
            # Browser-facing endpoints follow the public issuer, not the internal one.
            "authorize_url": "http://localhost:8180/realms/oil/protocol/openid-connect/auth",
            "end_session_url": "http://localhost:8180/realms/oil/protocol/openid-connect/logout",
        },
        "session_max_hours": 24,
    }


def test_login_limit_ignores_a_forged_client_address_unless_behind_our_proxy() -> None:
    from types import SimpleNamespace

    from app.api.v1.routes.system import _client_ip

    req = SimpleNamespace(
        headers={"x-real-ip": "203.0.113.9"}, client=SimpleNamespace(host="10.0.0.5")
    )
    assert _client_ip(req, _jwt_settings()) == "10.0.0.5"  # type: ignore[arg-type]
    assert _client_ip(req, _jwt_settings(trust_proxy_headers=True)) == "203.0.113.9"  # type: ignore[arg-type]
