"""Users and the audit log (admin only, B5)."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.params import NOT_FOUND
from app.api.v1.schemas.auth import AuditEntry, AuditPage, UserCreate, UserOut, UserUpdate
from app.core import users
from app.core.auth import CurrentUser, require
from app.db.models.auth import AuditLog
from app.db.session import get_session

router = APIRouter(tags=["admin"])
DbSession = Annotated[Session, Depends(get_session)]
Admin = Annotated[CurrentUser, Depends(require("admin"))]


@router.get("/users", summary="List users", response_model=list[UserOut])
def list_users(session: DbSession, _: Admin) -> list[UserOut]:
    return users.list_users(session)


@router.post("/users", summary="Create a user", response_model=UserOut, status_code=201)
def create_user(body: Annotated[UserCreate, Body()], session: DbSession, by: Admin) -> UserOut:
    out = users.create_user(session, body, by)
    session.commit()
    return out


@router.patch(
    "/users/{user_id}",
    summary="Change roles, name, password or deactivate",
    response_model=UserOut,
    responses=NOT_FOUND,
)
def update_user(
    user_id: int, body: Annotated[UserUpdate, Body()], session: DbSession, by: Admin
) -> UserOut:
    out = users.update_user(session, user_id, body, by)
    session.commit()
    return out


@router.get("/audit", summary="Audit log, newest first", response_model=AuditPage)
def audit_log(
    session: DbSession,
    _: Admin,
    user_id: str | None = None,
    action: str | None = None,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditPage:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    if before_id:
        q = q.where(AuditLog.id < before_id)
    rows = list(session.scalars(q))
    more = len(rows) > limit
    rows = rows[:limit]
    return AuditPage(
        items=[AuditEntry.model_validate(r, from_attributes=True) for r in rows],
        next_before_id=rows[-1].id if more and rows else None,
    )
