import io
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi import UploadFile
from starlette.requests import Request

from models.content.enrichment_training import (
    ContentEnrichmentTrainingExample,
    ContentEnrichmentWorkerTrainingDataset,
)
from services.content.indexed_content_item import (
    upsert_attachment_entry,
    upsert_directory_entry,
    upsert_email_message_entry,
    upsert_indexed_content_item,
)
from models.task_queue import (
    ClaimedTask,
    EnqueueProcessTask,
    ProcessTaskMetadata,
    TaskFailureResult,
)
from models.enums import TaskStatus
from models.sqlalchemy_models import (
    ContentItemAttachmentDetails,
    ContentItemEmailMessageDetails,
    IndexedContentItem,
    TaskQueue,
)
from models.worker import (
    AbortTaskRequest,
    CheckSupersededRequest,
    ClaimTaskRequest,
    CompleteContentEnrichmentTrainingTaskRequest,
    CompleteTaskRequest,
    ContentEnrichmentTaskSourceResponse,
    ContentEnrichmentTrainingArtifactUploadResponse,
    FailTaskRequest,
    HeartbeatTaskRequest,
)
from routers.worker.tasks import (
    abort_task_endpoint,
    claim_task,
    check_superseded,
    upload_content_enrichment_training_artifact,
    complete_content_enrichment_training_task,
    complete_task,
    fail_task,
    get_content_enrichment_task_source,
    get_content_enrichment_training_dataset,
    heartbeat_task,
)
from services.task_queue import TaskQueueService
from services.task_queue.ops import TaskQueueAccessOperations

# --- Fixtures ---


def test_task_response_prefers_row_content_item_id_over_stale_metadata():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        folder_uuid="folder-uuid",
        relative_path="document.pdf",
        content_item_id="current-file",
        metadata_json='{"content_item_id":"stale-file"}',
        task_secret="secret-1",
        retry_count=0,
    )

    response = TaskQueueAccessOperations.task_response(task)

    assert response.content_item_id == "current-file"
    assert response.metadata["content_item_id"] == "current-file"


def test_task_metadata_prefers_row_content_item_id_over_stale_metadata():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        folder_uuid="folder-uuid",
        relative_path="document.pdf",
        content_item_id="current-file",
        metadata_json='{"content_item_id":"stale-file"}',
        task_secret="secret-1",
        retry_count=0,
    )

    metadata = TaskQueueAccessOperations.task_metadata(task)

    assert metadata.content_item_id == "current-file"


def test_task_response_ignores_non_object_metadata_json():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        folder_uuid="folder-uuid",
        relative_path="document.pdf",
        content_item_id="current-file",
        metadata_json='["not", "an", "object"]',
        task_secret="secret-1",
        retry_count=0,
    )

    response = TaskQueueAccessOperations.task_response(task)

    assert response.content_item_id == "current-file"
    assert response.metadata == {"content_item_id": "current-file"}


@pytest.mark.asyncio
async def test_newer_active_task_id_returns_matching_task_id(mock_db_session):
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "task-2"
    mock_db_session.execute.return_value = execute_result
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        created_at=datetime(2026, 5, 9, 10, 0, 0),
    )

    assert await svc.worker_lifecycle._newer_active_task_id(task) == "task-2"


@pytest.mark.asyncio
async def test_newer_active_task_id_skips_tasks_without_content_timestamp(
    mock_db_session,
):
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(id="task-1", task_type="process", content_item_id="file-1")

    assert await svc.worker_lifecycle._newer_active_task_id(task) is None
    mock_db_session.execute.assert_not_awaited()


@pytest.fixture
def mock_db_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    # Setup execute to return a result with scalar_one_or_none
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result
    return session


@pytest.fixture
def mock_record():
    """Create a mock IndexedContentItem record."""
    record = IndexedContentItem(
        content_item_id="test_file_id",
        folder_uuid="folder1",
        relative_path="path/to/file",
        modified_time=12345.0,
        size_bytes=100,
        processing_status="QUEUED",
        task_id="old_task_id",
        task_secret="old_secret",
    )
    return record


