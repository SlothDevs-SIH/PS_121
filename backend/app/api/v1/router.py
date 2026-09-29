"""Version-1 API router. Routes not yet built return 501 naming their phase."""

from fastapi import APIRouter, Depends

from app.api.v1.routes import (
    admin,
    copilot,
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
from app.core.auth import require

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(admin.router)  # its routes require the admin permission
for module in (
    documents,
    review,
    events,
    search,
    correlation,
    knowledge,
    wells,
    realtime,
    copilot,
):
    api_router.include_router(module.router, dependencies=[Depends(require("read_knowledge"))])

# WebSockets live at the application root (/ws/...), matching master plan §8.
ws_router = ws.router
