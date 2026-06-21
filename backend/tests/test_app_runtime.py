"""Tests for application background runtime helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app_runtime import (
    BackgroundTaskHandles,
    cancel_background_tasks,
    chat_run_loop,
    shutdown_runtime,
    start_background_tasks,
)


@pytest.mark.asyncio
async def test_chat_run_loop_sleeps_when_no_run_was_processed():
    process_next_chat_run = AsyncMock(return_value=False)
    logger = MagicMock()
    session_factory = object()

    with patch(
        "app_runtime.asyncio.sleep",
        new=AsyncMock(side_effect=asyncio.CancelledError),
    ) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await chat_run_loop(
                session_factory=session_factory,
                logger=logger,
                runner_id="backend-1",
                poll_interval_seconds=1.5,
                process_next_chat_run=process_next_chat_run,
            )

    process_next_chat_run.assert_awaited_once()
    call_kwargs = process_next_chat_run.await_args.kwargs
    assert call_kwargs["runner_id"] == "backend-1"
    assert callable(call_kwargs["session_factory"])
    assert call_kwargs["session_factory"] is not session_factory
    sleep.assert_awaited_once_with(1.5)
    logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_chat_run_loop_logs_errors_and_continues_after_sleep():
    process_next_chat_run = AsyncMock(side_effect=RuntimeError("boom"))
    logger = MagicMock()

    with patch(
        "app_runtime.asyncio.sleep",
        new=AsyncMock(side_effect=asyncio.CancelledError),
    ) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await chat_run_loop(
                session_factory=object(),
                logger=logger,
                runner_id="backend-1",
                poll_interval_seconds=2.0,
                process_next_chat_run=process_next_chat_run,
            )

    logger.error.assert_called_once()
    sleep.assert_awaited_once_with(2.0)


@pytest.mark.asyncio
async def test_cancel_background_tasks_cancels_and_waits_for_tasks():
    cleanup_started = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def _run_forever():
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await asyncio.sleep(0)
            cleanup_finished.set()

    task = asyncio.create_task(_run_forever())
    await asyncio.sleep(0)

    await cancel_background_tasks(task, None)

    assert task.cancelled()
    assert cleanup_started.is_set()
    assert cleanup_finished.is_set()


@pytest.mark.asyncio
async def test_start_background_tasks_registers_chat_runner_when_valkey_available():
    async def _sleep_forever(*_args, **_kwargs):
        await asyncio.Event().wait()

    settings = SimpleNamespace(
        EVENT_OUTBOX_POLL_INTERVAL_SECONDS=1.0,
        CHAT_RUNNER_ENABLED=True,
        CHAT_RUN_POLL_INTERVAL_SECONDS=2.0,
    )

    with (
        patch("app_runtime.stale_claim_cleanup_loop", new=_sleep_forever),
        patch("app_runtime.event_outbox_dispatch_loop", new=_sleep_forever),
        patch("app_runtime.chat_run_loop", new=_sleep_forever),
    ):
        handles = start_background_tasks(
            session_factory=object(),
            logger=MagicMock(),
            settings=settings,
            runner_id="backend-1",
            stale_cleanup_interval_seconds=300,
            task_queue_service_factory=MagicMock(),
            process_next_chat_run=AsyncMock(),
            valkey_configured=True,
        )

    try:
        assert handles.cleanup_task is not None
        assert handles.event_outbox_task is not None
        assert handles.chat_runner_task is not None
    finally:
        await cancel_background_tasks(*handles.tasks())


@pytest.mark.asyncio
async def test_start_background_tasks_warns_when_chat_runner_has_no_valkey():
    async def _sleep_forever(*_args, **_kwargs):
        await asyncio.Event().wait()

    settings = SimpleNamespace(
        EVENT_OUTBOX_POLL_INTERVAL_SECONDS=1.0,
        CHAT_RUNNER_ENABLED=True,
        CHAT_RUN_POLL_INTERVAL_SECONDS=2.0,
    )
    logger = MagicMock()

    with (
        patch("app_runtime.stale_claim_cleanup_loop", new=_sleep_forever),
        patch("app_runtime.event_outbox_dispatch_loop", new=_sleep_forever),
        patch("app_runtime.chat_run_loop", new=_sleep_forever),
    ):
        handles = start_background_tasks(
            session_factory=object(),
            logger=logger,
            settings=settings,
            runner_id="backend-1",
            stale_cleanup_interval_seconds=300,
            task_queue_service_factory=MagicMock(),
            process_next_chat_run=AsyncMock(),
            valkey_configured=False,
        )

    try:
        assert handles.chat_runner_task is None
        logger.warning.assert_called_once()
    finally:
        await cancel_background_tasks(*handles.tasks())


@pytest.mark.asyncio
async def test_shutdown_runtime_cancels_tasks_and_closes_resources():
    async def _run_forever():
        await asyncio.Event().wait()

    cleanup_task = asyncio.create_task(_run_forever())
    event_outbox_task = asyncio.create_task(_run_forever())
    await asyncio.sleep(0)

    watcher = MagicMock()
    watcher.stop = AsyncMock()
    close_valkey_client = AsyncMock()
    close_chat_checkpointer = AsyncMock()

    await shutdown_runtime(
        background_tasks=BackgroundTaskHandles(
            cleanup_task=cleanup_task,
            event_outbox_task=event_outbox_task,
            chat_runner_task=None,
        ),
        watcher=watcher,
        close_valkey_client=close_valkey_client,
        close_chat_checkpointer=close_chat_checkpointer,
    )

    assert cleanup_task.cancelled()
    assert event_outbox_task.cancelled()
    watcher.stop.assert_awaited_once()
    close_valkey_client.assert_awaited_once()
    close_chat_checkpointer.assert_awaited_once()
