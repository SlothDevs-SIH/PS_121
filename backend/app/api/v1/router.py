"""Version-1 API router. Routes not yet built return 501 naming their phase."""

from fastapi import APIRouter, Depends

from app.api.v1.routes import documents, knowledge, realtime, system, wells, ws
from app.core.auth import get_current_user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(documents.router, dependencies=[Depends(get_current_user)])
api_router.include_router(knowledge.router, dependencies=[Depends(get_current_user)])
api_router.include_router(wells.router, dependencies=[Depends(get_current_user)])
api_router.include_router(realtime.router, dependencies=[Depends(get_current_user)])

# WebSockets live at the application root (/ws/...), matching master plan §8.
ws_router = ws.router
