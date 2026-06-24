"""File watcher service — monitors watchable connectors for changes and dispatches tasks."""

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select, text

from config import BaseDataConnector, LocalFsDataConnector
from database import AsyncSessionLocal
from models.sqlalchemy_models import DataSourceScanStatus
from rls import internal_context, rls_session
from services.connector import ConnectorRuntimeService
from services.watcher_runtime.local import _watch_folder, _watch_folder_smb
from services.watcher_runtime.remote import _watch_s3_poll
from services.watcher_runtime.scan import (
    _scan_existing,
    mark_scan_failed,
    scan_signature_key,
)

logger = logging.getLogger(__name__)


async def _watch_folder_dispatch(folder: BaseDataConnector) -> None:
    if not isinstance(folder, LocalFsDataConnector):
        await _watch_s3_poll(folder)
    elif folder.watcher_type == "smb_notify":
        await _watch_folder_smb(folder)
    else:
        await _watch_folder(folder)


class WatcherService:
    """Manages async file watchers."""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._scan_tasks: dict[str, asyncio.Task] = {}
        self._watch_signatures: dict[str, tuple] = {}
        self._scan_signatures: dict[str, tuple] = {}
        self._started = False
        self._lifecycle_lock = asyncio.Lock()

    @staticmethod
    async def _wait_for_db(max_attempts: int = 10, delay_seconds: int = 2) -> None:
        for _ in range(max_attempts):
            try:
                async with rls_session(
                    AsyncSessionLocal, internal_context("watcher")
                ) as db:
                    await db.execute(text("SELECT 1"))
                return
            except Exception:
                logger.info("Waiting for DB...")
                await asyncio.sleep(delay_seconds)

    @staticmethod
    async def _refresh_runtime_connectors() -> list[BaseDataConnector]:
        async with rls_session(AsyncSessionLocal, internal_context("watcher")) as db:
            runtime = ConnectorRuntimeService(db)
            await runtime.refresh()
            return runtime.browsable_connectors()

    @staticmethod
    def _partition_connectors(
        all_connectors: list[BaseDataConnector],
    ) -> tuple[list[BaseDataConnector], list[BaseDataConnector]]:
        watched = [
            folder for folder in all_connectors if getattr(folder, "watch", False)
        ]
        scannable = [
            folder
            for folder in all_connectors
            if getattr(folder, "initial_scan", False)
        ]
        return watched, scannable

    @staticmethod
    def _watch_signature(folder: BaseDataConnector) -> tuple:
        """Stable watcher config signature for restart detection."""
        if isinstance(folder, LocalFsDataConnector):
            return (
                str(Path(folder.path).resolve()),
                bool(folder.force_polling),
                int(folder.poll_interval_seconds),
                str(folder.watcher_type),
                folder.smb_server or "",
                folder.smb_share or "",
                int(folder.smb_port),
            )
        return (
            folder.connector_type,
            folder.uuid,
            int(folder.poll_interval_seconds),
        )

    @staticmethod
    def _task_is_current(
        task: asyncio.Task | None,
        current_signature: tuple | None,
        new_signature: tuple,
    ) -> bool:
        return (
            task is not None and not task.done() and current_signature == new_signature
        )

    @staticmethod
    def _scan_signature(folder: BaseDataConnector) -> tuple:
        """Stable initial-scan signature for restart detection."""
        return WatcherService._watch_signature(folder)

    async def _cancel_watcher_task(
        self, connector_uuid: str, task: asyncio.Task
    ) -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._tasks.pop(connector_uuid, None)
        self._watch_signatures.pop(connector_uuid, None)

    async def _cancel_scan_task(
        self,
        connector_uuid: str,
        task: asyncio.Task,
        *,
        drop_signature: bool,
    ) -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._scan_tasks.pop(connector_uuid, None)
        if drop_signature:
            self._scan_signatures.pop(connector_uuid, None)

    def _release_scan_task(self, connector_uuid: str, task: asyncio.Task) -> None:
        current = self._scan_tasks.get(connector_uuid)
        if current is task:
            self._scan_tasks.pop(connector_uuid, None)

    async def _run_initial_scan(
        self,
        connector_uuid: str,
        folder: BaseDataConnector,
    ) -> None:
        try:
            await _scan_existing(folder)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._scan_signatures.pop(connector_uuid, None)
            logger.exception("Initial scan crashed for connector %s", connector_uuid)
            try:
                await mark_scan_failed(folder.uuid)
            except Exception:
                logger.warning(
                    "Failed to record scan failure for connector %s",
                    connector_uuid,
                    exc_info=True,
                )

    def _start_scan_task(
        self,
        connector_uuid: str,
        folder: BaseDataConnector,
        signature: tuple,
    ) -> None:
        task = asyncio.create_task(self._run_initial_scan(connector_uuid, folder))
        self._scan_tasks[connector_uuid] = task
        self._scan_signatures[connector_uuid] = signature
        task.add_done_callback(
            lambda done_task: self._release_scan_task(connector_uuid, done_task)
        )
        logger.info("Initial scan scheduled for connector %s", folder.name)

    async def _start_watcher_task(
        self,
        connector_uuid: str,
        folder: BaseDataConnector,
        signature: tuple,
        existing_signature: tuple | None,
        needs_initial_scan: set[str],
    ) -> None:
        self._tasks[connector_uuid] = asyncio.create_task(
            _watch_folder_dispatch(folder)
        )
        self._watch_signatures[connector_uuid] = signature
        if existing_signature is None or existing_signature[0] != signature[0]:
            needs_initial_scan.add(connector_uuid)
        logger.info(
            "Watcher configured for connector %s (type=%s, poll_interval=%ss)",
            folder.name,
            folder.connector_type,
            folder.poll_interval_seconds,
        )

    async def _sync_watch_tasks(self, watched: list[BaseDataConnector]) -> set[str]:
        """Sync watcher tasks to current connector configs and return scan candidates."""
        watched_by_uuid = {folder.uuid: folder for folder in watched}
        needs_initial_scan: set[str] = set()

        for connector_uuid, task in list(self._tasks.items()):
            if connector_uuid not in watched_by_uuid or task.done():
                await self._cancel_watcher_task(connector_uuid, task)

        for connector_uuid, folder in watched_by_uuid.items():
            signature = self._watch_signature(folder)
            existing_task = self._tasks.get(connector_uuid)
            existing_signature = self._watch_signatures.get(connector_uuid)

            if self._task_is_current(existing_task, existing_signature, signature):
                continue

            if existing_task is not None and not existing_task.done():
                await self._cancel_watcher_task(connector_uuid, existing_task)

            await self._start_watcher_task(
                connector_uuid,
                folder,
                signature,
                existing_signature,
                needs_initial_scan,
            )
        return needs_initial_scan

    @staticmethod
    async def _load_completed_scan_signatures(
        uuids: list[str],
    ) -> dict[str, str]:
        """Return persisted signatures of connectors whose last scan completed."""
        if not uuids:
            return {}
        async with rls_session(AsyncSessionLocal, internal_context("watcher")) as db:
            result = await db.execute(
                select(
                    DataSourceScanStatus.connector_uuid,
                    DataSourceScanStatus.signature,
                ).where(
                    DataSourceScanStatus.connector_uuid.in_(uuids),
                    DataSourceScanStatus.state == "done",
                    DataSourceScanStatus.signature.isnot(None),
                )
            )
            return {uuid: signature for uuid, signature in result.all()}

    async def _hydrate_scan_signatures(
        self,
        scannable_by_uuid: dict[str, BaseDataConnector],
    ) -> None:
        """Seed in-memory scan signatures from completed scans (survives restart).

        Without this, ``self._scan_signatures`` starts empty on every process start
        and every connector with ``initial_scan=true`` would be re-scanned. We only
        seed when the persisted signature still matches the connector's current
        config, so a real config change still triggers a fresh scan.
        """
        missing = [
            uuid for uuid in scannable_by_uuid if uuid not in self._scan_signatures
        ]
        persisted = await self._load_completed_scan_signatures(missing)
        for connector_uuid, stored_signature in persisted.items():
            folder = scannable_by_uuid[connector_uuid]
            if stored_signature == scan_signature_key(folder):
                self._scan_signatures[connector_uuid] = self._scan_signature(folder)

    async def _sync_initial_scan_tasks(
        self,
        scannable: list[BaseDataConnector],
    ) -> None:
        """Sync background initial scans to current connector configs."""
        scannable_by_uuid = {folder.uuid: folder for folder in scannable}

        for connector_uuid, task in list(self._scan_tasks.items()):
            if connector_uuid not in scannable_by_uuid:
                await self._cancel_scan_task(
                    connector_uuid,
                    task,
                    drop_signature=True,
                )

        for connector_uuid in list(self._scan_signatures):
            if connector_uuid not in scannable_by_uuid:
                self._scan_signatures.pop(connector_uuid, None)

        await self._hydrate_scan_signatures(scannable_by_uuid)

        for connector_uuid, folder in scannable_by_uuid.items():
            signature = self._scan_signature(folder)
            existing_task = self._scan_tasks.get(connector_uuid)
            existing_signature = self._scan_signatures.get(connector_uuid)

            if self._task_is_current(existing_task, existing_signature, signature):
                continue

            if existing_task is not None and not existing_task.done():
                await self._cancel_scan_task(
                    connector_uuid,
                    existing_task,
                    drop_signature=False,
                )

            if existing_signature == signature:
                continue

            self._start_scan_task(connector_uuid, folder, signature)

    def is_ready(self) -> bool:
        """Return whether watcher runtime configuration completed successfully."""
        return self._started

    async def start(self):
        async with self._lifecycle_lock:
            if self._started:
                await self._reload_config_unlocked()
                return

            await self._wait_for_db()
            all_connectors = await self._refresh_runtime_connectors()
            watched, scannable = self._partition_connectors(all_connectors)
            logger.info(
                "Starting watcher service: %d connector(s) total, %d initial_scan, %d watched",
                len(all_connectors),
                len(scannable),
                len(watched),
            )
            await self._sync_watch_tasks(watched)
            await self._sync_initial_scan_tasks(scannable)
            self._started = True

    async def _reload_config_unlocked(self) -> None:
        """Reload connector config and apply watcher changes; requires lifecycle lock."""
        if not self._started:
            return

        all_folders = await self._refresh_runtime_connectors()
        watched, scannable = self._partition_connectors(all_folders)
        await self._sync_watch_tasks(watched)
        await self._sync_initial_scan_tasks(scannable)
        logger.info(
            "Reloaded watcher configuration: %d watched connector(s), %d scannable connector(s)",
            len(watched),
            len(scannable),
        )

    async def reload_config(self) -> None:
        """Reload connector config and apply watcher changes without full restart."""
        async with self._lifecycle_lock:
            await self._reload_config_unlocked()

    async def stop_connector(self, connector_uuid: str) -> None:
        """Stop watcher task for a single connector UUID, if running."""
        async with self._lifecycle_lock:
            task = self._tasks.get(connector_uuid)
            if task is not None and not task.done():
                await self._cancel_watcher_task(connector_uuid, task)
                logger.info("Stopped watcher for connector %s", connector_uuid)
            else:
                self._tasks.pop(connector_uuid, None)
                self._watch_signatures.pop(connector_uuid, None)
            scan_task = self._scan_tasks.get(connector_uuid)
            if scan_task is not None and not scan_task.done():
                await self._cancel_scan_task(
                    connector_uuid,
                    scan_task,
                    drop_signature=True,
                )
            else:
                self._scan_tasks.pop(connector_uuid, None)
                self._scan_signatures.pop(connector_uuid, None)

    async def stop(self):
        async with self._lifecycle_lock:
            for task in self._tasks.values():
                task.cancel()
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            for task in self._scan_tasks.values():
                task.cancel()
            await asyncio.gather(*self._scan_tasks.values(), return_exceptions=True)
            self._tasks.clear()
            self._scan_tasks.clear()
            self._watch_signatures.clear()
            self._scan_signatures.clear()
            self._started = False
            logger.info("Watcher service stopped")
