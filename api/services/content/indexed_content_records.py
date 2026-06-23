"""Record builders for indexed content item upserts.

These helpers are pure normalization/value-construction code. The database
write path remains in ``indexed_content_item.py``.
"""

import mimetypes
import os
import secrets
from dataclasses import dataclass, replace
from datetime import datetime

from models.content.items import ContentItemKind
from models.enums import ProcessingStatus
from services.content.invariants import (
    ContentItemInvariantInput,
    normalize_content_relative_path,
    validate_content_item_invariants,
    validate_non_negative_size,
)


TERMINAL_PROCESSING_STATUSES = {
    ProcessingStatus.COMPLETED,
    ProcessingStatus.FAILED,
    ProcessingStatus.REVOKED,
}


@dataclass(frozen=True)
class ContentItemRecordValues:
    folder_uuid: str
    relative_path: str
    content_kind: str
    modified_time: float
    change_time: float
    size_bytes: int
    status: str | None
    parent_path: str
    name: str
    display_name: str
    extension: str | None
    mime_type: str | None
    is_container: bool
    is_hidden: bool
    is_symlink: bool


@dataclass(frozen=True)
class DirectoryRecordValues:
    folder_uuid: str
    relative_path: str
    content_kind: str
    parent_path: str
    name: str
    display_name: str
    mime_type: str | None
    is_container: bool
    is_hidden: bool
    is_symlink: bool


@dataclass(frozen=True)
class EmailMessageRecordValues:
    folder_uuid: str
    relative_path: str
    external_id: str | None
    modified_time: float
    change_time: float
    size_bytes: int
    status: str | None
    parent_path: str
    name: str
    display_name: str
    mime_type: str | None
    is_hidden: bool
    subject: str
    message_id_header: str | None
    thread_id: str | None
    from_name: str | None
    from_address: str | None
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]
    reply_to_addresses: list[str]
    sent_at: datetime | None
    received_at: datetime | None
    body_text: str | None
    body_html: str | None
    snippet: str | None
    has_attachments: bool


@dataclass(frozen=True)
class AttachmentRecordValues:
    base_values: ContentItemRecordValues
    parent_content_item_id: str | None
    container_content_item_id: str | None
    external_id: str | None
    email_message_content_item_id: str | None
    content_id_header: str | None
    disposition: str | None
    is_inline: bool
    attachment_index: int | None


@dataclass(frozen=True)
class FileTaskState:
    status: str | None
    task_id: str | None
    task_secret: str | None


def _split_path_parts(relative_path: str) -> tuple[str, str, str | None, bool]:
    """Extract parent_path, name, extension, is_hidden from relative_path."""
    if not relative_path:
        return ("", "", None, False)
    parent = os.path.dirname(relative_path)
    name = os.path.basename(relative_path)
    _, ext = os.path.splitext(name)
    extension = ext.lower() if ext else None
    hidden = name.startswith(".")
    return (parent, name, extension, hidden)


def _content_kind_value(kind: ContentItemKind) -> str:
    return kind.value


def _new_file_task_state(status: str | None, task_id: str | None) -> FileTaskState:
    return FileTaskState(
        status=status,
        task_id=task_id,
        task_secret=secrets.token_urlsafe(32) if task_id else None,
    )


def _build_file_record_values(
    *,
    folder_uuid: str,
    relative_path: str,
    modified_time: float,
    change_time: float,
    size_bytes: int,
    status: str | None,
    is_symlink: bool,
    display_name: str | None = None,
) -> ContentItemRecordValues:
    normalized_path = normalize_content_relative_path(relative_path)
    validate_non_negative_size(size_bytes)
    parent_path, name, extension, is_hidden = _split_path_parts(normalized_path)
    content_kind = _content_kind_value(ContentItemKind.FILE)
    validate_content_item_invariants(
        ContentItemInvariantInput(
            content_kind=content_kind,
            relative_path=normalized_path,
            size_bytes=size_bytes,
            is_dir=False,
            is_container=False,
        )
    )
    return ContentItemRecordValues(
        folder_uuid=folder_uuid,
        relative_path=normalized_path,
        content_kind=content_kind,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=status,
        parent_path=parent_path,
        name=name,
        display_name=display_name.strip()
        if isinstance(display_name, str) and display_name.strip()
        else name,
        extension=extension,
        mime_type=mimetypes.guess_type(normalized_path)[0],
        is_container=False,
        is_hidden=is_hidden,
        is_symlink=is_symlink,
    )


def _build_directory_record_values(
    *,
    folder_uuid: str,
    relative_path: str,
    is_symlink: bool,
) -> DirectoryRecordValues:
    normalized_path = normalize_content_relative_path(relative_path, allow_empty=True)
    parent_path, name, _, is_hidden = _split_path_parts(normalized_path)
    content_kind = _content_kind_value(ContentItemKind.FOLDER)
    validate_content_item_invariants(
        ContentItemInvariantInput(
            content_kind=content_kind,
            relative_path=normalized_path,
            size_bytes=0,
            is_dir=True,
            is_container=True,
        ),
        allow_empty_path=True,
    )
    return DirectoryRecordValues(
        folder_uuid=folder_uuid,
        relative_path=normalized_path,
        content_kind=content_kind,
        parent_path=parent_path,
        name=name,
        display_name=name,
        mime_type=None,
        is_container=True,
        is_hidden=is_hidden,
        is_symlink=is_symlink,
    )


