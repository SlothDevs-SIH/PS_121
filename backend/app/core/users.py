"""Local users: login, and the admin operations behind /api/v1/users (B5, jwt mode)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.schemas.auth import Me, TokenOut, UserCreate, UserOut, UserUpdate
from app.core import oidc
from app.core.audit import audit
from app.core.auth import (
    CurrentUser,
    NotAuthenticatedError,
    decode_token,
    hash_password,
    issue_token,
    load_user,
    verify_password,
)
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.db.models.auth import AppUser

# Checked when the username does not exist, so a failed login takes the same time either way.
_DUMMY_HASH = hash_password("not-a-real-password-0000")


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


def me(user: CurrentUser, settings: Settings) -> Me:
    return Me(
        user_id=user.user_id,
        name=user.name,
        roles=user.roles,
        permissions=sorted(user.permissions),
        auth_mode=settings.auth_mode,
    )


def _require_jwt(settings: Settings) -> None:
    if settings.auth_mode != "jwt":
        raise ConflictError(
            f"Login is used in jwt auth mode; this server runs in {settings.auth_mode} mode.",
            {"auth_mode": settings.auth_mode},
        )


def _token_out(settings: Settings, u: AppUser, auth_time: datetime | None = None) -> TokenOut:
    token, exp = issue_token(settings, u.id, epoch=u.session_epoch, auth_time=auth_time)
    cur = CurrentUser.model_validate({"user_id": u.username, "name": u.name, "roles": u.roles})
    return TokenOut(access_token=token, expires_at=exp, user=me(cur, settings))


def login(
    session: Session, settings: Settings, username: str, password: str, now: datetime | None = None
) -> TokenOut:
    """Check the password. ``login_max_failures`` wrong passwords in a row lock the account
    for ``login_lockout_minutes``; a locked account answers like a wrong password (the audit
    log says which), so the response does not reveal which accounts exist or are locked."""
    _require_jwt(settings)
    now = now or datetime.now(tz=UTC)
    name = username.strip().lower()
    u = session.scalar(select(AppUser).where(AppUser.username == name))
    ok = verify_password(password, u.password_hash if u else _DUMMY_HASH)
    locked = u is not None and u.locked_until is not None and u.locked_until > now
    if u is None or not ok or not u.active or locked:
        if u is not None and not locked and not ok:
            u.failed_logins += 1
            if u.failed_logins >= settings.login_max_failures:
                u.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                u.failed_logins = 0
                audit(session, u.username, "account_locked", "user", u.id)
        audit(
            session,
            name[:80],
            "login_failed",
            "user",
            name[:80],
            reason="locked" if locked else "inactive" if u and ok else "credentials",
        )
        session.commit()
        raise NotAuthenticatedError("Wrong username or password.")
    u.failed_logins = 0
    u.locked_until = None
    u.last_login_at = now
    audit(session, u.username, "login", "user", u.id)
    return _token_out(settings, u)


def refresh(session: Session, settings: Settings, token: str | None) -> TokenOut:
    """A fresh token for a live session, never past ``session_max_hours`` after login."""
    _require_jwt(settings)
    if not token:
        raise NotAuthenticatedError("Log in first.")
    claims = decode_token(settings, token)
    uid = int(claims["sub"])
    load_user(session, uid, int(claims.get("ep", 0)))  # active and not revoked
    auth_time = datetime.fromtimestamp(int(claims.get("auth_time", claims["iat"])), tz=UTC)
    if datetime.now(tz=UTC) - auth_time >= timedelta(hours=settings.session_max_hours):
        raise NotAuthenticatedError("The session has reached its maximum length; log in again.")
    u = session.get(AppUser, uid)
    assert u is not None
    return _token_out(settings, u, auth_time)


def _require_oidc(settings: Settings) -> None:
    if settings.auth_mode != "oidc":
        raise ConflictError(
            f"This server runs in {settings.auth_mode} mode, not oidc.",
            {"auth_mode": settings.auth_mode},
        )


def oidc_exchange(
    settings: Settings, code: str, verifier: str, redirect_uri: str
) -> dict[str, Any]:
    _require_oidc(settings)
    try:
        tokens = oidc.exchange_code(settings, code, verifier, redirect_uri)
    except oidc.OidcError as exc:
        raise NotAuthenticatedError(str(exc)) from exc
    if not tokens.get("access_token"):
        raise NotAuthenticatedError("The identity provider returned no access token.")
    return tokens


def oidc_refresh(settings: Settings, refresh_token: str | None) -> dict[str, Any]:
    _require_oidc(settings)
    if not refresh_token:
        raise NotAuthenticatedError("Log in first.")
    try:
        return oidc.refresh_tokens(settings, refresh_token)
    except oidc.OidcError as exc:
        raise NotAuthenticatedError(str(exc)) from exc


def _out(u: AppUser) -> UserOut:
    return UserOut.model_validate(u, from_attributes=True)


def list_users(session: Session) -> list[UserOut]:
    return [_out(u) for u in session.scalars(select(AppUser).order_by(AppUser.username))]


def create_user(session: Session, body: UserCreate, by: CurrentUser) -> UserOut:
    u = AppUser(
        username=body.username.lower(),
        name=body.name,
        password_hash=hash_password(body.password),
        roles=sorted(set(body.roles)),
        active=True,
    )
    session.add(u)
    try:
        session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"User {body.username} already exists.") from exc
    audit(session, by, "user_create", "user", u.id, username=u.username, roles=u.roles)
    session.refresh(u)
    return _out(u)


def update_user(session: Session, user_id: int, body: UserUpdate, by: CurrentUser) -> UserOut:
    u = session.get(AppUser, user_id)
    if u is None:
        raise NotFoundError(f"User {user_id} not found.", {"user_id": user_id})
    changed: dict[str, object] = {}
    if body.name is not None:
        u.name = changed["name"] = body.name
    if body.roles is not None:
        u.roles = sorted(set(body.roles))
        changed["roles"] = u.roles
    if body.active is not None:
        u.active = changed["active"] = body.active
    if body.password is not None:
        u.password_hash = hash_password(body.password)
        changed["password"] = "changed"  # noqa: S105 (audit note, not a secret)
    if body.unlock:
        u.locked_until, u.failed_logins = None, 0
        changed["unlocked"] = True
    # A new password, deactivation, a role change or an explicit revoke ends every session.
    if (
        body.password is not None
        or body.active is False
        or body.roles is not None
        or (body.revoke_sessions)
    ):
        u.session_epoch += 1
        changed["sessions_revoked"] = True
    audit(session, by, "user_update", "user", u.id, **changed)
    session.flush()
    return _out(u)
