"""Application factory: JSON API under /api/v1, web UI at /."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import api, web
from .config import Settings
from .db import Database
from .domain import CardService
from .errors import AppError

log = logging.getLogger("cardpay")


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


async def app_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, AppError)
    return JSONResponse(exc.to_body(), status_code=exc.status)


async def http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, HTTPException)
    if _is_api(request):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(AppError(exc.status_code, code, str(exc.detail)).to_body(), status_code=exc.status_code)
    if exc.status_code == 404:
        return web.templates.TemplateResponse(request, "not_found.html", {"flash": None}, status_code=404)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


async def server_error(request: Request, exc: Exception) -> Response:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    body = AppError(500, "INTERNAL_ERROR", "Internal server error.").to_body()
    return JSONResponse(body, status_code=500)


async def health(request: Request) -> Response:
    db: Database = request.app.state.db
    return JSONResponse({"status": "ok" if db.ping() else "degraded"})


class RequestLog:
    """Adds X-Request-Id to every response and logs one line per request.
    Tests send their own id, so a failing test can be matched to service logs."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        request_id = headers.get(b"x-request-id", b"").decode()[:64] or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        status = 0

        async def send_wrapper(message):  # type: ignore[no-untyped-def]
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
                message["headers"].append((b"x-content-type-options", b"nosniff"))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "%s %s %s %.1fms request_id=%s",
                scope["method"],
                scope["path"],
                status,
                (time.perf_counter() - started) * 1000,
                request_id,
            )


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        db = Database(settings.database_path)
        app.state.db = db
        app.state.cards = CardService(db, settings)
        yield

    static = Path(__file__).parent / "static"
    routes = [
        Route("/health", health, methods=["GET"]),
        Mount("/api/v1", routes=api.routes),
        Mount("/static", app=StaticFiles(directory=str(static)), name="static"),
        *web.routes,
    ]
    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(RequestLog),
            Middleware(
                SessionMiddleware,
                secret_key=settings.session_secret,
                session_cookie="cardpay_session",
                same_site="lax",
                https_only=False,
            ),
        ],
        exception_handlers={AppError: app_error, HTTPException: http_error, Exception: server_error},
    )


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
