"""Skeleton routes for alerts, copilot and replay."""

from fastapi import APIRouter

from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError

router = APIRouter(responses=NOT_IMPLEMENTED)


@router.get("/alerts", tags=["alerts"], summary="List alerts")
def list_alerts(well_id: int | None = None, status: str | None = None) -> None:
    raise NotImplementedYetError("Alert list (S9)", "B4")


@router.post("/alerts/{alert_id}/ack", tags=["alerts"], summary="Acknowledge an alert")
def ack_alert(alert_id: int) -> None:
    raise NotImplementedYetError("Alert lifecycle (S9)", "B4")


@router.post("/alerts/{alert_id}/dismiss", tags=["alerts"], summary="Dismiss an alert with reason")
def dismiss_alert(alert_id: int) -> None:
    raise NotImplementedYetError("Alert lifecycle (S9)", "B4")


@router.post("/alerts/{alert_id}/feedback", tags=["alerts"], summary="Useful / not useful")
def alert_feedback(alert_id: int) -> None:
    raise NotImplementedYetError("Alert feedback (S9)", "B4")


@router.post("/copilot/chat", tags=["copilot"], summary="Ask the copilot (SSE stream)")
def copilot_chat() -> None:
    raise NotImplementedYetError("Copilot (S10)", "B5")


@router.post("/replay", tags=["replay"], summary="Start/stop/speed a replay session")
def replay() -> None:
    raise NotImplementedYetError("Replay adapter (S12)", "B4")
