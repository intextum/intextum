"""Tests for backend email-message content ingestion."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.sqlalchemy_models import IndexedContentItem
from models.task_queue import InlineDocumentSource
from services.content.email_ingestion import (
    EmailAttachmentInput,
    ingest_email_message,
)


@pytest.fixture
def mock_db_session():
    """Create a mock AsyncSession for content-ingestion tests."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_ingest_email_message_creates_message_attachments_and_process_task(
    mock_db_session,
):
    """Email ingestion should create the message, child attachments, and queue processing."""
    with patch(
        "services.content.email_ingestion.TaskQueueService.enqueue_process",
        new=AsyncMock(return_value="task-mail-1"),
    ) as enqueue_process:
        result = await ingest_email_message(
            mock_db_session,
            folder_uuid="mail-connector",
            relative_path="Inbox/2026-04-27/quarterly-update.eml",
            subject="Quarterly update",
            from_name="Alice Example",
            from_address="alice@example.com",
            to_addresses=["team@example.com"],
            cc_addresses=["finance@example.com"],
            body_text=(
                f"{'Hello team. ' * 90}"
                f"{'This is the quarterly update. ' * 90}"
                f"{'Revenue is stable and project delivery is on track. ' * 90}"
            ),
            snippet="This is the quarterly update.",
            external_id="imap:42",
            requested_by_sub="sub-admin",
            attachments=[
                EmailAttachmentInput(
                    relative_path="Inbox/2026-04-27/attachments/report.pdf",
                    display_name="report.pdf",
                    size_bytes=5120,
                    disposition="attachment",
                )
            ],
        )

    added_records = [call.args[0] for call in mock_db_session.add.call_args_list]
    message_record = next(
        rec
        for rec in added_records
        if isinstance(rec, IndexedContentItem) and rec.content_kind == "email_message"
    )
    attachment_record = next(
        rec
        for rec in added_records
        if isinstance(rec, IndexedContentItem) and rec.content_kind == "attachment"
    )

    assert result.content_item_id == message_record.content_item_id
    assert result.attachment_content_item_ids == [attachment_record.content_item_id]
    assert result.task_id == "task-mail-1"

    assert message_record.display_name == "Quarterly update"
    assert message_record.external_id == "imap:42"
    assert message_record.processing_status == "QUEUED"
    assert message_record.email_message_details is not None
    assert message_record.email_message_details.from_address == "alice@example.com"
    assert message_record.email_message_details.has_attachments is True

    assert attachment_record.parent_content_item_id == message_record.content_item_id
    assert attachment_record.container_content_item_id == message_record.content_item_id
    assert attachment_record.attachment_details is not None
    assert (
        attachment_record.attachment_details.email_message_content_item_id
        == message_record.content_item_id
    )

    mock_db_session.commit.assert_awaited()
    enqueue_request = enqueue_process.await_args.args[0]
    assert enqueue_request.content_item_id == message_record.content_item_id
    assert enqueue_request.requested_by_sub == "sub-admin"
    assert enqueue_request.relative_path.endswith(".eml")
    assert enqueue_request.metadata.inline_document_source == InlineDocumentSource(
        format="md",
        content=enqueue_request.metadata.inline_document_source.content,
    )
    assert "Quarterly update" in enqueue_request.metadata.inline_document_source.content
    assert (
        "Revenue is stable" in enqueue_request.metadata.inline_document_source.content
    )


@pytest.mark.asyncio
async def test_ingest_email_message_prefers_html_worker_source(mock_db_session):
    """Email ingestion should prefer HTML body content when building the worker source."""
    with patch(
        "services.content.email_ingestion.TaskQueueService.enqueue_process",
        new=AsyncMock(return_value="task-mail-html"),
    ) as enqueue_process:
        result = await ingest_email_message(
            mock_db_session,
            folder_uuid="mail-connector",
            relative_path="Inbox/newsletter.eml",
            subject="Newsletter",
            body_text="Plain fallback",
            body_html="<p><strong>Hello</strong> from HTML</p>",
        )

    assert result.task_id == "task-mail-html"
    enqueue_request = enqueue_process.await_args.args[0]
    assert enqueue_request.metadata.inline_document_source == InlineDocumentSource(
        format="html",
        content=enqueue_request.metadata.inline_document_source.content,
    )
    assert (
        "<strong>Hello</strong> from HTML"
        in enqueue_request.metadata.inline_document_source.content
    )
