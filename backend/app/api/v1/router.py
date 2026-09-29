"""Version-1 API router. Routes not yet built return 501 naming their phase."""

from fastapi import APIRouter, Depends

from app.api.v1.routes import (
    correlation,
    documents,
    events,
    knowledge,
    realtime,
    review,
    search,
    system,
    wells,
    ws,
)
from app.core.auth import get_current_user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
for module in (documents, review, events, search, correlation, knowledge, wells, realtime):
    api_router.include_router(module.router, dependencies=[Depends(get_current_user)])

# WebSockets live at the application root (/ws/...), matching master plan §8.
ws_router = ws.router
