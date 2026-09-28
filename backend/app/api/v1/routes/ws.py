"""Skeleton WebSockets (master plan §8), mounted at the application root: /ws/...

Auth for WebSockets (token in the first message or a query parameter) lands in phase B6.
"""

from fastapi import APIRouter, WebSocket

router = APIRouter()

# Application close code (4000-4999 range) sent by skeleton WebSockets.
WS_NOT_IMPLEMENTED = 4501


async def _close_not_implemented(ws: WebSocket, feature: str) -> None:
    await ws.accept()
    await ws.send_json(
        {"error": {"code": "not_implemented", "message": f"{feature} is planned for phase B4."}}
    )
    await ws.close(code=WS_NOT_IMPLEMENTED)


@router.websocket("/ws/wells/{well_id}/live")
async def live_well(ws: WebSocket, well_id: int) -> None:
    await _close_not_implemented(ws, "Live well stream")


@router.websocket("/ws/alerts")
async def live_alerts(ws: WebSocket) -> None:
    await _close_not_implemented(ws, "Live alert push")
