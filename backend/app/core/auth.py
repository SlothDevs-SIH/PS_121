"""Authentication and role-based authorisation (master plan §16).

Modes (``SMRITI_AUTH_MODE``):

- ``dev`` (default): a fixed local admin, so every endpoint can be exercised; refused when
  ``SMRITI_ENV=prod``.
- ``jwt`` (B5): local users (``app_user``, scrypt password hashes) log in at
  ``POST /api/v1/auth/login`` and send ``Authorization: Bearer <token>``. Tokens are HS256,
  signed with ``SMRITI_JWT_SECRET``, and expire after ``SMRITI_JWT_TTL_MINUTES``. The user
  is re-read on every request, so deactivating a user or changing their roles applies at
  once, not when the token expires.
- ``oidc``: Keycloak (B6, not built).

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
    settings: Settings, user_id: int, now: datetime | None = None
) -> tuple[str, datetime]:
    now = now or datetime.now(tz=UTC)
    exp = now + timedelta(minutes=settings.jwt_ttl_minutes)
    claims: dict[str, Any] = {"sub": str(user_id), "iat": now, "exp": exp, "iss": "smriti"}
    return jwt.encode(claims, _secret(settings), algorithm="HS256"), exp


def user_id_from_token(settings: Settings, token: str) -> int:
    try:
        claims = jwt.decode(
            token,
            _secret(settings),
            algorithms=["HS256"],
            issuer="smriti",
            options={"require": ["exp", "sub"]},
        )
        return int(claims["sub"])
    except jwt.ExpiredSignatureError as exc:
        raise NotAuthenticatedError("The session has expired; log in again.") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise NotAuthenticatedError("Invalid authentication token.") from exc


def load_user(session: Session, user_id: int) -> CurrentUser:
    from app.db.models.auth import AppUser

    u = session.get(AppUser, user_id)
    if u is None or not u.active:
        raise NotAuthenticatedError("This user does not exist or is deactivated.")
    roles = [cast(Role, r) for r in u.roles if r in ROLES]
    return CurrentUser(user_id=u.username, name=u.name, roles=roles)


def user_for_token(settings: Settings, session: Session, token: str | None) -> CurrentUser:
    """The user a bearer token (or a WebSocket's ``?token=``) belongs to, in any mode."""
    if settings.auth_mode == "dev":
        if settings.env == "prod":
            raise AuthNotConfiguredError("Dev auth mode is refused when SMRITI_ENV=prod.")
        return DEV_USER
    if settings.auth_mode == "oidc":
        raise AuthNotConfiguredError("OIDC authentication is planned for backend phase B6.")
    if not token:
        raise NotAuthenticatedError("Log in first (Authorization: Bearer <token>).")
    return load_user(session, user_id_from_token(settings, token))


def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentUser:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
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
