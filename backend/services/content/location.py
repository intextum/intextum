"""Content location helpers for connector-backed indexed content."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

from config import BaseDataConnector


def normalize_content_path(relative_path: str) -> str:
    """Normalize connector-relative paths before ID/path calculations."""
    return unicodedata.normalize("NFC", relative_path.strip("/"))


def compute_connector_content_item_id(connector_uuid: str, relative_path: str) -> str:
    """Compute a deterministic content item identity for one connector path."""
    normalized_path = normalize_content_path(relative_path)
    return hashlib.sha256(f"{connector_uuid}:{normalized_path}".encode()).hexdigest()[
        :16
    ]


@dataclass(frozen=True)
class ContentLocation:
    """A connector-relative content location with its stable content ID."""

    connector_uuid: str
    relative_path: str
    content_item_id: str

    @classmethod
    def from_parts(cls, connector_uuid: str, relative_path: str) -> "ContentLocation":
        normalized_path = normalize_content_path(relative_path)
        return cls(
            connector_uuid=connector_uuid,
            relative_path=normalized_path,
            content_item_id=compute_connector_content_item_id(
                connector_uuid, normalized_path
            ),
        )


def render_api_path(connector: BaseDataConnector, relative_path: str) -> str:
    """Render the user-facing connector-name-prefixed API path."""
    normalized_path = normalize_content_path(relative_path)
    return f"{connector.name}/{normalized_path}" if normalized_path else connector.name


def split_api_path(api_path: str) -> tuple[str, str]:
    """Split a connector-name-prefixed API path into name and relative path."""
    stripped = api_path.strip("/")
    if not stripped:
        raise FileNotFoundError("Cannot resolve empty path to a specific connector")
    connector_name, _, relative_path = stripped.partition("/")
    return connector_name, normalize_content_path(relative_path)
