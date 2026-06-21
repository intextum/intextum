"""Tests for shared upstream AI timeout and backpressure helpers."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.ai_limits import create_embedding_response


class _EmbeddingClient:
    def __init__(self, create):
        self.embeddings = SimpleNamespace(create=create)


@pytest.mark.asyncio
async def test_create_embedding_response_times_out_slow_provider():
    async def _slow_create(*, model, input):
        await asyncio.sleep(1)

    settings = SimpleNamespace(
        EMBEDDING_TIMEOUT_SECONDS=0.01,
        EMBEDDING_MAX_CONCURRENT_REQUESTS=1,
        AI_BACKPRESSURE_WAIT_SECONDS=0.05,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_embedding_response(
            _EmbeddingClient(_slow_create),
            settings,
            model="embed-model",
            texts=["hello"],
        )

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == "Embedding request timed out"


@pytest.mark.asyncio
async def test_create_embedding_response_returns_503_when_slots_are_saturated():
    started = asyncio.Event()
    release = asyncio.Event()

    async def _held_create(*, model, input):
        started.set()
        await release.wait()
        return SimpleNamespace(data=[])

    async def _second_create(*, model, input):
        return SimpleNamespace(data=[])

    settings = SimpleNamespace(
        EMBEDDING_TIMEOUT_SECONDS=1.0,
        EMBEDDING_MAX_CONCURRENT_REQUESTS=1,
        AI_BACKPRESSURE_WAIT_SECONDS=0.01,
    )

    first = asyncio.create_task(
        create_embedding_response(
            _EmbeddingClient(_held_create),
            settings,
            model="embed-model",
            texts=["one"],
        )
    )
    await started.wait()

    try:
        with pytest.raises(HTTPException) as exc_info:
            await create_embedding_response(
                _EmbeddingClient(_second_create),
                settings,
                model="embed-model",
                texts=["two"],
            )
    finally:
        release.set()
        await first

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Embedding service is busy"
