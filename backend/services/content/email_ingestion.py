"""Helpers for ingesting email-message content items and queueing worker processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import ProcessingStatus
from models.task_queue import (
    EnqueueProcessTask,
    InlineDocumentSource,
    ProcessTaskMetadata,
)
from services.task_queue import TaskQueueService
from services.utils import compute_content_item_id

from .indexed_content_item import (
    upsert_attachment_entry,
    upsert_email_message_entry,
)


@dataclass(frozen=True)
class EmailAttachmentInput:
    """Attachment metadata for one ingested email message."""

    relative_path: str
    size_bytes: int = 0
    display_name: str | None = None
    content_item_id: str | None = None
    external_id: str | None = None
    content_id_header: str | None = None
    disposition: str | None = None
    is_inline: bool = False
    attachment_index: int | None = None
    modified_time: float = 0.0
    change_time: float = 0.0
    processing_status: str | None = None


@dataclass(frozen=True)
class EmailMessageIngestionResult:
    """Summary of one completed email-message ingestion run."""

    content_item_id: str
    attachment_content_item_ids: list[str]
    task_id: str | None


def _join_addresses(addresses: Sequence[str]) -> str:
    return ", ".join(
        part.strip() for part in addresses if isinstance(part, str) and part.strip()
    )


def _build_email_markdown_document(
    *,
    relative_path: str,
    subject: str | None,
    from_name: str | None,
    from_address: str | None,
    to_addresses: Sequence[str] | None,
    cc_addresses: Sequence[str] | None,
    bcc_addresses: Sequence[str] | None,
    reply_to_addresses: Sequence[str] | None,
    sent_at: datetime | None,
    received_at: datetime | None,
    snippet: str | None,
    body_text: str | None,
) -> str:
    """Build one markdown document representing the email message for Docling."""
    title = (subject or "").strip() or relative_path.rsplit("/", 1)[-1]
    lines = [f"# {title}", ""]

    sender = " ".join(
        part.strip()
        for part in [from_name or "", f"<{from_address}>" if from_address else ""]
        if part.strip()
    ).strip()
    if sender:
        lines.append(f"**From:** {sender}")

    recipients = _join_addresses(list(to_addresses or []))
    if recipients:
        lines.append(f"**To:** {recipients}")

    copied = _join_addresses(list(cc_addresses or []))
    if copied:
        lines.append(f"**Cc:** {copied}")

    blind_copied = _join_addresses(list(bcc_addresses or []))
    if blind_copied:
        lines.append(f"**Bcc:** {blind_copied}")

    replies = _join_addresses(list(reply_to_addresses or []))
    if replies:
        lines.append(f"**Reply-To:** {replies}")

    if sent_at is not None:
        lines.append(f"**Sent:** {sent_at.isoformat()}")
    elif received_at is not None:
        lines.append(f"**Received:** {received_at.isoformat()}")

    normalized_snippet = (snippet or "").strip()
    normalized_body = (body_text or "").strip()

    if lines[-1] != "":
        lines.append("")
    if normalized_snippet and normalized_snippet not in normalized_body:
        lines.extend(["## Snippet", "", normalized_snippet, ""])

    if normalized_body:
        lines.extend(["## Message Body", "", normalized_body])

    return "\n".join(lines).strip()


def _build_email_html_document(
    *,
    relative_path: str,
    subject: str | None,
    from_name: str | None,
    from_address: str | None,
    to_addresses: Sequence[str] | None,
    cc_addresses: Sequence[str] | None,
    bcc_addresses: Sequence[str] | None,
    reply_to_addresses: Sequence[str] | None,
    sent_at: datetime | None,
    received_at: datetime | None,
    snippet: str | None,
    body_html: str,
) -> str:
    """Build one HTML document representing the email message for Docling."""
    title = (subject or "").strip() or relative_path.rsplit("/", 1)[-1]
    fields: list[str] = []

    sender = " ".join(
        part.strip()
        for part in [from_name or "", f"&lt;{from_address}&gt;" if from_address else ""]
        if part.strip()
    ).strip()
    if sender:
        fields.append(f"<p><strong>From:</strong> {sender}</p>")

    recipients = _join_addresses(list(to_addresses or []))
    if recipients:
        fields.append(f"<p><strong>To:</strong> {recipients}</p>")

    copied = _join_addresses(list(cc_addresses or []))
    if copied:
        fields.append(f"<p><strong>Cc:</strong> {copied}</p>")

    blind_copied = _join_addresses(list(bcc_addresses or []))
    if blind_copied:
        fields.append(f"<p><strong>Bcc:</strong> {blind_copied}</p>")

    replies = _join_addresses(list(reply_to_addresses or []))
    if replies:
        fields.append(f"<p><strong>Reply-To:</strong> {replies}</p>")

    if sent_at is not None:
        fields.append(f"<p><strong>Sent:</strong> {sent_at.isoformat()}</p>")
    elif received_at is not None:
        fields.append(f"<p><strong>Received:</strong> {received_at.isoformat()}</p>")

    normalized_snippet = (snippet or "").strip()
    snippet_block = (
        f"<section><h2>Snippet</h2><p>{normalized_snippet}</p></section>"
        if normalized_snippet
        else ""
    )

    metadata_block = "".join(fields)
    return (
        "<html><body>"
        f"<h1>{title}</h1>"
        f"{metadata_block}"
        f"{snippet_block}"
        f"<section><h2>Message Body</h2>{body_html}</section>"
        "</body></html>"
    )


def _build_email_inline_document_source(
    *,
    relative_path: str,
    subject: str | None,
    from_name: str | None,
    from_address: str | None,
    to_addresses: Sequence[str] | None,
    cc_addresses: Sequence[str] | None,
    bcc_addresses: Sequence[str] | None,
    reply_to_addresses: Sequence[str] | None,
    sent_at: datetime | None,
    received_at: datetime | None,
    snippet: str | None,
    body_text: str | None,
    body_html: str | None,
) -> InlineDocumentSource:
    """Build the worker-side inline document source for one email message."""
    normalized_html = (body_html or "").strip()
    if normalized_html:
        return InlineDocumentSource(
            format="html",
            content=_build_email_html_document(
                relative_path=relative_path,
                subject=subject,
                from_name=from_name,
                from_address=from_address,
                to_addresses=to_addresses,
                cc_addresses=cc_addresses,
                bcc_addresses=bcc_addresses,
                reply_to_addresses=reply_to_addresses,
                sent_at=sent_at,
                received_at=received_at,
                snippet=snippet,
                body_html=normalized_html,
            ),
        )

    return InlineDocumentSource(
        format="md",
        content=_build_email_markdown_document(
            relative_path=relative_path,
            subject=subject,
            from_name=from_name,
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            reply_to_addresses=reply_to_addresses,
            sent_at=sent_at,
            received_at=received_at,
            snippet=snippet,
            body_text=body_text,
        ),
    )


async def ingest_email_message(
    db: AsyncSession,
    *,
    folder_uuid: str,
    relative_path: str,
    subject: str | None = None,
    from_name: str | None = None,
    from_address: str | None = None,
    to_addresses: Sequence[str] | None = None,
    cc_addresses: Sequence[str] | None = None,
    bcc_addresses: Sequence[str] | None = None,
    reply_to_addresses: Sequence[str] | None = None,
    body_text: str | None = None,
    body_html: str | None = None,
    snippet: str | None = None,
    external_id: str | None = None,
    message_id_header: str | None = None,
    thread_id: str | None = None,
    sent_at: datetime | None = None,
    received_at: datetime | None = None,
    size_bytes: int = 0,
    modified_time: float = 0.0,
    change_time: float = 0.0,
    display_name: str | None = None,
    content_item_id: str | None = None,
    attachments: Sequence[EmailAttachmentInput] | None = None,
    allowed_viewers: list[str] | None = None,
    denied_viewers: list[str] | None = None,
    requested_by_sub: str | None = None,
) -> EmailMessageIngestionResult:
    """Create/update one email message, seed attachments, and enqueue worker processing."""
    resolved_content_item_id = content_item_id or compute_content_item_id(
        folder_uuid, relative_path
    )
    attachment_inputs = list(attachments or [])

    await upsert_email_message_entry(
        db,
        content_item_id=resolved_content_item_id,
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        external_id=external_id,
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        status=ProcessingStatus.QUEUED,
        display_name=display_name,
        subject=subject,
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
        has_attachments=bool(attachment_inputs),
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        auto_commit=False,
    )

    attachment_content_item_ids: list[str] = []
    for default_index, attachment in enumerate(attachment_inputs):
        attachment_content_item_id = (
            attachment.content_item_id
            or compute_content_item_id(folder_uuid, attachment.relative_path)
        )
        attachment_content_item_ids.append(attachment_content_item_id)
        await upsert_attachment_entry(
            db,
            content_item_id=attachment_content_item_id,
            folder_uuid=folder_uuid,
            relative_path=attachment.relative_path,
            parent_content_item_id=resolved_content_item_id,
            container_content_item_id=resolved_content_item_id,
            external_id=attachment.external_id,
            email_message_content_item_id=resolved_content_item_id,
            modified_time=attachment.modified_time,
            change_time=attachment.change_time,
            size_bytes=attachment.size_bytes,
            status=attachment.processing_status,
            display_name=attachment.display_name,
            content_id_header=attachment.content_id_header,
            disposition=attachment.disposition,
            is_inline=attachment.is_inline,
            attachment_index=(
                attachment.attachment_index
                if attachment.attachment_index is not None
                else default_index
            ),
            allowed_viewers=allowed_viewers,
            denied_viewers=denied_viewers,
            auto_commit=False,
        )

    metadata = ProcessTaskMetadata(
        content_item_id=resolved_content_item_id,
        size_bytes=size_bytes,
        modified_time=modified_time,
        created_time=change_time,
        file_extension=".eml",
        source_name=None,
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        inline_document_source=_build_email_inline_document_source(
            relative_path=relative_path,
            subject=subject,
            from_name=from_name,
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            reply_to_addresses=reply_to_addresses,
            sent_at=sent_at,
            received_at=received_at,
            snippet=snippet,
            body_text=body_text,
            body_html=body_html,
        ),
    )

    task_id = await TaskQueueService(db).enqueue_process(
        EnqueueProcessTask(
            content_item_id=resolved_content_item_id,
            folder_uuid=folder_uuid,
            relative_path=relative_path,
            metadata=metadata,
            requested_by_sub=requested_by_sub,
        ),
        auto_commit=False,
    )
    await db.commit()

    return EmailMessageIngestionResult(
        content_item_id=resolved_content_item_id,
        attachment_content_item_ids=attachment_content_item_ids,
        task_id=task_id,
    )
