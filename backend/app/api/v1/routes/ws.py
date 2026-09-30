"""WebSockets (master plan §8), mounted at the application root: /ws/...

- ``/ws/wells/{well_id}/live``: at most one frame a second from the stream service's
  ``scores:{wellbore_id}`` stream (the latest frame wins), plus a ``status`` message every
  5 s saying whether the stream is stale (no frame for 30 s) and where the replay is.
- ``/ws/alerts``: every alert created or fused, as the full alert (optionally one well's).

Auth: the browser's session cookie (B6) or ``?token=`` (API clients; browsers cannot set
headers on a WebSocket); the user needs the ``read_live`` permission. Closes 4401 / 4403
otherwise. A cookie-authenticated socket must come from our own origin (the ``Origin``
header's host equals ``Host``), so another site cannot open it with the user's cookie.
"""

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlsplit

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.alerts.service import get_alert
from app.core.auth import user_for_token
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.models import Wellbore
from app.db.models.realtime import ReplaySession
from app.db.session import session_scope
from app.stream.service import ALERTS_KEY, scores_key

router = APIRouter()

FRAME_INTERVAL_S = 1.0
STATUS_INTERVAL_S = 5.0
STALE_AFTER_S = 30.0
WS_NOT_FOUND = 4404
WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403


def _same_origin(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:
        return True  # not a browser
    return urlsplit(origin).netloc == ws.headers.get("host", "")


def _ws_token(ws: WebSocket, token: str | None) -> tuple[str | None, int | None]:
    """(token, refusal code): ``?token=`` first, else the session cookie from our origin."""
    if token:
        return token, None
    cookie = ws.cookies.get(get_settings().session_cookie_name)
    if cookie and not _same_origin(ws):
        return None, WS_FORBIDDEN
    return cookie, None


def _authorise(token: str | None) -> int | None:
    """None when the socket may proceed, else the close code."""
    try:
        with session_scope() as s:
            user = user_for_token(get_settings(), s, token)
    except AppError as exc:
        return WS_UNAUTHENTICATED if exc.status_code == 401 else WS_FORBIDDEN
    return None if user.can("read_live") else WS_FORBIDDEN


async def _refuse(ws: WebSocket, code: int) -> None:
    msg = "log in first" if code == WS_UNAUTHENTICATED else "your role does not allow this"
    await ws.send_json({"type": "error", "error": {"code": code, "message": msg}})
    await ws.close(code=code)


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
async def live_well(ws: WebSocket, well_id: int, token: str | None = None) -> None:
    await ws.accept()
    token, code = _ws_token(ws, token)
    if code is None:
        code = await asyncio.to_thread(_authorise, token)
    if code is not None:
        await _refuse(ws, code)
        return
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
async def live_alerts(ws: WebSocket, well_id: int | None = None, token: str | None = None) -> None:
    await ws.accept()
    token, code = _ws_token(ws, token)
    if code is None:
        code = await asyncio.to_thread(_authorise, token)
    if code is not None:
        await _refuse(ws, code)
        return
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
