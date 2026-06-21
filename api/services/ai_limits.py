"""Shared timeout and concurrency guards for upstream AI calls."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeVar

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_AI_BACKPRESSURE_WAIT_SECONDS = 0.25
DEFAULT_AI_CLIENT_MAX_RETRIES = 1
DEFAULT_CHAT_TIMEOUT_SECONDS = 300.0
DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS = 4
DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 60.0
DEFAULT_EMBEDDING_MAX_CONCURRENT_REQUESTS = 8
DEFAULT_PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS = 2
DEFAULT_CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS = 2

_LIMITERS: dict[tuple[int, str, int], asyncio.Semaphore] = {}


def settings_positive_float(
    settings: object,
    attr_name: str,
    default: float,
    *,
    minimum: float = 0.001,
) -> float:
    raw_value = getattr(settings, attr_name, default)
    if not isinstance(raw_value, int | float | str):
        return default
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def settings_positive_int(settings: object, attr_name: str, default: int) -> int:
    raw_value = getattr(settings, attr_name, default)
    if not isinstance(raw_value, int | float | str):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def ai_backpressure_wait_seconds(settings: object) -> float:
    return settings_positive_float(
        settings,
        "AI_BACKPRESSURE_WAIT_SECONDS",
        DEFAULT_AI_BACKPRESSURE_WAIT_SECONDS,
        minimum=0.0,
    )


def ai_client_max_retries(settings: object) -> int:
    raw_value = getattr(
        settings, "AI_CLIENT_MAX_RETRIES", DEFAULT_AI_CLIENT_MAX_RETRIES
    )
    if not isinstance(raw_value, int | float | str):
        return DEFAULT_AI_CLIENT_MAX_RETRIES
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_AI_CLIENT_MAX_RETRIES
    return max(0, value)


def ai_timeout_seconds(
    settings: object,
    attr_name: str,
    default: float,
) -> float:
    return settings_positive_float(settings, attr_name, default)


def _limiter(name: str, max_concurrency: int) -> asyncio.Semaphore:
    key = (id(asyncio.get_running_loop()), name, max_concurrency)
    limiter = _LIMITERS.get(key)
    if limiter is None:
        limiter = asyncio.Semaphore(max_concurrency)
        _LIMITERS[key] = limiter
    return limiter


@dataclass(slots=True)
class AiRequestSlot:
    """One acquired upstream AI concurrency slot."""

    _semaphore: asyncio.Semaphore
    _released: bool = False

    def release(self) -> None:
        if not self._released:
            self._semaphore.release()
            self._released = True

    async def __aenter__(self) -> "AiRequestSlot":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.release()


async def acquire_ai_request_slot(
    settings: object,
    *,
    name: str,
    concurrency_attr: str,
    default_concurrency: int,
    busy_detail: str,
) -> AiRequestSlot:
    """Acquire a bounded AI concurrency slot or raise 503 when saturated."""
    max_concurrency = settings_positive_int(
        settings,
        concurrency_attr,
        default_concurrency,
    )
    limiter = _limiter(name, max_concurrency)
    wait_seconds = ai_backpressure_wait_seconds(settings)

    if wait_seconds <= 0 and limiter.locked():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=busy_detail,
        )

    try:
        await asyncio.wait_for(
            limiter.acquire(),
            timeout=max(wait_seconds, 0.001),
        )
    except TimeoutError as exc:
        logger.warning(
            "AI upstream concurrency limit saturated",
            extra={
                "ai_limit_name": name,
                "max_concurrency": max_concurrency,
                "wait_seconds": wait_seconds,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=busy_detail,
        ) from exc

    return AiRequestSlot(limiter)


@asynccontextmanager
async def ai_request_slot(
    settings: object,
    *,
    name: str,
    concurrency_attr: str,
    default_concurrency: int,
    busy_detail: str,
):
    """Async context manager wrapper around ``acquire_ai_request_slot``."""
    slot = await acquire_ai_request_slot(
        settings,
        name=name,
        concurrency_attr=concurrency_attr,
        default_concurrency=default_concurrency,
        busy_detail=busy_detail,
    )
    try:
        yield slot
    finally:
        slot.release()


def _is_timeout_exception(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    class_name = type(exc).__name__.lower()
    return "timeout" in class_name or "timedout" in class_name


async def run_ai_call(
    operation: Callable[[], Awaitable[T]],
    *,
    settings: object,
    name: str,
    timeout_attr: str,
    default_timeout_seconds: float,
    concurrency_attr: str,
    default_concurrency: int,
    timeout_detail: str,
    busy_detail: str,
) -> T:
    """Run one upstream AI operation with timeout and concurrency backpressure."""
    timeout_seconds = ai_timeout_seconds(
        settings, timeout_attr, default_timeout_seconds
    )
    slot = await acquire_ai_request_slot(
        settings,
        name=name,
        concurrency_attr=concurrency_attr,
        default_concurrency=default_concurrency,
        busy_detail=busy_detail,
    )
    async with slot:
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except Exception as exc:
            if _is_timeout_exception(exc):
                logger.warning(
                    "AI upstream request timed out",
                    extra={
                        "ai_limit_name": name,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=timeout_detail,
                ) from exc
            raise


async def create_embedding_response(
    client: object,
    settings: object,
    *,
    model: str,
    texts: list[str],
) -> object:
    """Call an OpenAI-compatible embedding client behind shared AI limits."""

    async def _operation() -> object:
        create = client.embeddings.create
        if inspect.iscoroutinefunction(create):
            return await create(model=model, input=texts)
        result = await asyncio.to_thread(create, model=model, input=texts)
        if inspect.isawaitable(result):
            return await result
        return result

    return await run_ai_call(
        _operation,
        settings=settings,
        name="embedding",
        timeout_attr="EMBEDDING_TIMEOUT_SECONDS",
        default_timeout_seconds=DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
        concurrency_attr="EMBEDDING_MAX_CONCURRENT_REQUESTS",
        default_concurrency=DEFAULT_EMBEDDING_MAX_CONCURRENT_REQUESTS,
        timeout_detail="Embedding request timed out",
        busy_detail="Embedding service is busy",
    )
