"""Content item kind, path, and relationship invariants."""

from __future__ import annotations

from dataclasses import dataclass

from models.content.items import ContentItemKind
from services.content.location import normalize_content_path

VALID_CONTENT_ITEM_KINDS = frozenset(item.value for item in ContentItemKind)


def normalize_content_item_kind(kind: ContentItemKind | str | None) -> str:
    """Return a supported content item kind value or raise a domain error."""
    value = kind.value if isinstance(kind, ContentItemKind) else kind
    if isinstance(value, str) and value in VALID_CONTENT_ITEM_KINDS:
        return value
    raise ValueError(f"Unsupported content item kind: {value!r}")


def safe_content_item_kind(kind: ContentItemKind | str | None) -> ContentItemKind:
    """Resolve API-facing content kind values, defaulting malformed rows to file."""
    try:
        return ContentItemKind(normalize_content_item_kind(kind))
    except ValueError:
        return ContentItemKind.FILE


def normalize_content_relative_path(
    relative_path: str,
    *,
    allow_empty: bool = False,
) -> str:
    """Normalize and validate one connector-relative content path."""
    if not isinstance(relative_path, str):
        raise ValueError("relative_path must be a string")

    raw_path = relative_path.strip().replace("\\", "/")
    if raw_path.startswith("/"):
        raise ValueError("relative_path must not be absolute")

    normalized_path = normalize_content_path(raw_path)
    if not normalized_path and not allow_empty:
        raise ValueError("relative_path is required")

    path_parts = normalized_path.split("/") if normalized_path else []
    if any(part in {"", ".", ".."} for part in path_parts):
        raise ValueError("relative_path must not contain empty or traversal segments")

    return normalized_path


def validate_non_negative_size(size_bytes: int) -> int:
    """Validate size fields before persisting content item rows."""
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    return size_bytes


@dataclass(frozen=True)
class ContentItemInvariantInput:
    """Minimal fields needed to validate one persisted content item shape."""

    content_kind: ContentItemKind | str | None
    relative_path: str
    size_bytes: int
    is_dir: bool
    is_container: bool
    has_email_details: bool = False
    has_attachment_details: bool = False
    parent_content_item_id: str | None = None
    container_content_item_id: str | None = None
    email_message_content_item_id: str | None = None


def validate_content_item_invariants(
    values: ContentItemInvariantInput,
    *,
    allow_empty_path: bool = False,
) -> str:
    """Validate kind-specific content item invariants and return normalized kind."""
    content_kind = normalize_content_item_kind(values.content_kind)
    normalize_content_relative_path(
        values.relative_path,
        allow_empty=allow_empty_path,
    )
    validate_non_negative_size(values.size_bytes)

    if content_kind == ContentItemKind.FOLDER.value:
        if not values.is_dir or not values.is_container:
            raise ValueError("folder content items must be directories and containers")
        return content_kind

    if values.is_dir:
        raise ValueError("non-folder content items must not be directories")

    if content_kind == ContentItemKind.EMAIL_MESSAGE.value:
        if not values.has_email_details:
            raise ValueError("email_message content items require email details")
        return content_kind

    if content_kind == ContentItemKind.ATTACHMENT.value:
        if not values.has_attachment_details:
            raise ValueError("attachment content items require attachment details")
        if not (
            values.parent_content_item_id
            and values.container_content_item_id
            and values.email_message_content_item_id
        ):
            raise ValueError("attachment content items require email parent linkage")
        return content_kind

    return content_kind
