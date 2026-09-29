"""WebSockets (master plan §8), mounted at the application root: /ws/...

- ``/ws/wells/{well_id}/live``: at most one frame a second from the stream service's
  ``scores:{wellbore_id}`` stream (the latest frame wins), plus a ``status`` message every
  5 s saying whether the stream is stale (no frame for 30 s) and where the replay is.
- ``/ws/alerts``: every alert created or fused, as the full alert (optionally one well's).

Auth for WebSockets (token in the first message or a query parameter) lands in phase B6.
"""

import asyncio
import json
import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.alerts.service import get_alert
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.models import Wellbore
from app.db.models.realtime import ReplaySession
from app.db.session import session_scope
from app.stream.service import ALERTS_KEY, scores_key

router = APIRouter()

FRAME_INTERVAL_S = 1.0
STATUS_INTERVAL_S = 5.0
STALE_AFTER_S = 30.0
WS_NOT_FOUND = 4404


def _redis() -> "aioredis.Redis":
    client: aioredis.Redis = aioredis.Redis.from_url(
        get_settings().redis_url, decode_responses=True
    )
    return client


def _wellbore_and_session(well_id: int) -> tuple[int | None, dict[str, Any] | None]:
    with session_scope() as s:
        rs = s.scalar(
            select(ReplaySession)
            .where(ReplaySession.well_id == well_id)
            .order_by(ReplaySession.id.desc())
            .limit(1)
        )
        wb = (
            rs.wellbore_id
            if rs
            else s.scalar(
                select(Wellbore.id)
                .where(Wellbore.well_id == well_id)
                .order_by(Wellbore.id)
                .limit(1)
            )
        )
        info = (
            {
                "id": rs.id,
                "status": rs.status,
                "speed": rs.speed,
                "position": rs.position,
                "total_rows": rs.total_rows,
                "data_now": rs.data_now.isoformat() if rs.data_now else None,
            }
            if rs
            else None
        )
        return wb, info


@router.websocket("/ws/wells/{well_id}/live")
async def live_well(ws: WebSocket, well_id: int) -> None:
    await ws.accept()
    wb, info = await asyncio.to_thread(_wellbore_and_session, well_id)
    if wb is None:
        await ws.send_json({"type": "error", "error": {"code": "not_found"}})
        await ws.close(code=WS_NOT_FOUND)
        return
    r = _redis()
    key = scores_key(wb)
    last_id = "$"
    last_frame_at = 0.0
    last_sent = 0.0
    last_status = 0.0
    pending: dict[str, Any] | None = None
    try:
        await ws.send_json({"type": "hello", "well_id": well_id, "wellbore_id": wb, "replay": info})
        while True:
            resp = await r.xread({key: last_id}, count=200, block=250)
            for _, messages in resp or []:
                for msg_id, fields in messages:
                    last_id = msg_id
                    pending = json.loads(fields["frame"])
                    last_frame_at = time.monotonic()
            now = time.monotonic()
            if pending is not None and now - last_sent >= FRAME_INTERVAL_S:
                await ws.send_json({"type": "frame", "frame": pending})
                pending, last_sent = None, now
            if now - last_status >= STATUS_INTERVAL_S:
                _, info = await asyncio.to_thread(_wellbore_and_session, well_id)
                stale = last_frame_at == 0.0 or now - last_frame_at > STALE_AFTER_S
                await ws.send_json({"type": "status", "stale": stale, "replay": info})
                last_status = now
    except WebSocketDisconnect:
        pass
    finally:
        await r.aclose()


@router.websocket("/ws/alerts")
async def live_alerts(ws: WebSocket, well_id: int | None = None) -> None:
    await ws.accept()
    r = _redis()
    last_id = "$"
    try:
        await ws.send_json({"type": "hello", "well_id": well_id})
        while True:
            resp = await r.xread({ALERTS_KEY: last_id}, count=50, block=1000)
            for _, messages in resp or []:
                for msg_id, fields in messages:
                    last_id = msg_id
                    if well_id is not None and int(fields["well_id"]) != well_id:
                        continue
                    try:
                        alert = await asyncio.to_thread(_alert_json, int(fields["id"]))
                    except NotFoundError:
                        continue
                    await ws.send_json(
                        {"type": "alert", "action": fields["action"], "alert": alert}
                    )
    except WebSocketDisconnect:
        pass
    finally:
        await r.aclose()


def _alert_json(alert_id: int) -> dict[str, Any]:
    with session_scope() as s:
        return get_alert(s, alert_id).model_dump(mode="json")
