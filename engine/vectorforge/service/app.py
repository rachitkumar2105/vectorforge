"""FastAPI app factory."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vectorforge.service import errors
from vectorforge.service.database import Database
from vectorforge.service.observability import Metrics, configure_logging, log_event
from vectorforge.service.routes import router
from vectorforge.service.security import RateLimiter, Settings

access_log = logging.getLogger("vectorforge.access")


class BodySizeLimit:
    """Reject bodies over ``limit`` bytes with 413 (S4).

    Checks ``Content-Length`` up front, then reads the body itself, counting bytes, and stops at
    the limit. Counting matters because a chunked request has no Content-Length. The body is
    buffered (at most ``limit`` bytes) and replayed to the app, which keeps the rejection here
    instead of surfacing as a body-parsing error deep inside the framework.
    """

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_big = int(value) > self.limit
                except ValueError:
                    too_big = True
                if too_big:
                    await self._reject(scope, receive, send)
                    return
        chunks: list[bytes] = []
        seen = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break  # client went away; let the app see the disconnect
            body = message.get("body", b"")
            seen += len(body)
            if seen > self.limit:
                await self._reject(scope, receive, send)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = errors.error_response(
            413, "payload_too_large", f"body exceeds {self.limit} bytes"
        )
        await response(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging()
    db = Database(settings.data_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        db.load_all()
        log_event(access_log, "collections loaded", count=len(db.names()))
        yield
        db.close_all()  # checkpoints every collection, so the next start replays nothing

    docs: dict[str, Any] = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.production else {}
    )
    app = FastAPI(title="VectorForge", version="0.1.0", lifespan=lifespan, **docs)
    app.state.settings = settings
    app.state.db = db
    app.state.limiter = RateLimiter()
    app.state.metrics = Metrics()
    errors.install(app)
    app.include_router(router)

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Handled here rather than left to Starlette, which would re-raise to the server and
            # print a traceback (including the exception message) into the logs.
            log_event(errors.logger, "unhandled error", error_type=type(exc).__name__)
            response = errors.error_response(500, "internal_error", "internal error")
        elapsed = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        app.state.metrics.observe(request.method, route, response.status_code, elapsed)
        log_event(
            access_log,
            "request",
            method=request.method,
            route=route,
            status=response.status_code,
            duration_ms=round(elapsed * 1000, 3),
            role=getattr(request.state, "role", None),
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.production:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key"],
        allow_credentials=False,
        max_age=600,
    )
    # Outermost, so oversized bodies are refused before any other work happens.
    app.add_middleware(BodySizeLimit, limit=settings.max_body_bytes)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import os

    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.environ.get("HOST", "0.0.0.0"),  # noqa: S104 - container listens on all interfaces
        port=int(os.environ.get("PORT", "8000")),
        access_log=False,  # our own middleware logs requests without paths or bodies
        server_header=False,
        proxy_headers=False,
    )
