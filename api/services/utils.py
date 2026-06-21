"""Shared utility functions for content item operations."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from config import BaseDataConnector
from services.connector import ConnectorRuntimeService
from services.content.location import compute_connector_content_item_id

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime (for DB storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_content_item_id(folder_uuid: str, relative_path: str) -> str:
    """Compute a deterministic content item identity from folder UUID and relative path.

    The path is Unicode NFC-normalized before hashing so that composed and
    decomposed forms (e.g. macOS NFD vs NFC from browsers) produce the same ID.
    """
    return compute_connector_content_item_id(folder_uuid, relative_path)


def get_content_item_metadata(path: Path) -> dict:
    """Extract filesystem metadata from one content item path."""
    try:
        stat = path.stat()
        return {
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
            "created_time": stat.st_ctime,
            "permissions": oct(stat.st_mode)[-3:],
            "owner_id": stat.st_uid,
            "group_id": stat.st_gid,
            "inode": stat.st_ino,
            "access_time": stat.st_atime,
            "is_symlink": path.is_symlink(),
            "file_extension": path.suffix.lower() if path.suffix else None,
        }
    except OSError as e:
        logger.warning("Could not extract metadata for %s: %s", path, e)
        return {}


def find_folder_by_uuid(source_uuid: str) -> BaseDataConnector | None:
    """Find any data source by its UUID."""
    return ConnectorRuntimeService().get_connector(source_uuid)


def find_folder_by_name(name: str) -> BaseDataConnector | None:
    """Find a browsable data source by its user-facing name."""
    return ConnectorRuntimeService().get_browsable_connector_by_name(name)


def is_hidden(path: Path) -> bool:
    """Check if a file or folder is hidden (starts with a dot)."""
    return path.name.startswith(".")
