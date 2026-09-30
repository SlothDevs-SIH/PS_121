"""Authentication and role-based authorisation (master plan §16).

Modes (``SMRITI_AUTH_MODE``):

- ``dev`` (default): a fixed local admin, so every endpoint can be exercised; refused when
  ``SMRITI_ENV=prod``.
- ``jwt`` (B5): local users (``app_user``, scrypt password hashes) log in at
  ``POST /api/v1/auth/login``. Tokens are HS256, signed with ``SMRITI_JWT_SECRET``, and
  expire after ``SMRITI_JWT_TTL_MINUTES``; ``/auth/refresh`` renews one until
  ``SMRITI_SESSION_MAX_HOURS`` after the password was typed. The user is re-read on every
  request, so deactivating a user or changing their roles applies at once; a password
  change, deactivation or "revoke sessions" bumps ``session_epoch`` and kills every token.
- ``oidc`` (B6): tokens issued by an OpenID Connect provider, verified against its JWKS
  (``app/core/oidc.py``); roles come from a claim.

Where the token travels (B6): browsers get it in an **HttpOnly, SameSite=Strict cookie**
(never readable by page scripts); API clients send ``Authorization: Bearer``. A write
authenticated by the cookie must also carry ``X-Requested-With: smriti``, a header a
cross-site form cannot send, as a second guard against cross-site request forgery.

Roles grant permissions; every route names the permission it needs (``require``). The
matrix follows §16: viewers read the knowledge base; field engineers add the live monitor
and alert actions; RTMAC engineers add replay control; drilling engineers add the ledger,
risk profiles and briefs; data stewards add ingestion and review; admins everything.
"""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast, get_args

import jwt
from fastapi import Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session

Role = Literal[
    "viewer", "field_engineer", "rtmac_engineer", "drilling_engineer", "data_steward", "admin"
]
ROLES: tuple[str, ...] = get_args(Role)

Permission = Literal[
    "read_knowledge",  # wells, documents, events, search, correlation, formations
    "read_risk",  # ledger, risk profile, cementing check, offset risk brief
    "read_live",  # real-time window, alerts, live WebSockets
    "act_alerts",  # ack / dismiss / feedback
    "control_replay",  # start / pause / stop replays
    "ingest",  # upload, reprocess, survey upload
    "review",  # review queue decisions, event verification and manual entry
    "copilot",  # ask the copilot (its tools still check the permissions above)
    "admin",  # users, audit log
]
PERMISSIONS: tuple[str, ...] = get_args(Permission)

_BASE: set[str] = {"read_knowledge", "copilot"}
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(_BASE),
    "field_engineer": frozenset(_BASE | {"read_live", "act_alerts"}),
    "rtmac_engineer": frozenset(_BASE | {"read_live", "act_alerts", "control_replay"}),
    "drilling_engineer": frozenset(_BASE | {"read_risk"}),
    "data_steward": frozenset(_BASE | {"ingest", "review"}),
    "admin": frozenset(PERMISSIONS),
}


class CurrentUser(BaseModel):
    user_id: str
    name: str
    roles: list[Role]

    @property
    def permissions(self) -> frozenset[str]:
        out: set[str] = set()
        for r in self.roles:
            out |= ROLE_PERMISSIONS.get(r, frozenset())
        return frozenset(out)

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class AuthNotConfiguredError(AppError):
    status_code = 503
    code = "auth_not_configured"


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


DEV_USER = CurrentUser(user_id="dev", name="Local Developer", roles=["admin"])

# ─── Passwords (stdlib scrypt; no extra dependency) ────────────────────────────

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, key = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    got = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
    )
    return hmac.compare_digest(got, bytes.fromhex(key))


# ─── Tokens ───────────────────────────────────────────────────────────────────


def _secret(settings: Settings) -> str:
    s = settings.jwt_secret.get_secret_value() if settings.jwt_secret else ""
    if len(s) < 32:
        raise AuthNotConfiguredError("SMRITI_JWT_SECRET (at least 32 characters) is required.")
    return s


