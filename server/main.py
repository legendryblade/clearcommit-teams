"""FastAPI application factory for the ClearCommit Teams backend."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text as sql_text
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .config import Settings, load_settings
from .db import create_db_engine, make_session_factory
from .errors import ApiError, fail
from .events import EventHub
from .models import Base
from .rate_limit import RateLimiter
from .security import AuthError, TokenService

log = logging.getLogger("clearcommit.server")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Adds a request id and a structured log line (never request bodies)."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        if len(request_id) > 64:
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        log.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "user_id": getattr(request.state, "user_id", None),
                }
            )
        )
        return response


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return fail(request, exc.code, exc.message, exc.status, exc.retryable)

    @app.exception_handler(AuthError)
    async def handle_auth_error(request: Request, exc: AuthError):
        return fail(request, exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", []))
        message = f"Invalid request at '{location}'." if location else "Invalid request."
        return fail(request, "invalid_request", message, 422)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        log.exception("unhandled error")
        return fail(
            request,
            "internal_error",
            "The request could not be completed. Retry with the same request id if needed.",
            500,
            retryable=True,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = create_db_engine(settings)
    # Demo/SQLite bootstraps its schema here. For Supabase PostgreSQL the SQL
    # migrations in supabase/migrations own the schema (including RLS); this
    # call is a no-op when the tables already exist.
    Base.metadata.create_all(engine)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.hub.attach_loop(asyncio.get_running_loop())
        log.info(json.dumps({"event": "startup", "mode": settings.mode}))
        yield

    app = FastAPI(
        title="ClearCommit Teams API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.tokens = TokenService(settings)
    app.state.hub = EventHub()
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)

    app.add_middleware(RequestContextMiddleware)
    # The desktop client loads from file:// (origin "null") or the loopback
    # dev server. Authentication is bearer-token based, never cookie based, so
    # allowing these origins does not enable credential replay.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_origin_regex=r"^(https?://(127\.0\.0\.1|localhost)(:\d+)?)$",
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        max_age=600,
    )
    _install_exception_handlers(app)

    from .routers import auth, conversations, events, insights, messaging, orgs, playbook

    for router in (auth, orgs, conversations, insights, playbook, messaging, events):
        app.include_router(router.router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "status": "live", "version": __version__}

    @app.get("/ready")
    def ready(request: Request) -> JSONResponse:
        try:
            with engine.connect() as connection:
                connection.execute(sql_text("SELECT 1"))
        except Exception as exc:
            log.error("ready check failed: database unavailable")
            return JSONResponse(
                {
                    "ok": False,
                    "status": "not_ready",
                    "database": "unavailable",
                    "request_id": getattr(request.state, "request_id", None),
                    "detail": str(exc)[:200],
                },
                status_code=503,
            )
        if not app.state.tokens.check_reachable():
            return JSONResponse(
                {"ok": False, "status": "not_ready", "auth": "unreachable"},
                status_code=503,
            )
        return JSONResponse(
            {"ok": True, "status": "ready", "mode": settings.mode, "database": "ok"}
        )

    return app
