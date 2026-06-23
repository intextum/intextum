"""Document extraction LLM upstream transport helpers."""

import logging
from typing import Any

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from services.ai_limits import (
    DEFAULT_CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS,
    acquire_ai_request_slot,
)
from .proxy_common import _sse_error_event


logger = logging.getLogger(__name__)


async def _post_document_extraction_llm(
    *,
    target_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float | None,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False
        ) as client:
            response = await client.post(
                target_url,
                json=payload,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        logger.warning(
            "Document extraction LLM upstream timed out",
            extra={"timeout_seconds": timeout_seconds},
        )
        raise HTTPException(
            status_code=504,
            detail="Document extraction LLM request timed out",
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "Document extraction LLM upstream request failed",
            extra={
                "error": str(exc) or repr(exc),
                "error_type": type(exc).__name__,
                "timeout_seconds": timeout_seconds,
                "target_url": target_url,
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Document extraction LLM request failed",
        ) from exc

    return response


async def _stream_document_extraction_llm(
    *,
    target_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float | None,
    settings: object,
) -> StreamingResponse:
    """Forward a streaming chat-completions request and pipe SSE chunks back."""
    slot = await acquire_ai_request_slot(
        settings,
        name="document_extraction_llm",
        concurrency_attr="CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS",
        default_concurrency=DEFAULT_CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS,
        busy_detail="Document extraction LLM service is busy",
    )

    async def _iter_upstream():
        try:
            async with (
                httpx.AsyncClient(
                    timeout=timeout_seconds, follow_redirects=False
                ) as client,
                client.stream(
                    "POST",
                    target_url,
                    json=payload,
                    headers=headers,
                ) as response,
            ):
                if response.status_code >= 400:
                    body = await response.aread()
                    message = body.decode("utf-8", errors="replace")
                    logger.warning(
                        "Document extraction LLM upstream returned error status",
                        extra={
                            "status_code": response.status_code,
                            "target_url": target_url,
                        },
                    )
                    yield _sse_error_event(
                        message=message,
                        error_type="upstream_error",
                        status_code=response.status_code,
                    )
                    return
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.TimeoutException as exc:
            logger.warning(
                "Document extraction LLM upstream timed out",
                extra={"timeout_seconds": timeout_seconds},
            )
            yield _sse_error_event(
                message="upstream timeout",
                error_type="timeout",
            )
            raise HTTPException(
                status_code=504,
                detail="Document extraction LLM request timed out",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Document extraction LLM upstream request failed",
                extra={
                    "error": str(exc) or repr(exc),
                    "error_type": type(exc).__name__,
                    "timeout_seconds": timeout_seconds,
                    "target_url": target_url,
                },
            )
            yield _sse_error_event(
                message="upstream request failed",
                error_type="request_error",
            )
        finally:
            slot.release()

    return StreamingResponse(
        _iter_upstream(),
        media_type="text/event-stream",
    )
