"""One error envelope for every non-2xx response.

{"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    headers: dict[str, str] | None = None

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message, {"retry_after_s": retry_after_s})
        self.headers = {"Retry-After": str(retry_after_s)}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class NotImplementedYetError(AppError):
    """Raised by skeleton endpoints: the route and contract exist, the logic lands in `phase`."""

    status_code = 501
    code = "not_implemented"

    def __init__(self, feature: str, phase: str) -> None:
        super().__init__(
            f"{feature} is planned for backend phase {phase} and is not implemented yet.",
            {"feature": feature, "phase": phase},
        )


def _envelope(
    status: int,
    code: str,
    message: str,
    details: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, details=details, request_id=request_id_var.get()
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


# Shared OpenAPI declaration for skeleton routes.
NOT_IMPLEMENTED: dict[int | str, dict[str, Any]] = {
    501: {"model": ErrorResponse, "description": "Planned, not implemented in this phase"}
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, str(exc.detail), {})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder: a validator raising ValueError puts the exception object in
        # errors()[i]["ctx"], which would otherwise break JSON serialisation (500, not 422).
        return _envelope(
            422,
            "validation_error",
            "Request validation failed",
            {"errors": jsonable_encoder(exc.errors())},
        )
