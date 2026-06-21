"""Tests for shared external-service client configuration."""

from types import SimpleNamespace
from unittest.mock import patch

from clients import get_async_embedding_client, get_embedding_client


def test_embedding_clients_apply_timeout_and_retry_settings():
    settings = SimpleNamespace(
        EMBEDDING_API_BASE="http://embedding.example/v1",
        EMBEDDING_API_KEY="embedding-key",
        EMBEDDING_TIMEOUT_SECONDS=12.5,
        AI_CLIENT_MAX_RETRIES=0,
    )

    get_embedding_client.cache_clear()
    get_async_embedding_client.cache_clear()
    try:
        with (
            patch("clients.get_settings", return_value=settings),
            patch("clients.OpenAI") as sync_client_cls,
            patch("clients.AsyncOpenAI") as async_client_cls,
        ):
            get_embedding_client()
            get_async_embedding_client()
    finally:
        get_embedding_client.cache_clear()
        get_async_embedding_client.cache_clear()

    expected_kwargs = {
        "base_url": "http://embedding.example/v1",
        "api_key": "embedding-key",
        "timeout": 12.5,
        "max_retries": 0,
    }
    sync_client_cls.assert_called_once_with(**expected_kwargs)
    async_client_cls.assert_called_once_with(**expected_kwargs)
