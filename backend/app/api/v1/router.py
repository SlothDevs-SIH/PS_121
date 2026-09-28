"""Version-1 API router. Every route except /meta and /me is a B0 skeleton returning 501."""

from fastapi import APIRouter, Depends

from app.api.v1.routes import knowledge, realtime, system, wells, ws
from app.core.auth import get_current_user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(knowledge.router, dependencies=[Depends(get_current_user)])
api_router.include_router(wells.router, dependencies=[Depends(get_current_user)])
api_router.include_router(realtime.router, dependencies=[Depends(get_current_user)])

# WebSockets live at the application root (/ws/...), matching master plan §8.
ws_router = ws.router
