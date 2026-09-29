"""Alert queries and lifecycle over the database (S9): list, detail, ack, dismiss, feedback.

Lifecycle: new → ack → (actioned | closed), or new → dismissed (with a reason). The stream
service reads acks and dismissals back into its engine for the 30-min cooldown.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.realtime import AlertFeedbackOut, AlertOut, AlertPage
from app.core.errors import AppError, NotFoundError
from app.db.models import Well
from app.db.models.realtime import Alert, AlertFeedback


class AlertStateError(AppError):
    status_code = 409
    code = "invalid_alert_state"


def _feedback(session: Session, ids: list[int]) -> dict[int, list[AlertFeedbackOut]]:
    rows = session.scalars(
        select(AlertFeedback)
        .where(AlertFeedback.alert_id.in_(ids or [-1]))
        .order_by(AlertFeedback.id)
    ).all()
    out: dict[int, list[AlertFeedbackOut]] = {}
    for r in rows:
        out.setdefault(r.alert_id, []).append(
            AlertFeedbackOut(
                id=r.id,
                alert_id=r.alert_id,
                verdict=r.verdict,
                comment=r.comment,
                user_id=r.user_id,
                created_at=r.created_at,
            )
        )
    return out


def _out(a: Alert, well: Well, feedback: list[AlertFeedbackOut]) -> AlertOut:
    return AlertOut.model_validate(
        {
            "id": a.id,
            "well_id": a.well_id,
            "well_name": well.canonical_name,
            "synthetic": well.synthetic,
            "wellbore_id": a.wellbore_id,
            "session_id": a.session_id,
            "alert_type": a.alert_type,
            "event_type": a.event_type,
            "severity": a.severity,
            "status": a.status,
            "title": a.title,
            "message": a.message,
            "score": a.score,
            "score_kind": a.score_kind,
            "md_m": a.md_m,
            "tvdss_m": a.tvdss_m,
            "formation": a.formation,
            "t_data": a.t_data,
            "created_at": a.created_at,
            "sources": a.sources,
            "evidence": a.evidence,
            "drivers": a.drivers,
            "recommendations": a.recommendations,
            "detail": a.detail,
            "budget_exempt": a.budget_exempt,
            "acked_by": a.acked_by,
            "acked_at": a.acked_at,
            "dismiss_reason": a.dismiss_reason,
            "feedback": feedback,
        }
    )


def list_alerts(
    session: Session,
    *,
    well_id: int | None = None,
    status: list[str] | None = None,
    severity: list[str] | None = None,
    session_id: int | None = None,
    limit: int = 100,
) -> AlertPage:
    scope = select(Alert.id)
    if well_id is not None:
        scope = scope.where(Alert.well_id == well_id)
    if session_id is not None:
        scope = scope.where(Alert.session_id == session_id)
    if severity:
        scope = scope.where(Alert.severity.in_(severity))
    counts = dict(
        session.execute(
            select(Alert.status, func.count())
            .where(Alert.id.in_(scope.scalar_subquery()))
            .group_by(Alert.status)
        )
        .tuples()
        .all()
    )
    q = select(Alert, Well).join(Well, Well.id == Alert.well_id).where(Alert.id.in_(scope))
    if status:
        q = q.where(Alert.status.in_(status))
    rows = session.execute(q.order_by(Alert.t_data.desc(), Alert.id.desc()).limit(limit)).all()
    fb = _feedback(session, [a.id for a, _ in rows])
    return AlertPage(
        items=[_out(a, w, fb.get(a.id, [])) for a, w in rows],
        counts={str(k): int(v) for k, v in counts.items()},
    )


def _get(session: Session, alert_id: int) -> tuple[Alert, Well]:
    row = session.execute(
        select(Alert, Well).join(Well, Well.id == Alert.well_id).where(Alert.id == alert_id)
    ).first()
    if row is None:
        raise NotFoundError(f"Alert {alert_id} not found.", {"alert_id": alert_id})
    return row[0], row[1]


def get_alert(session: Session, alert_id: int) -> AlertOut:
    a, w = _get(session, alert_id)
    return _out(a, w, _feedback(session, [a.id]).get(a.id, []))


def ack(session: Session, alert_id: int, user: str) -> AlertOut:
    a, _ = _get(session, alert_id)
    if a.status != "new":
        raise AlertStateError(f"Alert {alert_id} is {a.status}; only a new alert can be acked.")
    a.status, a.acked_by, a.acked_at = "ack", user, datetime.now(tz=UTC)
    session.flush()
    return get_alert(session, alert_id)


def dismiss(session: Session, alert_id: int, reason: str, user: str) -> AlertOut:
    a, _ = _get(session, alert_id)
    if a.status not in ("new", "ack"):
        raise AlertStateError(f"Alert {alert_id} is {a.status}; it cannot be dismissed.")
    a.status, a.dismiss_reason, a.closed_at = "dismissed", reason, datetime.now(tz=UTC)
    a.acked_by = a.acked_by or user
    session.flush()
    return get_alert(session, alert_id)


def feedback(
    session: Session, alert_id: int, verdict: str, comment: str | None, user: str
) -> AlertFeedbackOut:
    _get(session, alert_id)
    row = AlertFeedback(alert_id=alert_id, verdict=verdict, comment=comment, user_id=user)
    session.add(row)
    session.flush()
    session.refresh(row)
    return _feedback(session, [alert_id])[alert_id][-1]
