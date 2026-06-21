"""Abstract base for data-source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, BinaryIO


class DataConnectorWriteTooLargeError(ValueError):
    """Raised when an adapter write exceeds the caller's byte limit."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"Write exceeds maximum size of {max_bytes} bytes")


@dataclass(frozen=True, slots=True)
class ContentEntry:
    """Lightweight stat-like result for a single file or directory."""

    name: str
    relative_path: str
    is_dir: bool
    is_file: bool
    is_symlink: bool
    size_bytes: int
    modified_time: float  # epoch seconds
    change_time: float  # epoch seconds (= modified_time for S3)


class DataConnectorAdapter(ABC):
    """Abstract file operations for a data source.

    Every concrete adapter (local filesystem, S3, …) implements these
    methods so the rest of the application never touches storage
    primitives directly.
    """

    @abstractmethod
    async def list_directory(self, rel_path: str) -> list[ContentEntry]:
        """List immediate children of a directory/prefix.

        Hidden entries (name starts with ``"."``) are excluded.
        """

    @abstractmethod
    async def stat(self, rel_path: str) -> ContentEntry:
        """Return metadata for a single path.

        Raises ``FileNotFoundError`` when the path does not exist.
        """

    @abstractmethod
    async def exists(self, rel_path: str) -> bool:
        """Check whether *rel_path* exists."""

    @abstractmethod
    async def is_dir(self, rel_path: str) -> bool:
        """Return ``True`` when *rel_path* is a directory (or prefix)."""

    @abstractmethod
    async def is_file(self, rel_path: str) -> bool:
        """Return ``True`` when *rel_path* is a regular file (or object)."""

    @abstractmethod
    async def read_file(self, rel_path: str) -> AsyncIterator[bytes]:
        """Yield file contents as byte chunks.

        Raises ``FileNotFoundError`` when the path does not exist.
        """

    @abstractmethod
    async def write_file(
        self, rel_path: str, data: BinaryIO, *, max_bytes: int | None = None
    ) -> int:
        """Write (or overwrite) a file.  Returns bytes written.

        Implementations must raise ``DataConnectorWriteTooLargeError`` before
        writing bytes beyond ``max_bytes`` when a limit is supplied.
        """

    @abstractmethod
    async def create_directory(self, rel_path: str) -> None:
        """Create a directory (or prefix marker for object stores)."""

    @abstractmethod
    async def delete(self, rel_path: str) -> None:
        """Delete a file or empty directory."""

    @abstractmethod
    async def get_local_path(self, rel_path: str) -> Path | None:
        """Return a local filesystem ``Path`` when available.

        This enables zero-copy ``FileResponse`` for local sources.
        Object-store adapters return ``None``; callers must then fall
        back to :meth:`read_file` with ``StreamingResponse``.
        """
