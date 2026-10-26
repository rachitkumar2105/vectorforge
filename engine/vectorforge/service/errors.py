"""One error shape for every failure: ``{"error": {"code": str, "message": str}}``.

Messages are written by us, never copied from exceptions or request bodies, so no stack trace,
file path, key or submitted value can leak through an error response.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from vectorforge.service.observability import log_event

logger = logging.getLogger("vectorforge.errors")

STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    503: "not_ready",
}


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status, headers=headers
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Report where and what kind of problem, but never the offending input: pydantic's own
        # error objects include the submitted value, which may be a vector or private metadata.
        details = [
            {"loc": [str(p) for p in e.get("loc", ())][:6], "type": str(e.get("type", "invalid"))}
            for e in exc.errors()[:20]
        ]
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "request validation failed",
                    "details": details,
                }
            },
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "error")
        return error_response(exc.status_code, code, code.replace("_", " "))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log the exception type only; its message could contain data or internal paths.
        log_event(logger, "unhandled error", error_type=type(exc).__name__)
        return error_response(500, "internal_error", "internal error")
