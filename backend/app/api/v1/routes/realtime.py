"""Real-time routes: replay control, stream status, a well's live window, alerts (B4)."""

import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.alerts import service as alerts
from app.api.v1.params import NOT_FOUND
from app.api.v1.schemas.realtime import (
    AlertDismiss,
    AlertFeedbackIn,
    AlertFeedbackOut,
    AlertOut,
    AlertPage,
    RealtimeWindow,
    ReplayRequest,
    ReplaySessionOut,
    StreamStatus,
)
from app.core.audit import audit
from app.core.auth import CurrentUser, get_current_user, require
from app.db.session import get_session
from app.db.vocab import AlertSeverity, AlertStatus
from app.risk import assets
from app.stream import control
from app.stream.service import HEARTBEAT_KEY, get_redis

router = APIRouter()
DbSession = Annotated[Session, Depends(get_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"description": "The alert or replay is not in a state that allows this"}
}

_thresholds: tuple[float, dict[str, float]] | None = None


def model_thresholds() -> dict[str, float]:
    """Alert threshold per event type from the model metrics (cached for 5 min)."""
    global _thresholds
    if _thresholds is None or time.monotonic() - _thresholds[0] > 300:
        try:
            metrics: dict[str, Any] = json.loads(assets.get_object(assets.METRICS_KEY))
            th = {t: float(m["threshold"]) for t, m in metrics.get("types", {}).items()}
        except Exception:
            th = {}
        _thresholds = (time.monotonic(), th)
    return _thresholds[1]


@router.get(
    "/alerts",
    dependencies=[Depends(require("read_live"))],
    tags=["alerts"],
    summary="List alerts",
    response_model=AlertPage,
)
def list_alerts(
    session: DbSession,
    well_id: int | None = None,
    status: Annotated[list[AlertStatus] | None, Query()] = None,
    severity: Annotated[list[AlertSeverity] | None, Query()] = None,
    session_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AlertPage:
    """Newest first (by data time). ``counts`` covers the scope before the status filter."""
    return alerts.list_alerts(
        session,
        well_id=well_id,
        status=list(status) if status else None,
        severity=list(severity) if severity else None,
        session_id=session_id,
        limit=limit,
    )


@router.get(
    "/alerts/{alert_id}",
    dependencies=[Depends(require("read_live"))],
    tags=["alerts"],
    summary="Alert detail with evidence and recommendations",
    response_model=AlertOut,
    responses=NOT_FOUND,
)
def get_alert(alert_id: int, session: DbSession) -> AlertOut:
    return alerts.get_alert(session, alert_id)


@router.post(
    "/alerts/{alert_id}/ack",
    dependencies=[Depends(require("act_alerts"))],
    tags=["alerts"],
    summary="Acknowledge an alert",
    response_model=AlertOut,
    responses={**NOT_FOUND, **CONFLICT},
)
def ack_alert(alert_id: int, session: DbSession, user: User) -> AlertOut:
    out = alerts.ack(session, alert_id, user.user_id)
    audit(session, user, "alert_ack", "alert", alert_id)
    session.commit()
    return out


@router.post(
    "/alerts/{alert_id}/dismiss",
    dependencies=[Depends(require("act_alerts"))],
    tags=["alerts"],
    summary="Dismiss an alert with reason",
    response_model=AlertOut,
    responses={**NOT_FOUND, **CONFLICT},
)
def dismiss_alert(
    alert_id: int, body: Annotated[AlertDismiss, Body()], session: DbSession, user: User
) -> AlertOut:
    out = alerts.dismiss(session, alert_id, body.reason, user.user_id)
    audit(session, user, "alert_dismiss", "alert", alert_id, reason=body.reason)
    session.commit()
    return out


@router.post(
    "/alerts/{alert_id}/feedback",
    dependencies=[Depends(require("act_alerts"))],
    tags=["alerts"],
    summary="Useful / not useful / false alarm",
    response_model=AlertFeedbackOut,
    status_code=201,
    responses=NOT_FOUND,
)
def alert_feedback(
    alert_id: int, body: Annotated[AlertFeedbackIn, Body()], session: DbSession, user: User
) -> AlertFeedbackOut:
    out = alerts.feedback(session, alert_id, body.verdict, body.comment, user.user_id)
    audit(session, user, "alert_feedback", "alert", alert_id, verdict=body.verdict)
    session.commit()
    return out


@router.post(
    "/replay",
    dependencies=[Depends(require("control_replay"))],
    tags=["replay"],
    summary="Start/pause/resume/stop/speed a replay session",
    response_model=ReplaySessionOut,
    responses={**NOT_FOUND, **CONFLICT},
)
def replay(
    body: Annotated[ReplayRequest, Body()], session: DbSession, user: User
) -> ReplaySessionOut:
    """``start`` replays the well's SYNTHETIC replay file from the beginning (replacing its
    earlier replayed samples; alerts are kept) at ``speed`` data seconds per second."""
    out = control.replay(session, body.well_id, body.action, body.speed)
    audit(session, user, f"replay_{body.action}", "well", body.well_id, speed=body.speed)
    session.commit()
    return out


@router.get(
    "/replay",
    dependencies=[Depends(require("read_live"))],
    tags=["replay"],
    summary="Recent replay sessions",
    response_model=list[ReplaySessionOut],
)
def list_replays(session: DbSession) -> list[ReplaySessionOut]:
    return control.sessions(session)


@router.get(
    "/stream/status",
    dependencies=[Depends(require("read_live"))],
    tags=["replay"],
    summary="Stream service heartbeat and sessions",
    response_model=StreamStatus,
)
def stream_status(session: DbSession) -> StreamStatus:
    try:
        hb = get_redis().get(HEARTBEAT_KEY)
    except Exception:
        hb = None
    return control.status(session, str(hb) if hb else None)


@router.get(
    "/wells/{well_id}/realtime",
    dependencies=[Depends(require("read_live"))],
    tags=["replay"],
    summary="The last minutes of a well's stream (downsampled) with scores",
    response_model=RealtimeWindow,
    responses=NOT_FOUND,
)
def realtime_window(
    well_id: int,
    session: DbSession,
    minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 120,
    max_points: Annotated[int, Query(ge=10, le=5000)] = 720,
) -> RealtimeWindow:
    return control.window(session, well_id, minutes, max_points, model_thresholds())
