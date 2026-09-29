"""Audit log writes (master plan §16: every login, document view, alert action, review
decision and copilot query). Rows join the caller's transaction, so an action and its
audit record commit together or not at all."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.core.logging import request_id_var
from app.db.models.auth import AuditLog


def audit(
    session: Session,
    user: CurrentUser | str,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    **detail: Any,
) -> None:
    session.add(
        AuditLog(
            user_id=user if isinstance(user, str) else user.user_id,
            action=action,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            detail=detail,
            request_id=request_id_var.get(None),
        )
    )
