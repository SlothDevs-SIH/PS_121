"""FastAPI application factory. Run: ``uvicorn app.main:app``."""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.router import api_router, ws_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.health import DEFAULT_CHECKS, Check, ReadinessReport, run_checks
from app.core.logging import configure_logging
from app.core.metrics import instrument_api
from app.core.middleware import register_middleware


def get_health_checks() -> list[Check]:
    """Dependency so tests can replace the real network checks."""
    return DEFAULT_CHECKS


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="SMRITI API",
        summary="eRTMAC-NWIS offset-well knowledge and decision support (SIH PS 121)",
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    register_middleware(app)
    register_error_handlers(app)
    if settings.metrics_enabled:
        instrument_api(app)

    @app.get("/healthz", tags=["health"], summary="Liveness: the process is up")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/readyz",
        tags=["health"],
        summary="Readiness: database (with extensions), Redis and object storage reachable",
        response_model=ReadinessReport,
        responses={503: {"model": ReadinessReport}},
    )
    def readyz(
        settings: Annotated[Settings, Depends(get_settings)],
        checks: Annotated[list[Check], Depends(get_health_checks)],
    ) -> JSONResponse:
        report = run_checks(settings, checks)
        return JSONResponse(
            status_code=200 if report.status == "ready" else 503, content=report.model_dump()
        )

    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
