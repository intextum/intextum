"""Application runtime helpers for startup, shutdown, and background loops."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from logging import Logger

from rls import internal_context, rls_session, rls_session_factory


async def _maybe_await(result) -> None:
    if inspect.isawaitable(result):
        await result


async def start_watcher(watcher) -> None:
    """Start the configured watcher, awaiting async implementations when needed."""
    await _maybe_await(watcher.start())


async def stop_watcher(watcher) -> None:
    """Stop the configured watcher, awaiting async implementations when needed."""
    await _maybe_await(watcher.stop())


async def cancel_background_tasks(*tasks: asyncio.Task | None) -> None:
    """Cancel background tasks and wait for their cancellation to settle."""
    active_tasks = [task for task in tasks if task is not None]
    if not active_tasks:
        return

    for task in active_tasks:
        task.cancel()

    with suppress(asyncio.CancelledError):
        await asyncio.gather(*active_tasks, return_exceptions=True)


@dataclass(frozen=True)
class BackgroundTaskHandles:
    """Background task handles created during application startup."""

    cleanup_task: asyncio.Task
    event_outbox_task: asyncio.Task
    chat_runner_task: asyncio.Task | None

    def tasks(self) -> tuple[asyncio.Task | None, ...]:
        return self.cleanup_task, self.event_outbox_task, self.chat_runner_task


def start_background_tasks(
    *,
    session_factory,
    logger: Logger,
    settings,
    runner_id: str,
    stale_cleanup_interval_seconds: int,
    task_queue_service_factory: Callable,
    process_next_chat_run: Callable,
    valkey_configured: bool,
) -> BackgroundTaskHandles:
    """Start background maintenance loops and return their task handles."""
    cleanup_task = asyncio.create_task(
        stale_claim_cleanup_loop(
            session_factory=session_factory,
            logger=logger,
            interval_seconds=stale_cleanup_interval_seconds,
            task_queue_service_factory=task_queue_service_factory,
        )
    )
    event_outbox_task = asyncio.create_task(
        event_outbox_dispatch_loop(
            session_factory=session_factory,
            logger=logger,
            poll_interval_seconds=settings.EVENT_OUTBOX_POLL_INTERVAL_SECONDS,
        )
    )
    chat_runner_task = None
    if settings.CHAT_RUNNER_ENABLED:
        if valkey_configured:
            chat_runner_task = asyncio.create_task(
                chat_run_loop(
                    session_factory=session_factory,
                    logger=logger,
                    runner_id=runner_id,
                    poll_interval_seconds=settings.CHAT_RUN_POLL_INTERVAL_SECONDS,
                    process_next_chat_run=process_next_chat_run,
                )
            )
        else:
            logger.warning(
                "CHAT_RUNNER_ENABLED is true but VALKEY_URL is empty; "
                "resumable chat runs will stay disabled."
            )
    return BackgroundTaskHandles(
        cleanup_task=cleanup_task,
        event_outbox_task=event_outbox_task,
        chat_runner_task=chat_runner_task,
    )


async def shutdown_runtime(
    *,
    background_tasks: BackgroundTaskHandles,
    watcher,
    close_valkey_client: Callable,
    close_chat_checkpointer: Callable,
) -> None:
    """Stop background runtime resources in the application shutdown order."""
    await cancel_background_tasks(*background_tasks.tasks())
    await stop_watcher(watcher)
    await close_valkey_client()
    await close_chat_checkpointer()


def warn_missing_auth_proxy_secret(settings, logger: Logger) -> None:
    """Log a startup warning when forwarded-auth protection is disabled."""
    if settings.AUTH_PROXY_ENABLED and not settings.AUTH_PROXY_SECRET:
        logger.warning(
            "AUTH_PROXY_SECRET is empty — forwarded auth headers will be rejected. "
            "Set AUTH_PROXY_SECRET to enable authenticated requests."
        )


async def stale_claim_cleanup_loop(
    *,
    session_factory,
    logger: Logger,
    interval_seconds: int,
    task_queue_service_factory: Callable,
) -> None:
    """Background loop that re-queues stale claimed tasks."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with rls_session(
                session_factory, internal_context("stale_cleanup")
            ) as db:
                svc = task_queue_service_factory(db)
                count = await svc.cleanup_stale_claims()
                if count:
                    logger.info("Stale cleanup: re-queued %d tasks", count)
        except Exception as exc:
            logger.error("Stale cleanup error: %s", exc)


async def chat_run_loop(
    *,
    session_factory,
    logger: Logger,
    runner_id: str,
    poll_interval_seconds: float,
    process_next_chat_run: Callable,
) -> None:
    """Background loop that executes pending resumable chat runs."""
    while True:
        try:
            processed = await process_next_chat_run(
                session_factory=rls_session_factory(
                    session_factory, internal_context("chat_runner")
                ),
                runner_id=runner_id,
            )
            if not processed:
                await asyncio.sleep(poll_interval_seconds)
        except Exception as exc:
            logger.error("Chat runner error: %s", exc)
            await asyncio.sleep(poll_interval_seconds)


async def event_outbox_dispatch_loop(
    *,
    session_factory,
    logger: Logger,
    poll_interval_seconds: float,
) -> None:
    """Background loop that dispatches durable outbox side effects."""
    from services.event_outbox import EventOutboxService

    while True:
        try:
            async with rls_session(
                session_factory, internal_context("event_outbox")
            ) as db:
                processed = await EventOutboxService(db).dispatch_pending()
                if not processed:
                    await asyncio.sleep(poll_interval_seconds)
        except Exception as exc:
            logger.error("Event outbox dispatch error: %s", exc)
            await asyncio.sleep(poll_interval_seconds)
