"""FastAPI application for the intextum backend."""

import os
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from typing import Optional
from app_http import (
    attach_security_headers,
    build_internal_error_response,
    correlation_id_from_header,
)
from app_runtime import (
    shutdown_runtime,
    start_background_tasks,
    start_watcher,
    warn_missing_auth_proxy_secret,
)
from chat.runner import process_next_chat_run
from routers import (
    auth,
    chat_prompt_presets,
    client_errors,
    content,
    conversations,
    events,
    exports,
    me,
    permissions,
    search,
    worker,
    workers,
)
from auth.dependencies import get_current_user
from auth.payloads import user_payload
from auth.providers import resolve_request_user
from auth.startup import bootstrap_local_auth
from models.user import User
from logging_config import setup_logging, correlation_id_var, get_logger
from database import init_db, AsyncSessionLocal
from chat.checkpointer import close_chat_checkpointer, init_chat_checkpointer
from config import get_settings, validate_production_settings
from version import get_app_version
from services.valkey import (
    close_valkey_client,
    init_valkey_client,
    is_valkey_configured,
    probe_valkey,
)
from services.watcher import WatcherService

setup_logging()
logger = get_logger(__name__)

_watcher = WatcherService()

STALE_CLEANUP_INTERVAL = 300  # 5 minutes
CHAT_RUNNER_ID = f"{socket.gethostname()}:{os.getpid()}"
PASSWORD_CHANGE_ALLOWED_PATHS = {
    "/api/me",
    "/api/auth/change-password",
    "/api/auth/logout",
}


def _task_queue_service_factory(db):
    """Create the task queue service used by background maintenance loops."""
    from services.task_queue import TaskQueueService

    return TaskQueueService(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    validate_production_settings(settings)
    await init_db()
    await init_chat_checkpointer()
    await init_valkey_client()

    await bootstrap_local_auth(settings, session_factory=AsyncSessionLocal)

    warn_missing_auth_proxy_secret(get_settings(), logger)

    app.state.watcher = _watcher
    await start_watcher(_watcher)
    background_tasks = start_background_tasks(
        session_factory=AsyncSessionLocal,
        logger=logger,
        settings=settings,
        runner_id=CHAT_RUNNER_ID,
        stale_cleanup_interval_seconds=STALE_CLEANUP_INTERVAL,
        task_queue_service_factory=_task_queue_service_factory,
        process_next_chat_run=process_next_chat_run,
        valkey_configured=is_valkey_configured(),
    )
    try:
        yield
    finally:
        await shutdown_runtime(
            background_tasks=background_tasks,
            watcher=_watcher,
            close_valkey_client=close_valkey_client,
            close_chat_checkpointer=close_chat_checkpointer,
        )


app = FastAPI(
    title="intextum Backend",
    description="Document Management System API with file browsing and semantic search",
    version=get_app_version(),
    lifespan=lifespan,
)

settings = get_settings()
if not settings.CORS_ALLOW_ORIGINS:
    logger.warning(
        "CORS_ALLOW_ORIGINS is empty — browsers will reject credentialed "
        "cross-origin requests. Set CORS_ALLOW_ORIGINS_STR in production."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to each request for tracing."""
    correlation_id = correlation_id_from_header(
        request.headers.get("X-Correlation-ID", "")
    )
    token = correlation_id_var.set(correlation_id)

    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        correlation_id_var.reset(token)


@app.middleware("http")
async def auth_context_middleware(request: Request, call_next):
    """Resolve request auth once and enforce CSRF for local-session writes."""
    request.state.current_user = await resolve_request_user(
        request,
        session_factory=AsyncSessionLocal,
    )

    current_user: User | None = getattr(request.state, "current_user", None)
    if (
        current_user is not None
        and current_user.auth_provider == "local"
        and current_user.must_change_password
        and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Password change required",
                "code": "password_change_required",
            },
        )

    if (
        current_user is not None
        and current_user.auth_provider == "local"
        and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
    ):
        csrf_cookie = request.cookies.get(settings.AUTH_CSRF_COOKIE_NAME, "")
        csrf_header = request.headers.get(settings.AUTH_CSRF_HEADER_NAME, "")
        if (
            not csrf_cookie
            or not csrf_header
            or csrf_cookie != csrf_header
            or csrf_cookie != (current_user.csrf_token or "")
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )

    response = await call_next(request)
    if (
        current_user is not None
        and current_user.auth_provider == "local"
        and current_user.csrf_token
    ):
        response.set_cookie(
            settings.AUTH_CSRF_COOKIE_NAME,
            current_user.csrf_token,
            httponly=False,
            secure=settings.AUTH_SESSION_SECURE_COOKIE,
            samesite="lax",
            path="/",
            max_age=settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
        )
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach baseline hardening headers to API responses."""
    response = await call_next(request)
    attach_security_headers(response)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a sanitized response."""
    return build_internal_error_response(request, logger=logger, exc=exc)


app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(chat_prompt_presets.router, prefix="/api/chat", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(client_errors.router, prefix="/api", tags=["client-errors"])
app.include_router(search.router, prefix="/api/query", tags=["search"])
app.include_router(workers.router, prefix="/api/workers", tags=["workers"])
app.include_router(worker.router, prefix="/api/worker", tags=["worker-api"])
app.include_router(
    conversations.router, prefix="/api/conversations", tags=["conversations"]
)
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
app.include_router(me.router, prefix="/api", tags=["me"])
app.include_router(permissions.router, prefix="/api", tags=["permissions"])


@app.get("/health/live")
def health_live_explicit():
    """Liveness endpoint."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(request: Request):
    """Readiness endpoint validating external dependencies."""
    components: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        components["postgres"] = "ok"
    except Exception as e:
        logger.warning("Readiness check failed for Postgres: %s", e)
        components["postgres"] = "error"

    if is_valkey_configured():
        try:
            if await probe_valkey():
                components["valkey"] = "ok"
            else:
                components["valkey"] = "error"
        except Exception as e:
            logger.warning("Readiness check failed for Valkey: %s", e)
            components["valkey"] = "error"

    watcher = getattr(request.app.state, "watcher", None)
    watcher_ready = True
    if watcher is not None:
        is_ready = getattr(watcher, "is_ready", None)
        if callable(is_ready):
            watcher_ready = bool(is_ready())
    if not watcher_ready:
        components["watcher"] = "error"

    ready = all(status == "ok" for status in components.values())
    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ready else "degraded",
            "components": components,
        },
    )


@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "name": "intextum Backend",
        "version": get_app_version(),
        "docs": "/docs",
        "health": "/health/live",
        "readiness": "/health/ready",
    }


@app.get("/api/me")
def get_me(user: Optional[User] = Depends(get_current_user)):
    """
    Get current user information from the active auth context.

    Local sessions, trusted proxy headers, or unauthenticated local-dev access
    are resolved by the shared auth dependency.
    """
    return user_payload(user)