def _build_email_message_record_values(
    *,
    folder_uuid: str,
    relative_path: str,
    external_id: str | None,
    modified_time: float,
    change_time: float,
    size_bytes: int,
    status: str | None,
    display_name: str | None,
    subject: str | None,
    message_id_header: str | None,
    thread_id: str | None,
    from_name: str | None,
    from_address: str | None,
    to_addresses: list[str] | None,
    cc_addresses: list[str] | None,
    bcc_addresses: list[str] | None,
    reply_to_addresses: list[str] | None,
    sent_at: datetime | None,
    received_at: datetime | None,
    body_text: str | None,
    body_html: str | None,
    snippet: str | None,
    has_attachments: bool,
) -> EmailMessageRecordValues:
    normalized_path = normalize_content_relative_path(relative_path)
    validate_non_negative_size(size_bytes)
    parent_path, name, _, is_hidden = _split_path_parts(normalized_path)
    resolved_subject = subject or ""
    resolved_display_name = display_name or resolved_subject or name or normalized_path
    validate_content_item_invariants(
        ContentItemInvariantInput(
            content_kind=ContentItemKind.EMAIL_MESSAGE,
            relative_path=normalized_path,
            size_bytes=size_bytes,
            is_dir=False,
            is_container=False,
            has_email_details=True,
        )
    )
    return EmailMessageRecordValues(
        folder_uuid=folder_uuid,
        relative_path=normalized_path,
        external_id=external_id,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=status,
        parent_path=parent_path,
        name=name or resolved_display_name,
        display_name=resolved_display_name,
        mime_type="message/rfc822",
        is_hidden=is_hidden,
        subject=resolved_subject,
        message_id_header=message_id_header,
        thread_id=thread_id,
        from_name=from_name,
        from_address=from_address,
        to_addresses=list(to_addresses or []),
        cc_addresses=list(cc_addresses or []),
        bcc_addresses=list(bcc_addresses or []),
        reply_to_addresses=list(reply_to_addresses or []),
        sent_at=sent_at,
        received_at=received_at,
        body_text=body_text,
        body_html=body_html,
        snippet=snippet,
        has_attachments=has_attachments,
    )


def _email_file_record_values(
    values: EmailMessageRecordValues,
) -> ContentItemRecordValues:
    return ContentItemRecordValues(
        folder_uuid=values.folder_uuid,
        relative_path=values.relative_path,
        content_kind=_content_kind_value(ContentItemKind.EMAIL_MESSAGE),
        modified_time=values.modified_time,
        change_time=values.change_time,
        size_bytes=values.size_bytes,
        status=values.status,
        parent_path=values.parent_path,
        name=values.name,
        display_name=values.display_name,
        extension=".eml",
        mime_type=values.mime_type,
        is_container=False,
        is_hidden=values.is_hidden,
        is_symlink=False,
    )


def _build_attachment_record_values(
    *,
    folder_uuid: str,
    relative_path: str,
    parent_content_item_id: str | None,
    container_content_item_id: str | None,
    external_id: str | None,
    email_message_content_item_id: str | None,
    modified_time: float,
    change_time: float,
    size_bytes: int,
    status: str | None,
    display_name: str | None,
    content_id_header: str | None,
    disposition: str | None,
    is_inline: bool,
    attachment_index: int | None,
    is_symlink: bool,
) -> AttachmentRecordValues:
    if not (
        parent_content_item_id
        and container_content_item_id
        and email_message_content_item_id
    ):
        raise ValueError("attachment content items require email parent linkage")
    base_file_values = _build_file_record_values(
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=status,
        is_symlink=is_symlink,
    )
    base_values = replace(
        base_file_values,
        content_kind=_content_kind_value(ContentItemKind.ATTACHMENT),
        display_name=display_name or base_file_values.name,
    )
    validate_content_item_invariants(
        ContentItemInvariantInput(
            content_kind=ContentItemKind.ATTACHMENT,
            relative_path=base_values.relative_path,
            size_bytes=base_values.size_bytes,
            is_dir=False,
            is_container=False,
            has_attachment_details=True,
            parent_content_item_id=parent_content_item_id,
            container_content_item_id=container_content_item_id,
            email_message_content_item_id=email_message_content_item_id,
        )
    )
    return AttachmentRecordValues(
        base_values=base_values,
        parent_content_item_id=parent_content_item_id,
        container_content_item_id=container_content_item_id,
        external_id=external_id,
        email_message_content_item_id=email_message_content_item_id,
        content_id_header=content_id_header,
        disposition=disposition,
        is_inline=is_inline,
        attachment_index=attachment_index,
    )