# --- Tests for upsert_indexed_content_item ---


@pytest.mark.asyncio
async def test_upsert_generates_secret_for_new_task(mock_db_session):
    """Test that a new secret is generated when a task_id is provided."""
    # Simulate existing record
    record = IndexedContentItem(content_item_id="123")
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = record

    task_id = "new_task_uuid"
    secret = await upsert_indexed_content_item(
        mock_db_session,
        "123",
        "uuid",
        "path",
        1.0,
        1.0,
        100,
        status="QUEUED",
        task_id=task_id,
    )

    assert secret is not None
    assert len(secret) > 0
    assert record.task_id == task_id
    assert record.task_secret == secret
    assert record.processing_status == "QUEUED"


@pytest.mark.asyncio
async def test_upsert_clears_secret_on_terminal_status(mock_db_session):
    """Test that secret is cleared when status is terminal and no new task_id."""
    record = IndexedContentItem(
        content_item_id="123", task_id="old_task", task_secret="sensitive_secret"
    )
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = record

    # Update to COMPLETED without new task_id
    await upsert_indexed_content_item(
        mock_db_session, "123", "uuid", "path", 1.0, 1.0, 100, status="COMPLETED"
    )

    assert record.task_secret is None
    assert record.processing_status == "COMPLETED"


@pytest.mark.asyncio
async def test_upsert_does_not_clear_secret_on_non_terminal(mock_db_session):
    """Test that secret is preserved on non-terminal status updates."""
    record = IndexedContentItem(
        content_item_id="123", task_id="current_task", task_secret="keep_me"
    )
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = record

    # Update to PROCESSING
    await upsert_indexed_content_item(
        mock_db_session, "123", "uuid", "path", 1.0, 1.0, 100, status="PROCESSING"
    )

    assert record.task_secret == "keep_me"
    assert record.processing_status == "PROCESSING"


@pytest.mark.asyncio
async def test_upsert_regenerates_secret_on_retry(mock_db_session):
    """Test that a new secret is generated if we retry (provide new task_id) even if status is terminal."""
    record = IndexedContentItem(
        content_item_id="123",
        task_id="failed_task",
        task_secret="old_secret",
        processing_status="FAILED",
    )
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = record

    new_task_id = "retry_task_uuid"

    # Retry logic calls upsert with new task_id and status=QUEUED usually
    secret = await upsert_indexed_content_item(
        mock_db_session,
        "123",
        "uuid",
        "path",
        1.0,
        1.0,
        100,
        status="QUEUED",
        task_id=new_task_id,
    )

    assert secret is not None
    assert secret != "old_secret"
    assert record.task_secret == secret
    assert record.task_id == new_task_id


@pytest.mark.asyncio
async def test_upsert_indexed_content_item_can_skip_autocommit(mock_db_session):
    """upsert_indexed_content_item should not commit when auto_commit=False."""
    record = IndexedContentItem(content_item_id="123")
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = record

    await upsert_indexed_content_item(
        mock_db_session,
        "123",
        "uuid",
        "path",
        1.0,
        1.0,
        100,
        status="QUEUED",
        auto_commit=False,
    )

    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_indexed_content_item_rejects_invalid_path_and_size(
    mock_db_session,
):
    with pytest.raises(ValueError, match="absolute"):
        await upsert_indexed_content_item(
            mock_db_session,
            "123",
            "uuid",
            "/absolute.pdf",
            1.0,
            1.0,
            100,
        )

    with pytest.raises(ValueError, match="non-negative"):
        await upsert_indexed_content_item(
            mock_db_session,
            "123",
            "uuid",
            "path.pdf",
            1.0,
            1.0,
            -1,
        )


