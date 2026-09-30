"""OpenID Connect resource-server mode (B6, ``SMRITI_AUTH_MODE=oidc``).

The browser logs in at the identity provider (Keycloak, Entra ID, …) with the
authorisation-code flow and PKCE and sends the access token. This module only *verifies*
tokens:

- signature against the provider's JWKS (fetched from ``oidc_jwks_url`` or the issuer's
  discovery document, cached by PyJWT and refetched when an unknown key id appears);
- ``iss`` equal to ``oidc_issuer``, ``aud`` containing ``oidc_audience`` when set, ``exp``;
- asymmetric algorithms only (``oidc_algorithms``), so an ``alg: none`` or HS256 token
  signed with a public key is rejected.

Roles come from a dotted claim path (Keycloak: ``realm_access.roles``), mapped through
``oidc_role_map``; names that are already SMRITI roles pass through; unknown roles are
dropped, so a user with none gets 403 everywhere except ``/me``.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import Settings


class OidcError(Exception):
    """A token that must not be accepted; the message is safe to show."""


def _discover_jwks_url(issuer: str) -> str:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    if not url.startswith(("https://", "http://")):
        raise OidcError("The OIDC issuer must be an http(s) URL.")
    with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 (scheme checked above)
        doc = json.loads(r.read())
    jwks = doc.get("jwks_uri")
    if not isinstance(jwks, str):
        raise OidcError("The provider's discovery document has no jwks_uri.")
    return jwks


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)


def jwks_url(settings: Settings) -> str:
    if settings.oidc_jwks_url:
        return settings.oidc_jwks_url
    if not settings.oidc_issuer:
        raise OidcError("SMRITI_OIDC_ISSUER is not set.")
    return _discover_jwks_url(settings.oidc_issuer)


def claim(claims: dict[str, Any], path: str) -> Any:
    cur: Any = claims
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def map_roles(raw: Any, role_map: dict[str, str], known: tuple[str, ...]) -> list[str]:
    names = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
    out: set[str] = set()
    for n in names:
        if not isinstance(n, str):
            continue
        r = role_map.get(n, n)
        if r in known:
            out.add(r)
    return sorted(out)


def verify(settings: Settings, token: str, signing_key: Any | None = None) -> dict[str, Any]:
    """The token's claims if it is valid for this server, else OidcError."""
    if not settings.oidc_issuer:
        raise OidcError("SMRITI_OIDC_ISSUER is not set.")
    try:
        key = signing_key or _jwks_client(jwks_url(settings)).get_signing_key_from_jwt(token).key
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=settings.oidc_algorithms,
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={
                "require": ["exp", "iss", "sub"],
                "verify_aud": settings.oidc_audience is not None,
            },
            leeway=30,
        )
    except jwt.ExpiredSignatureError as exc:
        raise OidcError("The session has expired; log in again.") from exc
    except (jwt.PyJWTError, OSError, ValueError) as exc:
        raise OidcError("Invalid authentication token.") from exc
    return claims


# ─── Authorisation-code exchange (the backend-for-frontend half of the login) ─────────────


def _kc(base: str | None, path: str) -> str | None:
    return f"{base.rstrip('/')}/protocol/openid-connect/{path}" if base else None


def authorize_url(settings: Settings) -> str | None:
    return settings.oidc_authorize_url or _kc(
        settings.oidc_public_issuer or settings.oidc_issuer, "auth"
    )


def end_session_url(settings: Settings) -> str | None:
    return settings.oidc_end_session_url or _kc(
        settings.oidc_public_issuer or settings.oidc_issuer, "logout"
    )


def token_url(settings: Settings) -> str:
    url = settings.oidc_token_url or _kc(settings.oidc_issuer, "token")
    if not url or not url.startswith(("https://", "http://")):
        raise OidcError("The OIDC token endpoint must be an http(s) URL.")
    return url


def _post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(  # noqa: S310 (scheme checked by token_url)
        url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
            out: dict[str, Any] = json.loads(r.read())
            return out
    except urllib.error.HTTPError as exc:
        # The provider says why (invalid_grant: code reused or expired, bad verifier…).
        try:
            err = json.loads(exc.read()).get("error", "error")
        except (ValueError, OSError):
            err = "error"
        raise OidcError(f"The identity provider refused the login ({err}).") from exc
    except OSError as exc:
        raise OidcError("The identity provider could not be reached.") from exc


def exchange_code(
    settings: Settings, code: str, verifier: str, redirect_uri: str, post: Any = None
) -> dict[str, Any]:
    """Trade an authorisation code (+ PKCE verifier) for tokens at the token endpoint."""
    return (post or _post_form)(
        token_url(settings),
        {
            "grant_type": "authorization_code",
            "client_id": settings.oidc_client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
    )


def refresh_tokens(settings: Settings, refresh_token: str, post: Any = None) -> dict[str, Any]:
    return (post or _post_form)(
        token_url(settings),
        {
            "grant_type": "refresh_token",
            "client_id": settings.oidc_client_id,
            "refresh_token": refresh_token,
        },
    )
