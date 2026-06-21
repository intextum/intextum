"""Local-filesystem adapter for data sources."""

from __future__ import annotations

import asyncio
import logging
import os
import unicodedata
import uuid
from pathlib import Path
from typing import AsyncIterator, BinaryIO, TYPE_CHECKING

from .base import ContentEntry, DataConnectorAdapter, DataConnectorWriteTooLargeError

if TYPE_CHECKING:
    from models.connector_types import LocalFsDataConnector

logger = logging.getLogger(__name__)

_READ_CHUNK_SIZE = 256 * 1024  # 256 KiB


def _normalize_rel_path(rel_path: str) -> str:
    return unicodedata.normalize("NFC", rel_path.strip("/"))


class LocalFsAdapter(DataConnectorAdapter):
    """Adapter that maps file operations to the local filesystem."""

    def __init__(self, source: LocalFsDataConnector) -> None:
        self._root = Path(source.path).resolve()

    def _resolve(self, rel_path: str) -> Path:
        """Resolve *rel_path* against the source root with traversal guard."""
        cleaned = _normalize_rel_path(rel_path)
        full = (self._root / cleaned).resolve() if cleaned else self._root
        if cleaned and not full.exists():
            full = self._resolve_normalized_existing_path(cleaned)
        try:
            full.relative_to(self._root)
        except ValueError:
            raise FileNotFoundError("Path traversal detected")
        return full

    def _resolve_normalized_existing_path(self, cleaned_rel_path: str) -> Path:
        """Resolve NFC paths against filesystems that expose decomposed names."""
        current = self._root
        parts = [part for part in Path(cleaned_rel_path).parts if part not in ("", ".")]
        for index, part in enumerate(parts):
            if part in ("", "."):
                continue
            if part == "..":
                raise FileNotFoundError("Path traversal detected")
            candidate = current / part
            if candidate.exists():
                current = candidate
                continue
            try:
                children = list(current.iterdir())
            except OSError:
                return (current / Path(*parts[index:])).resolve()
            normalized_part = _normalize_rel_path(part)
            match = next(
                (
                    child
                    for child in children
                    if _normalize_rel_path(child.name) == normalized_part
                ),
                None,
            )
            if match is None:
                return (current / Path(*parts[index:])).resolve()
            current = match
        return current.resolve()

    @staticmethod
    def _entry_from_dir_entry(dir_entry: os.DirEntry, rel_path: str) -> ContentEntry:
        """Build a ``ContentEntry`` from an ``os.DirEntry``."""
        try:
            st = dir_entry.stat(follow_symlinks=True)
        except OSError:
            st = dir_entry.stat(follow_symlinks=False)
        normalized_rel_path = _normalize_rel_path(rel_path)
        return ContentEntry(
            name=_normalize_rel_path(dir_entry.name),
            relative_path=normalized_rel_path,
            is_dir=dir_entry.is_dir(follow_symlinks=False),
            is_file=dir_entry.is_file(follow_symlinks=True),
            is_symlink=dir_entry.is_symlink(),
            size_bytes=st.st_size,
            modified_time=st.st_mtime,
            change_time=st.st_ctime,
        )

    @staticmethod
    def _entry_from_path(path: Path, rel_path: str) -> ContentEntry:
        """Build a ``ContentEntry`` from a ``Path``."""
        st = path.stat()
        normalized_rel_path = _normalize_rel_path(rel_path)
        return ContentEntry(
            name=_normalize_rel_path(path.name),
            relative_path=normalized_rel_path,
            is_dir=path.is_dir(),
            is_file=path.is_file(),
            is_symlink=path.is_symlink(),
            size_bytes=st.st_size,
            modified_time=st.st_mtime,
            change_time=st.st_ctime,
        )

    async def list_directory(self, rel_path: str) -> list[ContentEntry]:
        dir_path = self._resolve(rel_path)
        parent_rel = _normalize_rel_path(rel_path)

        def _scan() -> list[ContentEntry]:
            entries: list[ContentEntry] = []
            try:
                with os.scandir(dir_path) as it:
                    for de in it:
                        if de.name.startswith("."):
                            continue
                        child_rel = f"{parent_rel}/{de.name}" if parent_rel else de.name
                        try:
                            entries.append(self._entry_from_dir_entry(de, child_rel))
                        except OSError:
                            logger.debug(
                                "Skipping unreadable local filesystem entry %s",
                                child_rel,
                                exc_info=True,
                            )
                            continue
            except (OSError, PermissionError):
                logger.debug(
                    "Unable to scan local filesystem directory %s",
                    dir_path,
                    exc_info=True,
                )
            return entries

        return await asyncio.to_thread(_scan)

    async def stat(self, rel_path: str) -> ContentEntry:
        full = self._resolve(rel_path)
        if not full.exists():
            raise FileNotFoundError(rel_path)
        cleaned = _normalize_rel_path(rel_path)
        return await asyncio.to_thread(self._entry_from_path, full, cleaned)

    async def exists(self, rel_path: str) -> bool:
        return await asyncio.to_thread(self._resolve(rel_path).exists)

    async def is_dir(self, rel_path: str) -> bool:
        return await asyncio.to_thread(self._resolve(rel_path).is_dir)

    async def is_file(self, rel_path: str) -> bool:
        return await asyncio.to_thread(self._resolve(rel_path).is_file)

    async def read_file(self, rel_path: str) -> AsyncIterator[bytes]:
        full = self._resolve(rel_path)
        if not full.is_file():
            raise FileNotFoundError(rel_path)

        async def _stream() -> AsyncIterator[bytes]:
            fh = await asyncio.to_thread(open, full, "rb")
            try:
                while True:
                    chunk = await asyncio.to_thread(fh.read, _READ_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await asyncio.to_thread(fh.close)

        return _stream()

    async def write_file(
        self, rel_path: str, data: BinaryIO, *, max_bytes: int | None = None
    ) -> int:
        cleaned = _normalize_rel_path(rel_path)
        if not cleaned:
            raise IsADirectoryError("Cannot write connector root")

        full = self._resolve(rel_path)
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError) as exc:
            raise NotADirectoryError(
                f"Parent path is blocked by an existing file: {_normalize_rel_path(rel_path)}"
            ) from exc

        def _write() -> int:
            written = 0
            tmp_path = full.parent / f".{full.name}.{uuid.uuid4().hex}.upload"
            try:
                with open(tmp_path, "wb") as fh:
                    while True:
                        chunk = data.read(_READ_CHUNK_SIZE)
                        if not chunk:
                            break
                        next_written = written + len(chunk)
                        if max_bytes is not None and next_written > max_bytes:
                            raise DataConnectorWriteTooLargeError(max_bytes)
                        fh.write(chunk)
                        written = next_written
                tmp_path.replace(full)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
            return written

        return await asyncio.to_thread(_write)

    async def create_directory(self, rel_path: str) -> None:
        full = self._resolve(rel_path)
        await asyncio.to_thread(full.mkdir, parents=True, exist_ok=True)

    async def delete(self, rel_path: str) -> None:
        full = self._resolve(rel_path)
        if not full.exists():
            raise FileNotFoundError(rel_path)

        def _delete() -> None:
            if full.is_dir():
                full.rmdir()
            else:
                full.unlink()

        await asyncio.to_thread(_delete)

    async def get_local_path(self, rel_path: str) -> Path | None:
        full = self._resolve(rel_path)
        if not full.exists():
            return None
        return full