@pytest.mark.asyncio
async def test_upsert_file_clears_stale_email_and_attachment_details(mock_db_session):
    record = IndexedContentItem(
        content_item_id="123",
        content_kind="email_message",
        folder_uuid="uuid",
        relative_path="mail/message.eml",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=10,
        is_dir=False,
        is_container=False,
        parent_content_item_id="mail-parent",
        container_content_item_id="mail-parent",
        external_id="external-1",
    )
    record.email_message_details = ContentItemEmailMessageDetails(
        content_item_id="123",
        subject="Old mail",
    )
    record.attachment_details = ContentItemAttachmentDetails(
        content_item_id="123",
        email_message_content_item_id="mail-parent",
    )
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = record

    await upsert_indexed_content_item(
        mock_db_session,
        "123",
        "uuid",
        "docs/file.pdf",
        1.0,
        1.0,
        100,
        auto_commit=False,
    )

    assert record.content_kind == "file"
    assert record.parent_content_item_id is None
    assert record.container_content_item_id is None
    assert record.external_id is None
    assert record.email_message_details is None
    assert record.attachment_details is None


@pytest.mark.asyncio
async def test_upsert_directory_entry_can_skip_autocommit(mock_db_session):
    """upsert_directory_entry should not commit when auto_commit=False."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db_session.add = MagicMock()

    await upsert_directory_entry(
        mock_db_session,
        content_item_id="dir123",
        folder_uuid="folder1",
        relative_path="nested",
        auto_commit=False,
    )

    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_email_message_entry_creates_kind_and_details(mock_db_session):
    """Email message upserts should persist the future mail-specific detail row."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db_session.add = MagicMock()

    secret = await upsert_email_message_entry(
        mock_db_session,
        content_item_id="mail-123",
        folder_uuid="connector-1",
        relative_path="Inbox/msg-123.eml",
        external_id="imap:msg-123",
        subject="Quarterly update",
        from_name="Alice Example",
        from_address="alice@example.com",
        to_addresses=["team@example.com"],
        body_text="Hello team",
        has_attachments=True,
        task_id="task-mail-123",
        auto_commit=False,
    )

    added = next(
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], IndexedContentItem)
    )
    assert secret
    assert added.content_kind == "email_message"
    assert added.display_name == "Quarterly update"
    assert added.external_id == "imap:msg-123"
    assert added.mime_type == "message/rfc822"
    assert added.email_message_details is not None
    assert added.email_message_details.subject == "Quarterly update"
    assert added.email_message_details.from_address == "alice@example.com"
    assert added.email_message_details.to_addresses_json == ["team@example.com"]
    assert added.email_message_details.has_attachments is True
    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_attachment_entry_creates_relationship_metadata(mock_db_session):
    """Attachment upserts should preserve parent/message linkage and attachment details."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db_session.add = MagicMock()

    secret = await upsert_attachment_entry(
        mock_db_session,
        content_item_id="attachment-1",
        folder_uuid="connector-1",
        relative_path="Inbox/attachments/invoice.pdf",
        parent_content_item_id="mail-123",
        container_content_item_id="mail-123",
        email_message_content_item_id="mail-123",
        external_id="imap:msg-123:attachment-1",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=128,
        display_name="Invoice attachment",
        disposition="attachment",
        attachment_index=0,
        task_id="task-attachment-1",
        auto_commit=False,
    )

    added = next(
        call.args[0]
        for call in mock_db_session.add.call_args_list
        if isinstance(call.args[0], IndexedContentItem)
    )
    assert secret
    assert added.content_kind == "attachment"
    assert added.display_name == "Invoice attachment"
    assert added.parent_content_item_id == "mail-123"
    assert added.container_content_item_id == "mail-123"
    assert added.external_id == "imap:msg-123:attachment-1"
    assert added.attachment_details is not None
    assert added.attachment_details.email_message_content_item_id == "mail-123"
    assert added.attachment_details.disposition == "attachment"
    assert added.attachment_details.attachment_index == 0
    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_attachment_entry_requires_email_parent_linkage(mock_db_session):
    with pytest.raises(ValueError, match="email parent linkage"):
        await upsert_attachment_entry(
            mock_db_session,
            content_item_id="attachment-1",
            folder_uuid="connector-1",
            relative_path="Inbox/attachments/invoice.pdf",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=128,
            auto_commit=False,
        )


@pytest.mark.asyncio
async def test_enqueue_process_can_skip_autocommit(mock_db_session):
    """enqueue_process should support batched transactions via auto_commit=False."""
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db_session.add = MagicMock()
    svc = TaskQueueService(mock_db_session)

    task_id = await svc.enqueue_process(
        EnqueueProcessTask(
            content_item_id="file123",
            folder_uuid="folder1",
            relative_path="docs/file.pdf",
            metadata=ProcessTaskMetadata(
                content_item_id="file123",
                modified_time=1.0,
                created_time=1.0,
                size_bytes=5,
            ),
        ),
        auto_commit=False,
    )

    assert isinstance(task_id, str) and task_id
    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_process_persists_requested_by_sub(mock_db_session):
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_db_session.add = MagicMock()
    svc = TaskQueueService(mock_db_session)

    await svc.enqueue_process(
        EnqueueProcessTask(
            content_item_id="file123",
            folder_uuid="folder1",
            relative_path="docs/file.pdf",
            metadata=ProcessTaskMetadata(
                content_item_id="file123",
                modified_time=1.0,
                created_time=1.0,
                size_bytes=5,
                source_name="documents",
            ),
            requested_by_sub="sub-testuser",
        ),
        auto_commit=False,
    )

    added_task = mock_db_session.add.call_args_list[0].args[0]
    assert isinstance(added_task, TaskQueue)
    assert added_task.requested_by_sub == "sub-testuser"


@pytest.mark.asyncio
async def test_complete_task_publishes_user_event_for_requested_task(mock_db_session):
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        folder_uuid="folder1",
        relative_path="docs/file.pdf",
        metadata_json=ProcessTaskMetadata(
            content_item_id="file-1",
            source_name="documents",
        ).model_dump_json(exclude_none=True),
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        requested_by_sub="sub-testuser",
    )

    with (
        patch.object(svc, "_get_authorized_task", new=AsyncMock(return_value=task)),
        patch.object(svc, "_processing_duration_ms", new=AsyncMock(return_value=42)),
        patch.object(svc, "_update_indexed_content_item", new=AsyncMock()),
        patch(
            "services.task_queue.event_ops.EventOutboxService.enqueue_user_event"
        ) as enqueue_user_event,
    ):
        ok = await svc.complete_task("task-1", "secret-1")

    assert ok is True
    assert task.task_secret is None
    enqueue_user_event.assert_called_once()
    assert enqueue_user_event.call_args.kwargs["kind"] == "file.process.completed"
    assert (
        enqueue_user_event.call_args.kwargs["metadata"]["file_path"]
        == "documents/docs/file.pdf"
    )


@pytest.mark.asyncio
async def test_fail_task_publishes_user_event_only_for_terminal_failure(
    mock_db_session,
):
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        folder_uuid="folder1",
        relative_path="docs/file.pdf",
        metadata_json=ProcessTaskMetadata(
            content_item_id="file-1",
            source_name="documents",
        ).model_dump_json(exclude_none=True),
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        retry_count=3,
        max_retries=3,
        requested_by_sub="sub-testuser",
    )

    with (
        patch.object(svc, "_get_authorized_task", new=AsyncMock(return_value=task)),
        patch.object(svc, "_update_process_content_item", new=AsyncMock()),
        patch(
            "services.task_queue.event_ops.EventOutboxService.enqueue_user_event"
        ) as enqueue_user_event,
    ):
        result = await svc.fail_task("task-1", "secret-1", "boom")

    assert result == TaskFailureResult(requeued=False, retry_count=3)
    assert task.task_secret is None
    enqueue_user_event.assert_called_once()
    assert enqueue_user_event.call_args.kwargs["kind"] == "file.process.failed"


@pytest.mark.asyncio
async def test_get_authorized_task_rejects_correct_secret_for_wrong_worker(
    mock_db_session,
):
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        folder_uuid="folder1",
        relative_path="docs/file.pdf",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        claimed_by="worker-2",
    )
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = task
    svc = TaskQueueService(mock_db_session)

    assert (
        await svc.get_authorized_task("task-1", "secret-1", worker_id="worker-1")
        is None
    )
    assert (
        await svc.get_authorized_task("task-1", "secret-1", worker_id="worker-2")
        is task
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        TaskStatus.PENDING,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.SUPERSEDED,
    ],
)
async def test_abort_task_rejects_non_claimed_task_statuses(
    mock_db_session,
    status,
):
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        folder_uuid="folder1",
        relative_path="docs/file.pdf",
        status=status,
        task_secret="stale-secret",
        claimed_by="worker-1",
    )

    with (
        patch.object(svc, "_get_authorized_task", new=AsyncMock(return_value=task)),
        patch.object(svc, "_update_process_content_item", new=AsyncMock()) as update,
        patch.object(svc, "_append_task_audit_event", new=AsyncMock()) as audit,
    ):
        ok = await svc.abort_task(
            "task-1",
            "stale-secret",
            reason="late abort",
            worker_id="worker-1",
        )

    assert ok is False
    assert task.status == status
    assert task.task_secret == "stale-secret"
    update.assert_not_awaited()
    audit.assert_not_awaited()
    mock_db_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_task_persists_stage_and_mirrors_to_content_item(
    mock_db_session,
):
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        folder_uuid="folder1",
        relative_path="docs/file.pdf",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        claimed_by="worker-1",
    )

    with (
        patch.object(svc, "_get_authorized_task", new=AsyncMock(return_value=task)),
        patch.object(svc, "_update_process_content_item", new=AsyncMock()) as update,
    ):
        ok = await svc.heartbeat_task(
            "task-1", "secret-1", worker_id="worker-1", stage="chunking"
        )

    assert ok is True
    assert task.stage == "chunking"
    assert task.stage_updated_at is not None
    update.assert_awaited_once_with(task, processing_stage="chunking")
    mock_db_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_task_without_stage_skips_content_item_update(mock_db_session):
    svc = TaskQueueService(mock_db_session)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        folder_uuid="folder1",
        relative_path="docs/file.pdf",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        claimed_by="worker-1",
    )

    with (
        patch.object(svc, "_get_authorized_task", new=AsyncMock(return_value=task)),
        patch.object(svc, "_update_process_content_item", new=AsyncMock()) as update,
    ):
        ok = await svc.heartbeat_task("task-1", "secret-1", worker_id="worker-1")

    assert ok is True
    assert task.stage is None
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_task_forwards_processing_config(mock_db_session):
    """Worker complete endpoint forwards optional processing config to task service."""
    request = CompleteTaskRequest(
        task_secret="task-secret",
        processing_config={"do_ocr": False},
    )

    svc = AsyncMock()
    svc.complete_task.return_value = True

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        response = await complete_task(
            "task-id",
            request,
            worker_id="worker-1",
            db=mock_db_session,
        )

    assert response == {"status": "ok"}
    svc.complete_task.assert_awaited_once_with(
        "task-id",
        "task-secret",
        processing_config={"do_ocr": False},
        document_classification=None,
        document_extraction=None,
        worker_id="worker-1",
    )


@pytest.mark.asyncio
async def test_complete_task_returns_404_on_task_secret_auth_failure(mock_db_session):
    request = CompleteTaskRequest(task_secret="wrong-secret")
    svc = AsyncMock()
    svc.complete_task.return_value = False

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await complete_task(
                "task-id",
                request,
                worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_complete_content_enrichment_training_task_forwards_registry_payload(
    mock_db_session,
):
    request = CompleteContentEnrichmentTrainingTaskRequest(
        task_secret="task-secret",
        artifact_path="models/content-enrichment/model-1/adapter",
        metrics={"accuracy": 0.91},
    )
    svc = AsyncMock()
    svc.complete_content_enrichment_training_task.return_value = True

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        response = await complete_content_enrichment_training_task(
            "task-id",
            request,
            worker_id="worker-1",
            db=mock_db_session,
        )

    assert response == {"status": "ok"}
    svc.complete_content_enrichment_training_task.assert_awaited_once_with(
        "task-id",
        "task-secret",
        artifact_path="models/content-enrichment/model-1/adapter",
        metrics={"accuracy": 0.91},
        worker_id="worker-1",
    )


@pytest.mark.asyncio
async def test_complete_content_enrichment_training_task_returns_404_on_auth_failure(
    mock_db_session,
):
    request = CompleteContentEnrichmentTrainingTaskRequest(
        task_secret="wrong-secret",
        artifact_path="models/content-enrichment/model-1/adapter",
    )
    svc = AsyncMock()
    svc.complete_content_enrichment_training_task.return_value = False

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await complete_content_enrichment_training_task(
                "task-id",
                request,
                worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_complete_task_forwards_content_enrichment_payloads(mock_db_session):
    request = CompleteTaskRequest(
        task_secret="task-secret",
        document_classification={"status": "completed", "label": "Permit"},
        document_extraction={"status": "completed", "schema_name": "permit_core"},
    )

    svc = AsyncMock()
    svc.complete_task.return_value = True

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        response = await complete_task(
            "task-id",
            request,
            worker_id="worker-1",
            db=mock_db_session,
        )

    assert response == {"status": "ok"}
    svc.complete_task.assert_awaited_once_with(
        "task-id",
        "task-secret",
        processing_config=None,
        document_classification={"status": "completed", "label": "Permit"},
        document_extraction={"status": "completed", "schema_name": "permit_core"},
        worker_id="worker-1",
    )


@pytest.mark.asyncio
async def test_heartbeat_returns_404_on_task_secret_auth_failure(mock_db_session):
    request = HeartbeatTaskRequest(task_secret="wrong-secret")
    svc = AsyncMock()
    svc.heartbeat_task.return_value = False

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await heartbeat_task(
                "task-id",
                request,
                worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found or invalid secret"


@pytest.mark.asyncio
async def test_heartbeat_forwards_stage_to_service(mock_db_session):
    request = HeartbeatTaskRequest(task_secret="secret-1", stage="chunking")
    svc = AsyncMock()
    svc.heartbeat_task.return_value = True

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        await heartbeat_task(
            "task-id",
            request,
            worker_id="worker-1",
            db=mock_db_session,
        )

    svc.heartbeat_task.assert_awaited_once_with(
        "task-id", "secret-1", worker_id="worker-1", stage="chunking"
    )


@pytest.mark.asyncio
async def test_fail_returns_404_on_task_secret_auth_failure(mock_db_session):
    request = FailTaskRequest(task_secret="wrong-secret", error_message="boom")
    svc = AsyncMock()
    svc.fail_task.return_value = None

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await fail_task(
                "task-id",
                request,
                worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found or invalid secret"


@pytest.mark.asyncio
async def test_claim_task_serializes_typed_task_payload(mock_db_session):
    request = ClaimTaskRequest(capabilities=["document"])
    svc = AsyncMock()
    svc.claim_task.return_value = ClaimedTask(
        task_id="task-id",
        task_type="process",
        content_kind="document",
        content_item_id="file-1",
        folder_uuid="folder-1",
        relative_path="docs/file.pdf",
        metadata=ProcessTaskMetadata(
            content_item_id="file-1",
            modified_time=1.0,
            created_time=1.0,
            size_bytes=5,
        ).model_dump(),
        task_secret="secret-1",
        retry_count=0,
    )

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        response = await claim_task(
            request,
            worker_id="worker-1",
            db=mock_db_session,
        )

    assert response == {
        "task_id": "task-id",
        "task_type": "process",
        "content_kind": "document",
        "content_item_id": "file-1",
        "folder_uuid": "folder-1",
        "relative_path": "docs/file.pdf",
        "metadata": {
            "content_item_id": "file-1",
            "size_bytes": 5,
            "modified_time": 1.0,
            "created_time": 1.0,
            "is_symlink": False,
            "file_extension": None,
            "source_name": None,
            "allowed_viewers": None,
            "denied_viewers": None,
            "processing_config": None,
            "inline_document_source": None,
        },
        "task_secret": "secret-1",
        "retry_count": 0,
    }


@pytest.mark.asyncio
async def test_get_content_enrichment_training_dataset_returns_typed_payload(
    mock_db_session,
):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-task-secret", b"secret-1")],
        }
    )
    svc = AsyncMock()
    svc.get_worker_training_dataset.return_value = (
        ContentEnrichmentWorkerTrainingDataset(
            task_id="task-1",
            training_job_id="job-1",
            registry_model_id="model-1",
            target_kind="classification",
            training_method="lora",
            base_model="fastino/gliner2-multi-v1",
            config_fingerprint="fingerprint-1",
            examples=[
                ContentEnrichmentTrainingExample(
                    content_item_id="file-1",
                    relative_path="docs/invoice.pdf",
                    input="Invoice 42",
                    output={
                        "classifications": [
                            {
                                "task": "document_class",
                                "labels": ["Invoice"],
                                "true_label": "Invoice",
                            }
                        ]
                    },
                    review_status="accepted",
                )
            ],
        )
    )

    with patch(
        "routers.worker.tasks.ContentEnrichmentTrainingService",
        return_value=svc,
    ):
        response = await get_content_enrichment_training_dataset(
            "task-1",
            request=request,
            _worker_id="worker-1",
            db=mock_db_session,
        )

    assert response.task_id == "task-1"
    assert response.examples[0].relative_path == "docs/invoice.pdf"


@pytest.mark.asyncio
async def test_get_content_enrichment_task_source_returns_typed_payload(
    mock_db_session,
):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-task-secret", b"secret-1")],
        }
    )
    svc = AsyncMock()
    svc.get_content_enrichment_task_source.return_value = (
        ContentEnrichmentTaskSourceResponse(
            task_id="task-1",
            content_item_id="file-1",
            relative_path="docs/invoice.pdf",
            current_document_class="Invoice",
            chunks=[
                {
                    "chunk_index": 0,
                    "text": "Invoice 42",
                    "page_numbers": [1],
                    "doc_refs": ["#/pages/1"],
                    "images": [],
                }
            ],
        )
    )

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        response = await get_content_enrichment_task_source(
            "task-1",
            request=request,
            _worker_id="worker-1",
            db=mock_db_session,
        )

    assert response.task_id == "task-1"
    assert response.current_document_class == "Invoice"
    assert response.chunks[0].text == "Invoice 42"


@pytest.mark.asyncio
async def test_get_content_enrichment_task_source_returns_404_on_auth_failure(
    mock_db_session,
):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-task-secret", b"wrong-secret")],
        }
    )
    svc = AsyncMock()
    svc.get_content_enrichment_task_source.return_value = None

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await get_content_enrichment_task_source(
                "task-1",
                request=request,
                _worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found or invalid secret"


@pytest.mark.asyncio
async def test_upload_content_enrichment_training_artifact_stores_file_and_returns_typed_payload(
    mock_db_session,
    temp_data_dir,
):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-task-secret", b"secret-1")],
        }
    )
    upload = UploadFile(filename="../adapter.tar.gz", file=io.BytesIO(b"adapter"))
    svc = AsyncMock()
    svc.get_worker_training_artifact_upload_target.return_value = MagicMock(
        registry_model_id="model-1",
        artifact_path="content-enrichment/model-1/adapter.tar.gz",
        filename="adapter.tar.gz",
    )
    settings = MagicMock()
    settings.MODEL_ARTIFACTS_DIR = str(temp_data_dir / "model-artifacts")
    settings.MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES = 1024

    with (
        patch(
            "routers.worker.tasks.ContentEnrichmentTrainingService",
            return_value=svc,
        ),
        patch("routers.worker.tasks.get_settings", return_value=settings),
    ):
        response = await upload_content_enrichment_training_artifact(
            "task-1",
            request=request,
            file=upload,
            _worker_id="worker-1",
            db=mock_db_session,
        )

    assert isinstance(response, ContentEnrichmentTrainingArtifactUploadResponse)
    assert response.artifact_path == "content-enrichment/model-1/adapter.tar.gz"
    assert (
        temp_data_dir
        / "model-artifacts"
        / "content-enrichment"
        / "model-1"
        / "adapter.tar.gz"
    ).read_bytes() == b"adapter"


@pytest.mark.asyncio
async def test_upload_content_enrichment_training_artifact_returns_404_on_auth_failure(
    mock_db_session,
):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-task-secret", b"wrong-secret")],
        }
    )
    upload = UploadFile(filename="adapter.tar.gz", file=io.BytesIO(b"adapter"))
    svc = AsyncMock()
    svc.get_worker_training_artifact_upload_target.return_value = None

    with patch(
        "routers.worker.tasks.ContentEnrichmentTrainingService",
        return_value=svc,
    ):
        with pytest.raises(HTTPException) as exc:
            await upload_content_enrichment_training_artifact(
                "task-1",
                request=request,
                file=upload,
                _worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found or invalid secret"


@pytest.mark.asyncio
async def test_upload_content_enrichment_training_artifact_returns_clear_500_on_storage_error(
    mock_db_session,
    temp_data_dir,
):
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-task-secret", b"secret-1")],
        }
    )
    upload = UploadFile(filename="adapter.tar.gz", file=io.BytesIO(b"adapter"))
    svc = AsyncMock()
    svc.get_worker_training_artifact_upload_target.return_value = MagicMock(
        registry_model_id="model-1",
        artifact_path="content-enrichment/model-1/adapter.tar.gz",
        filename="adapter.tar.gz",
    )
    settings = MagicMock()
    settings.MODEL_ARTIFACTS_DIR = str(temp_data_dir / "model-artifacts")
    settings.MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES = 1024

    with (
        patch(
            "routers.worker.tasks.ContentEnrichmentTrainingService",
            return_value=svc,
        ),
        patch("routers.worker.tasks.get_settings", return_value=settings),
        patch(
            "pathlib.Path.mkdir",
            side_effect=PermissionError(13, "Permission denied", "/model-artifacts"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await upload_content_enrichment_training_artifact(
                "task-1",
                request=request,
                file=upload,
                _worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 500
    assert "Failed to store model artifact" in exc.value.detail
    assert "MODEL_ARTIFACTS_DIR permissions" in exc.value.detail


@pytest.mark.asyncio
async def test_fail_task_serializes_typed_result(mock_db_session):
    request = FailTaskRequest(task_secret="secret-1", error_message="boom")
    svc = AsyncMock()
    svc.fail_task.return_value = TaskFailureResult(
        requeued=True,
        retry_count=1,
        new_task_secret="secret-2",
    )

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        response = await fail_task(
            "task-id",
            request,
            worker_id="worker-1",
            db=mock_db_session,
        )

    assert response == {
        "requeued": True,
        "retry_count": 1,
        "new_task_secret": "secret-2",
    }


@pytest.mark.asyncio
async def test_abort_returns_404_on_task_secret_auth_failure(mock_db_session):
    request = AbortTaskRequest(task_secret="wrong-secret", reason="stop")
    svc = AsyncMock()
    svc.abort_task.return_value = False

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await abort_task_endpoint(
                "task-id",
                request,
                worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found or invalid secret"


@pytest.mark.asyncio
async def test_superseded_returns_404_on_task_secret_auth_failure(mock_db_session):
    request = CheckSupersededRequest(task_secret="wrong-secret")
    svc = AsyncMock()
    svc.is_superseded.return_value = None

    with patch("routers.worker.tasks.TaskQueueService", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            await check_superseded(
                "task-id",
                request,
                worker_id="worker-1",
                db=mock_db_session,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Task not found or invalid secret"