def issue_token(
    settings: Settings,
    user_id: int,
    now: datetime | None = None,
    epoch: int = 0,
    auth_time: datetime | None = None,
) -> tuple[str, datetime]:
    """A signed token for ``user_id``; ``auth_time`` is when the password was typed (kept
    across refreshes, so a session cannot be extended forever)."""
    now = now or datetime.now(tz=UTC)
    auth_time = auth_time or now
    cap = auth_time + timedelta(hours=settings.session_max_hours)
    exp = min(now + timedelta(minutes=settings.jwt_ttl_minutes), cap)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": exp,
        "iss": "smriti",
        "ep": epoch,
        "auth_time": int(auth_time.timestamp()),
    }
    return jwt.encode(claims, _secret(settings), algorithm="HS256"), exp


def decode_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            _secret(settings),
            algorithms=["HS256"],
            issuer="smriti",
            options={"require": ["exp", "sub"]},
        )
        int(claims["sub"])
        return claims
    except jwt.ExpiredSignatureError as exc:
        raise NotAuthenticatedError("The session has expired; log in again.") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise NotAuthenticatedError("Invalid authentication token.") from exc


def user_id_from_token(settings: Settings, token: str) -> int:
    return int(decode_token(settings, token)["sub"])


def load_user(session: Session, user_id: int, epoch: int | None = None) -> CurrentUser:
    from app.db.models.auth import AppUser

    u = session.get(AppUser, user_id)
    if u is None or not u.active:
        raise NotAuthenticatedError("This user does not exist or is deactivated.")
    if epoch is not None and epoch != u.session_epoch:
        raise NotAuthenticatedError("This session was ended; log in again.")
    roles = [cast(Role, r) for r in u.roles if r in ROLES]
    return CurrentUser(user_id=u.username, name=u.name, roles=roles)


def _oidc_user(settings: Settings, token: str) -> CurrentUser:
    from app.core import oidc

    try:
        claims = oidc.verify(settings, token)
    except oidc.OidcError as exc:
        raise NotAuthenticatedError(str(exc)) from exc
    username = oidc.claim(claims, settings.oidc_username_claim) or claims["sub"]
    roles = oidc.map_roles(
        oidc.claim(claims, settings.oidc_roles_claim), settings.oidc_role_map, ROLES
    )
    return CurrentUser(
        user_id=str(username)[:80],
        name=str(claims.get("name") or username)[:200],
        roles=[cast(Role, r) for r in roles],
    )


def user_for_token(settings: Settings, session: Session, token: str | None) -> CurrentUser:
    """The user a token (header, session cookie or a WebSocket's ``?token=``) belongs to."""
    if settings.auth_mode == "dev":
        if settings.env == "prod":
            raise AuthNotConfiguredError("Dev auth mode is refused when SMRITI_ENV=prod.")
        return DEV_USER
    if settings.auth_mode == "oidc" and not settings.oidc_issuer:
        raise AuthNotConfiguredError("OIDC mode needs SMRITI_OIDC_ISSUER.")
    if not token:
        raise NotAuthenticatedError("Log in first.")
    if settings.auth_mode == "oidc":
        return _oidc_user(settings, token)
    claims = decode_token(settings, token)
    return load_user(session, int(claims["sub"]), int(claims.get("ep", 0)))


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "smriti"


class CsrfError(AppError):
    status_code = 403
    code = "csrf_check_failed"


def token_from_request(request: Request, settings: Settings) -> tuple[str | None, bool]:
    """(token, came_from_cookie). The Authorization header wins over the cookie."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None, False
    cookie = request.cookies.get(settings.session_cookie_name)
    return (cookie or None), bool(cookie)


def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentUser:
    token, from_cookie = token_from_request(request, settings)
    if (
        from_cookie
        and settings.auth_mode != "dev"
        and request.method not in SAFE_METHODS
        and request.headers.get(CSRF_HEADER, "").lower() != CSRF_VALUE
    ):
        raise CsrfError(
            "Cookie-authenticated writes need the X-Requested-With: smriti header.",
            {"header": "X-Requested-With"},
        )
    return user_for_token(settings, session, token)


def require(permission: Permission) -> Callable[..., CurrentUser]:
    """Route dependency: the current user, if one of their roles grants ``permission``."""

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.can(permission):
            raise ForbiddenError(
                f"Your role does not allow this ({permission}).",
                {"permission": permission, "roles": list(user.roles)},
            )
        return user

    dependency.__name__ = f"require_{permission}"
    return dependency
