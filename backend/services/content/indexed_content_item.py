"""IndexedContentItem CRUD operations (stateless async helpers)."""

import os
import secrets
import mimetypes
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.enums import ProcessingStatus
from models.sqlalchemy_models import (
    ContentItemAttachmentDetails,
    ContentItemEmailMessageDetails,
    IndexedContentItem,
)
from models.content.items import ContentItemKind
from services.content.invariants import (
    ContentItemInvariantInput,
    normalize_content_relative_path,
    validate_content_item_invariants,
    validate_non_negative_size,
)
from services.content.audit import ContentAuditService
from services.utils import utcnow

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


async def _get_indexed_content_item(
    db: AsyncSession, content_item_id: str
) -> IndexedContentItem | None:
    stmt = select(IndexedContentItem).where(
        IndexedContentItem.content_item_id == content_item_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _add_record(
    db: AsyncSession, record: IndexedContentItem, *, auto_commit: bool
) -> None:
    db.add(record)
    if not auto_commit:
        await db.flush()


async def _append_created_audit_event(
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    source: str = "content_index",
) -> None:
    await ContentAuditService(db).append_for_record(
        record,
        event_type="content.created",
        event_group="content",
        status="completed",
        summary=f"Content item created: {record.display_name or record.name or record.relative_path}",
        metadata={
            "content_kind": record.content_kind,
            "size_bytes": record.size_bytes,
            "processing_status": record.processing_status,
        },
        source=source,
    )


def _set_acl_fields(
    record: IndexedContentItem,
    allowed_viewers: list[str] | None,
    denied_viewers: list[str] | None,
) -> None:
    if allowed_viewers is not None:
        record.allowed_viewers = allowed_viewers
    if denied_viewers is not None:
        record.denied_viewers = denied_viewers


def _set_file_fields(
    record: IndexedContentItem,
    values: ContentItemRecordValues,
) -> None:
    record.folder_uuid = values.folder_uuid
    record.relative_path = values.relative_path
    record.content_kind = values.content_kind
    record.modified_time = values.modified_time
    record.change_time = values.change_time
    record.size_bytes = values.size_bytes
    record.processing_status = values.status
    record.parent_path = values.parent_path
    record.name = values.name
    record.display_name = values.display_name
    record.extension = values.extension
    record.mime_type = values.mime_type
    record.is_container = values.is_container
    record.is_hidden = values.is_hidden
    record.is_symlink = values.is_symlink
    record.is_dir = False


def _clear_incompatible_detail_rows(
    record: IndexedContentItem,
    content_kind: str,
) -> None:
    """Remove stale kind-specific relationships after a kind change."""
    if content_kind not in {
        _content_kind_value(ContentItemKind.FILE),
        _content_kind_value(ContentItemKind.ATTACHMENT),
    }:
        record.file_details = None
    if content_kind != _content_kind_value(ContentItemKind.FOLDER):
        record.folder_details = None
    if content_kind != _content_kind_value(ContentItemKind.EMAIL_MESSAGE):
        record.email_message_details = None
    if content_kind != _content_kind_value(ContentItemKind.ATTACHMENT):
        record.attachment_details = None


def _set_content_item_relationship_fields(
    record: IndexedContentItem,
    *,
    parent_content_item_id: str | None = None,
    container_content_item_id: str | None = None,
    external_id: str | None = None,
) -> None:
    record.parent_content_item_id = parent_content_item_id
    record.container_content_item_id = container_content_item_id
    record.external_id = external_id


def _set_file_task_state(
    record: IndexedContentItem,
    task_state: FileTaskState,
) -> None:
    if task_state.task_id:
        record.task_id = task_state.task_id
        record.task_secret = task_state.task_secret
    elif task_state.status in TERMINAL_PROCESSING_STATUSES:
        record.task_secret = None

    if task_state.status == ProcessingStatus.QUEUED:
        record.error_message = None
    if task_state.status == ProcessingStatus.COMPLETED:
        record.indexed_at = utcnow()


def _new_file_task_state(status: str | None, task_id: str | None) -> FileTaskState:
    return FileTaskState(
        status=status,
        task_id=task_id,
        task_secret=secrets.token_urlsafe(32) if task_id else None,
    )


def _new_file_record(
    content_item_id: str,
    values: ContentItemRecordValues,
    task_state: FileTaskState,
    allowed_viewers: list[str] | None,
    denied_viewers: list[str] | None,
) -> IndexedContentItem:
    return IndexedContentItem(
        content_item_id=content_item_id,
        folder_uuid=values.folder_uuid,
        content_kind=values.content_kind,
        relative_path=values.relative_path,
        modified_time=values.modified_time,
        change_time=values.change_time,
        size_bytes=values.size_bytes,
        processing_status=values.status,
        task_id=task_state.task_id,
        task_secret=task_state.task_secret,
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        indexed_at=utcnow() if values.status == ProcessingStatus.COMPLETED else None,
        parent_path=values.parent_path,
        name=values.name,
        display_name=values.display_name,
        extension=values.extension,
        mime_type=values.mime_type,
        is_container=values.is_container,
        is_hidden=values.is_hidden,
        is_symlink=values.is_symlink,
        is_dir=False,
    )


async def _upsert_file_record_base(
    db: AsyncSession,
    *,
    content_item_id: str,
    values: ContentItemRecordValues,
    task_state: FileTaskState,
    allowed_viewers: list[str] | None,
    denied_viewers: list[str] | None,
    auto_commit: bool,
    parent_content_item_id: str | None = None,
    container_content_item_id: str | None = None,
    external_id: str | None = None,
) -> IndexedContentItem:
    record = await _get_indexed_content_item(db, content_item_id)

    if record:
        _set_file_fields(record=record, values=values)
    else:
        record = _new_file_record(
            content_item_id=content_item_id,
            values=values,
            task_state=task_state,
            allowed_viewers=allowed_viewers,
            denied_viewers=denied_viewers,
        )
        await _add_record(db, record, auto_commit=auto_commit)
        await _append_created_audit_event(db, record)

    _set_content_item_relationship_fields(
        record,
        parent_content_item_id=parent_content_item_id,
        container_content_item_id=container_content_item_id,
        external_id=external_id,
    )
    _clear_incompatible_detail_rows(record, values.content_kind)
    _set_acl_fields(record, allowed_viewers, denied_viewers)
    _set_file_task_state(record, task_state)
    return record


def _set_email_message_details(
    record: IndexedContentItem,
    values: EmailMessageRecordValues,
) -> None:
    details = record.email_message_details
    if details is None:
        details = ContentItemEmailMessageDetails(content_item_id=record.content_item_id)
        record.email_message_details = details
    details.message_id_header = values.message_id_header
    details.thread_id = values.thread_id
    details.subject = values.subject
    details.from_name = values.from_name
    details.from_address = values.from_address
    details.to_addresses_json = list(values.to_addresses)
    details.cc_addresses_json = list(values.cc_addresses)
    details.bcc_addresses_json = list(values.bcc_addresses)
    details.reply_to_addresses_json = list(values.reply_to_addresses)
    details.sent_at = values.sent_at
    details.received_at = values.received_at
    details.body_text = values.body_text
    details.body_html = values.body_html
    details.snippet = values.snippet
    details.has_attachments = values.has_attachments


def _set_attachment_details(
    record: IndexedContentItem,
    values: AttachmentRecordValues,
) -> None:
    details = record.attachment_details
    if details is None:
        details = ContentItemAttachmentDetails(content_item_id=record.content_item_id)
        record.attachment_details = details
    details.email_message_content_item_id = values.email_message_content_item_id
    details.content_id_header = values.content_id_header
    details.disposition = values.disposition
    details.is_inline = values.is_inline
    details.attachment_index = values.attachment_index


def _set_directory_fields(
    record: IndexedContentItem,
    values: DirectoryRecordValues,
) -> None:
    record.folder_uuid = values.folder_uuid
    record.relative_path = values.relative_path
    record.content_kind = values.content_kind
    record.modified_time = 0.0
    record.change_time = 0.0
    record.size_bytes = 0
    record.processing_status = ProcessingStatus.COMPLETED
    record.parent_path = values.parent_path
    record.name = values.name
    record.display_name = values.display_name
    record.extension = None
    record.mime_type = values.mime_type
    record.is_container = values.is_container
    record.is_hidden = values.is_hidden
    record.is_symlink = values.is_symlink
    record.is_dir = True


def _new_directory_record(
    content_item_id: str,
    values: DirectoryRecordValues,
    allowed_viewers: list[str] | None,
    denied_viewers: list[str] | None,
) -> IndexedContentItem:
    return IndexedContentItem(
        content_item_id=content_item_id,
        folder_uuid=values.folder_uuid,
        content_kind=values.content_kind,
        relative_path=values.relative_path,
        modified_time=0.0,
        change_time=0.0,
        size_bytes=0,
        processing_status=ProcessingStatus.COMPLETED,
        parent_path=values.parent_path,
        name=values.name,
        display_name=values.display_name,
        mime_type=values.mime_type,
        is_container=values.is_container,
        is_hidden=values.is_hidden,
        is_symlink=values.is_symlink,
        is_dir=True,
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
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


async def upsert_indexed_content_item(
    db: AsyncSession,
    content_item_id: str,
    folder_uuid: str,
    relative_path: str,
    modified_time: float,
    change_time: float,
    size_bytes: int,
    status: str | None = ProcessingStatus.QUEUED,
    task_id: str | None = None,
    allowed_viewers: list[str] | None = None,
    denied_viewers: list[str] | None = None,
    is_symlink: bool = False,
    display_name: str | None = None,
    auto_commit: bool = True,
) -> str | None:
    """Insert or update a file record to track processing state.

    Returns the task_secret (needed by the worker to authenticate status updates).
    """
    task_state = _new_file_task_state(status, task_id)

    values = _build_file_record_values(
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=status,
        is_symlink=is_symlink,
        display_name=display_name,
    )
    await _upsert_file_record_base(
        db,
        content_item_id=content_item_id,
        values=values,
        task_state=task_state,
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        auto_commit=auto_commit,
    )

    if auto_commit:
        await db.commit()
    return task_state.task_secret


async def upsert_directory_entry(
    db: AsyncSession,
    content_item_id: str,
    folder_uuid: str,
    relative_path: str,
    allowed_viewers: list[str] | None = None,
    denied_viewers: list[str] | None = None,
    is_symlink: bool = False,
    auto_commit: bool = True,
) -> None:
    """Insert or update a directory entry (no processing fields)."""
    values = _build_directory_record_values(
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        is_symlink=is_symlink,
    )
    record = await _get_indexed_content_item(db, content_item_id)

    if record:
        _set_directory_fields(record=record, values=values)
        _set_content_item_relationship_fields(record)
        _clear_incompatible_detail_rows(record, values.content_kind)
        _set_acl_fields(record, allowed_viewers, denied_viewers)
    else:
        record = _new_directory_record(
            content_item_id=content_item_id,
            values=values,
            allowed_viewers=allowed_viewers,
            denied_viewers=denied_viewers,
        )
        await _add_record(db, record, auto_commit=auto_commit)
        await _append_created_audit_event(db, record)

    if auto_commit:
        await db.commit()


async def upsert_email_message_entry(
    db: AsyncSession,
    *,
    content_item_id: str,
    folder_uuid: str,
    relative_path: str,
    external_id: str | None = None,
    modified_time: float = 0.0,
    change_time: float = 0.0,
    size_bytes: int = 0,
    status: str | None = ProcessingStatus.QUEUED,
    task_id: str | None = None,
    display_name: str | None = None,
    subject: str | None = None,
    message_id_header: str | None = None,
    thread_id: str | None = None,
    from_name: str | None = None,
    from_address: str | None = None,
    to_addresses: list[str] | None = None,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
    reply_to_addresses: list[str] | None = None,
    sent_at: datetime | None = None,
    received_at: datetime | None = None,
    body_text: str | None = None,
    body_html: str | None = None,
    snippet: str | None = None,
    has_attachments: bool = False,
    allowed_viewers: list[str] | None = None,
    denied_viewers: list[str] | None = None,
    auto_commit: bool = True,
) -> str | None:
    """Insert or update one email-message content item and its detail row."""
    task_state = _new_file_task_state(status, task_id)
    values = _build_email_message_record_values(
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        external_id=external_id,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=status,
        display_name=display_name,
        subject=subject,
        message_id_header=message_id_header,
        thread_id=thread_id,
        from_name=from_name,
        from_address=from_address,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        reply_to_addresses=reply_to_addresses,
        sent_at=sent_at,
        received_at=received_at,
        body_text=body_text,
        body_html=body_html,
        snippet=snippet,
        has_attachments=has_attachments,
    )
    record = await _upsert_file_record_base(
        db,
        content_item_id=content_item_id,
        values=_email_file_record_values(values),
        task_state=task_state,
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        auto_commit=auto_commit,
        external_id=values.external_id,
    )

    _set_email_message_details(record, values)

    if auto_commit:
        await db.commit()
    return task_state.task_secret


async def upsert_attachment_entry(
    db: AsyncSession,
    *,
    content_item_id: str,
    folder_uuid: str,
    relative_path: str,
    parent_content_item_id: str | None = None,
    container_content_item_id: str | None = None,
    external_id: str | None = None,
    email_message_content_item_id: str | None = None,
    modified_time: float,
    change_time: float,
    size_bytes: int,
    status: str | None = ProcessingStatus.QUEUED,
    task_id: str | None = None,
    display_name: str | None = None,
    content_id_header: str | None = None,
    disposition: str | None = None,
    is_inline: bool = False,
    attachment_index: int | None = None,
    allowed_viewers: list[str] | None = None,
    denied_viewers: list[str] | None = None,
    is_symlink: bool = False,
    auto_commit: bool = True,
) -> str | None:
    """Insert or update one attachment content item and its detail row."""
    task_state = _new_file_task_state(status, task_id)
    values = _build_attachment_record_values(
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        parent_content_item_id=parent_content_item_id,
        container_content_item_id=container_content_item_id,
        external_id=external_id,
        email_message_content_item_id=email_message_content_item_id,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=status,
        display_name=display_name,
        content_id_header=content_id_header,
        disposition=disposition,
        is_inline=is_inline,
        attachment_index=attachment_index,
        is_symlink=is_symlink,
    )
    record = await _upsert_file_record_base(
        db,
        content_item_id=content_item_id,
        values=values.base_values,
        task_state=task_state,
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        auto_commit=auto_commit,
        parent_content_item_id=values.parent_content_item_id,
        container_content_item_id=values.container_content_item_id,
        external_id=values.external_id,
    )

    _set_attachment_details(record, values)

    if auto_commit:
        await db.commit()
    return task_state.task_secret
