"""Local users: login, and the admin operations behind /api/v1/users (B5, jwt mode)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.schemas.auth import Me, TokenOut, UserCreate, UserOut, UserUpdate
from app.core.audit import audit
from app.core.auth import (
    CurrentUser,
    NotAuthenticatedError,
    hash_password,
    issue_token,
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


def login(session: Session, settings: Settings, username: str, password: str) -> TokenOut:
    if settings.auth_mode != "jwt":
        raise ConflictError(
            f"Login is used in jwt auth mode; this server runs in {settings.auth_mode} mode.",
            {"auth_mode": settings.auth_mode},
        )
    u = session.scalar(select(AppUser).where(AppUser.username == username.strip().lower()))
    ok = verify_password(password, u.password_hash if u else _DUMMY_HASH)
    if u is None or not ok or not u.active:
        audit(session, username[:80], "login_failed", "user", username[:80])
        session.commit()
        raise NotAuthenticatedError("Wrong username or password.")
    u.last_login_at = datetime.now(tz=UTC)
    token, exp = issue_token(settings, u.id)
    audit(session, u.username, "login", "user", u.id)
    cur = CurrentUser.model_validate({"user_id": u.username, "name": u.name, "roles": u.roles})
    return TokenOut(access_token=token, expires_at=exp, user=me(cur, settings))


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
    audit(session, by, "user_update", "user", u.id, **changed)
    session.flush()
    return _out(u)
