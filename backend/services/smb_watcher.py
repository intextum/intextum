"""SMB CHANGE_NOTIFY watcher — detects file changes via the SMB protocol."""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Any

from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.open import (
    Open,
    CreateDisposition,
    CreateOptions,
    DirectoryAccessMask,
    FileAttributes,
    ImpersonationLevel,
    ShareAccess,
)
from smbprotocol.change_notify import (
    ChangeNotifyFlags,
    CompletionFilter,
    FileSystemWatcher,
    NotifyEnumDir,
)
from watchfiles import Change

from config import LocalFsDataConnector

logger = logging.getLogger(__name__)

_SMB_ACTION_MAP: dict[int, Change] = {
    1: Change.added,
    2: Change.deleted,
    3: Change.modified,
    4: Change.deleted,
    5: Change.added,
}

_COMPLETION_FILTER = (
    CompletionFilter.FILE_NOTIFY_CHANGE_FILE_NAME
    | CompletionFilter.FILE_NOTIFY_CHANGE_DIR_NAME
    | CompletionFilter.FILE_NOTIFY_CHANGE_SIZE
    | CompletionFilter.FILE_NOTIFY_CHANGE_LAST_WRITE
)


class SmbNotifyWatcher:
    """Watch for file changes via SMB2 CHANGE_NOTIFY requests."""

    def __init__(self, folder: LocalFsDataConnector):
        self._folder = folder
        self._connection: Connection | None = None
        self._session: Session | None = None
        self._tree: TreeConnect | None = None
        self._dir_handle: Open | None = None

    def _username(self) -> str:
        username = self._folder.smb_username or ""
        if self._folder.smb_domain and username and "\\" not in username:
            return f"{self._folder.smb_domain}\\{username}"
        return username

    def _entry_change(self, entry: Any) -> tuple[Change, str] | None:
        action = entry["action"].get_value()
        file_name = entry["file_name"].get_value()
        change_type = _SMB_ACTION_MAP.get(action)
        if change_type is None:
            logger.debug("Unknown SMB action %d for %s", action, file_name)
            return None
        return change_type, self._smb_path_to_local(file_name)

    def _connect(self) -> None:
        """Establish SMB connection, session, tree connect, and open root dir."""
        server = self._folder.smb_server
        port = self._folder.smb_port
        share = self._folder.smb_share
        self._connection = Connection(guid=None, server_name=server, port=port)
        self._connection.connect()

        self._session = Session(
            connection=self._connection,
            username=self._username(),
            password=self._folder.smb_password or "",
            require_encryption=False,
        )
        self._session.connect()

        tree_path = f"\\\\{server}\\{share}"
        self._tree = TreeConnect(self._session, tree_path)
        self._tree.connect()

        self._dir_handle = Open(self._tree, "")
        self._dir_handle.create(
            impersonation_level=ImpersonationLevel.Impersonation,
            desired_access=DirectoryAccessMask.FILE_LIST_DIRECTORY,
            file_attributes=FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
            share_access=ShareAccess.FILE_SHARE_READ
            | ShareAccess.FILE_SHARE_WRITE
            | ShareAccess.FILE_SHARE_DELETE,
            create_disposition=CreateDisposition.FILE_OPEN,
            create_options=CreateOptions.FILE_DIRECTORY_FILE,
        )

        logger.info(
            "SMB CHANGE_NOTIFY connected: %s -> \\\\%s\\%s",
            self._folder.name,
            server,
            share,
        )

    def _disconnect(self) -> None:
        """Tear down SMB resources."""
        for resource in (self._dir_handle, self._tree, self._session, self._connection):
            self._close_resource(resource)
        self._dir_handle = None
        self._tree = None
        self._session = None
        self._connection = None

    @staticmethod
    def _close_resource(resource: object | None) -> None:
        if resource is None:
            return
        try:
            close = getattr(resource, "close", None)
            if callable(close):
                close()
                return

            disconnect = getattr(resource, "disconnect", None)
            if callable(disconnect):
                disconnect()
        except Exception:
            logger.debug(
                "Failed to close SMB watcher resource %s",
                type(resource).__name__,
                exc_info=True,
            )

    def _smb_path_to_local(self, smb_relative: str) -> str:
        """Convert an SMB-relative path (backslashes) to a local absolute path."""
        posix_rel = smb_relative.replace("\\", "/")
        return str(PurePosixPath(self._folder.path) / posix_rel)

    def _poll_changes(self) -> list[tuple[Change, str]] | None:
        """Blocking call: send CHANGE_NOTIFY and wait for response.

        Returns a list of (Change, local_path) tuples, or None on buffer
        overflow (STATUS_NOTIFY_ENUM_DIR) which signals a full reconcile.
        """
        assert self._dir_handle is not None

        fs_watcher = FileSystemWatcher(self._dir_handle)

        try:
            fs_watcher.start(
                completion_filter=_COMPLETION_FILTER,
                flags=ChangeNotifyFlags.SMB2_WATCH_TREE,
            )
            response = fs_watcher.wait()
        except NotifyEnumDir:
            logger.warning(
                "SMB CHANGE_NOTIFY buffer overflow for %s — full reconcile needed",
                self._folder.name,
            )
            return None

        changes: list[tuple[Change, str]] = []
        for entry in response:
            mapped = self._entry_change(entry)
            if mapped:
                changes.append(mapped)

        return changes

    async def watch(self) -> AsyncIterator[list[tuple[Change, str]]]:
        """Async generator yielding batches of file changes.

        Yields an empty list on buffer overflow to signal that the caller
        should perform a full reconcile scan.
        """
        poll_interval = max(1, int(self._folder.poll_interval_seconds))

        while True:
            try:
                self._connect()

                while True:
                    result = await asyncio.to_thread(self._poll_changes)
                    if result is None:
                        yield []
                    elif result:
                        yield result

            except asyncio.CancelledError:
                self._disconnect()
                raise
            except Exception:
                logger.exception(
                    "SMB CHANGE_NOTIFY error for %s, reconnecting in %ds",
                    self._folder.name,
                    poll_interval,
                )
                self._disconnect()
                await asyncio.sleep(poll_interval)
