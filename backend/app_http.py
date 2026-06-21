"""HTTP-layer helpers for middleware and exception handling."""

from __future__ import annotations

import re
import uuid
from logging import Logger

from fastapi import Request
from fastapi.responses import JSONResponse

from logging_config import correlation_id_var

_CORRELATION_ID_RE = re.compile(r"^[\w\-\.]{1,128}$")


def correlation_id_from_header(raw_id: str) -> str:
    """Normalize a caller-supplied correlation id or generate a new one."""
    return raw_id if _CORRELATION_ID_RE.match(raw_id) else str(uuid.uuid4())


def attach_security_headers(response) -> None:
    """Attach baseline hardening headers to API responses."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )


def build_internal_error_response(
    request: Request,
    *,
    logger: Logger,
    exc: Exception,
) -> JSONResponse:
    """Create the standardized unhandled-exception response payload."""
    correlation_id = (
        correlation_id_var.get()
        or request.headers.get("X-Correlation-ID")
        or str(uuid.uuid4())
    )
    logger.exception(
        "Unhandled exception (correlation_id=%s) on %s %s",
        correlation_id,
        request.method,
        request.url.path,
    )

    response = JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "correlation_id": correlation_id,
        },
    )
    if correlation_id:
        response.headers["X-Correlation-ID"] = correlation_id
    return response
