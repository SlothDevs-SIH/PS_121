"""B6 OIDC end to end against a real Keycloak (compose profile ``oidc``): a scripted
browser does the authorisation-code + PKCE login at the provider, the API exchanges the
code and sets HttpOnly cookies, roles map to permissions, refresh goes through the
provider, and a code cannot be used twice. Skipped when the profile is not running."""

import base64
import hashlib
import html
import os
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

API = os.environ.get("SMRITI_OIDC_API_URL", "http://localhost:8002")
REDIRECT = "http://localhost:8082/auth/callback"
PASSWORD = "smriti-demo-password"


def _up() -> bool:
    try:
        return httpx.get(f"{API}/api/v1/auth/config", timeout=3).json()["auth_mode"] == "oidc"
    except (httpx.HTTPError, ValueError, KeyError):
        return False


pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _up(), reason="oidc profile down")]


def _code(username: str) -> tuple[str, str]:
    """Log in at Keycloak like a browser; the authorisation code and the PKCE verifier."""
    cfg = httpx.get(f"{API}/api/v1/auth/config").json()["oidc"]
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    query = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": REDIRECT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(8),
    }
    with httpx.Client(follow_redirects=False, timeout=10) as b:
        page = b.get(cfg["authorize_url"] + "?" + urlencode(query))
        m = re.search(r'action="([^"]+)"', page.text)
        assert m, "no login form"
        # Keycloak marks its cookies Secure; a browser sends them to http://localhost, httpx
        # does not, so forward them by hand.
        jar = "; ".join(f"{c.name}={c.value}" for c in b.cookies.jar)
        r = b.post(
            html.unescape(m.group(1)),
            data={"username": username, "password": PASSWORD},
            headers={"Cookie": jar},
        )
        assert r.status_code == 302, r.text[:300]
    return parse_qs(urlsplit(r.headers["location"]).query)["code"][0], verifier


def _session(username: str) -> httpx.Client:
    code, verifier = _code(username)
    c = httpx.Client(base_url=API, timeout=10)
    r = c.post(
        "/api/v1/auth/oidc/callback",
        json={"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT},
    )
    assert r.status_code == 200, r.text
    return c


def test_pkce_login_sets_httponly_cookies_and_maps_roles() -> None:
    c = _session("priya")
    me = c.get("/api/v1/me").json()
    assert me["user_id"] == "priya" and me["roles"] == ["rtmac_engineer"]
    assert me["auth_mode"] == "oidc" and "control_replay" in me["permissions"]
    assert {"smriti_session", "smriti_refresh"} <= set(c.cookies.keys())
    # A write with the cookie needs the CSRF header; with it, the permission check passes.
    body = {"well_id": 999999, "action": "pause"}
    assert c.post("/api/v1/replay", json=body).status_code == 403
    r = c.post("/api/v1/replay", json=body, headers={"X-Requested-With": "smriti"})
    assert r.status_code == 404  # past auth: the well does not exist


def test_viewer_is_refused_live_data() -> None:
    c = _session("meera")
    assert c.get("/api/v1/me").json()["roles"] == ["viewer"]
    assert c.get("/api/v1/alerts").status_code == 403
    assert c.get("/api/v1/wells", params={"limit": 1}).status_code == 200


def test_refresh_goes_through_the_provider_and_codes_are_single_use() -> None:
    code, verifier = _code("arun")
    c = httpx.Client(base_url=API, timeout=10)
    body = {"code": code, "code_verifier": verifier, "redirect_uri": REDIRECT}
    assert c.post("/api/v1/auth/oidc/callback", json=body).status_code == 200
    first = c.cookies["smriti_session"]
    r = c.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["user_id"] == "arun"
    assert c.cookies["smriti_session"] != first
    again = httpx.post(f"{API}/api/v1/auth/oidc/callback", json=body)
    assert again.status_code == 401 and "invalid_grant" in again.json()["error"]["message"]
    wrong = httpx.post(f"{API}/api/v1/auth/oidc/callback", json={**body, "code_verifier": "x" * 43})
    assert wrong.status_code == 401


def test_a_forged_token_is_refused() -> None:
    fake = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0."
    r = httpx.get(f"{API}/api/v1/me", headers={"Authorization": f"Bearer {fake}"})
    assert r.status_code == 401
