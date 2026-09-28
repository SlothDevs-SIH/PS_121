"""Request-ID and access-log middleware."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
log = logging.getLogger("smriti.access")


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Accept a caller-supplied ID only if it is short and printable; otherwise mint one.
        request_id = (
            incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.info("%s %s %.1fms", request.method, request.url.path, elapsed_ms)
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
