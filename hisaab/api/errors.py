"""The only place where Hisaab errors become HTTP responses (SE423 M1 Table 6.2)."""

from __future__ import annotations

import logging
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hisaab.domain.errors import (
    ConcurrencyError,
    ConflictError,
    HisaabError,
    NotFoundError,
    PermissionDeniedError,
    PersistenceError,
    ValidationError,
)

logger = logging.getLogger("hisaab.api")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

STATUS_BY_TYPE: list[tuple[type[HisaabError], int]] = [
    (ValidationError, 422),
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (ConflictError, 409),
    (ConcurrencyError, 503),
    (PersistenceError, 500),
]


def status_for(exc: HisaabError) -> int:
    for exc_type, status in STATUS_BY_TYPE:
        if isinstance(exc, exc_type):
            return status
    return 500


def _body(exc: HisaabError, status: int) -> dict:
    if status == 500:
        # Never show SQL, file paths or stack traces to the user (QR-10).
        return {"error": "InternalError", "message": "something went wrong",
                "request_id": request_id_var.get()}
    body = {"error": type(exc).__name__, "message": str(exc), "request_id": request_id_var.get()}
    if isinstance(exc, ValidationError):
        body["field"] = exc.field
        body["rule"] = exc.rule
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HisaabError)
    async def _hisaab_error(request: Request, exc: HisaabError) -> JSONResponse:
        status = status_for(exc)
        log = logger.error if status >= 500 else logger.info
        log(
            "%s %s -> %s %s: %s",
            request.method, request.url.path, status, type(exc).__name__, exc,
            exc_info=status == 500,
        )
        headers = {"Retry-After": "1"} if status == 503 else None
        return JSONResponse(_body(exc, status), status_code=status, headers=headers)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # The single allowed broad handler: last line of defence at the API boundary.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            {"error": "InternalError", "message": "something went wrong",
             "request_id": request_id_var.get()},
            status_code=500,
        )
