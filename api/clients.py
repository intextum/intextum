"""Centralized client initialization for external services."""

from functools import lru_cache

from openai import AsyncOpenAI, OpenAI

from config import get_settings
from services.ai_limits import (
    DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
    ai_client_max_retries,
    ai_timeout_seconds,
)


# --- Sync clients (used by search router, worker helpers) ---


@lru_cache()
def get_embedding_client() -> OpenAI:
    """Get cached synchronous OpenAI-compatible embedding client."""
    settings = get_settings()
    return OpenAI(
        base_url=settings.EMBEDDING_API_BASE,
        api_key=settings.EMBEDDING_API_KEY,
        timeout=ai_timeout_seconds(
            settings,
            "EMBEDDING_TIMEOUT_SECONDS",
            DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
        ),
        max_retries=ai_client_max_retries(settings),
    )


# --- Async clients (used by conversations engine) ---


@lru_cache()
def get_async_embedding_client() -> AsyncOpenAI:
    """Get cached asynchronous OpenAI-compatible embedding client."""
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.EMBEDDING_API_BASE,
        api_key=settings.EMBEDDING_API_KEY,
        timeout=ai_timeout_seconds(
            settings,
            "EMBEDDING_TIMEOUT_SECONDS",
            DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
        ),
        max_retries=ai_client_max_retries(settings),
    )
