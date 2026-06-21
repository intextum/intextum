"""Tests for enrichment lifecycle metadata in task completion."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.ai_settings import EffectiveAiSettings
from models.enums import TaskStatus
from models.sqlalchemy_models import (
    ContentItemEnrichmentState,
    IndexedContentItem,
    TaskQueue,
)
from services.ai_settings import (
    AiSettingsService,
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
)
from services.task_queue import TaskQueueService


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_complete_task_attaches_enrichment_config_fingerprints(mock_get_settings):
    db = AsyncMock()
    db.add = MagicMock()
    svc = TaskQueueService(db)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        folder_uuid="folder-documents",
        relative_path="invoice.pdf",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        content_item_id="file-1",
        created_at=_utc(2026, 4, 25, 10),
        updated_at=_utc(2026, 4, 25, 10),
    )
    settings = EffectiveAiSettings.model_validate(
        {
            **AiSettingsService._base_defaults().model_dump(mode="json"),
            "document_classification_enabled": True,
            "document_classification_labels": [
                {
                    "name": "Invoice",
                    "description": "Billing document",
                    "aliases": ["Rechnung"],
                }
            ],
            "document_extraction_enabled": True,
            "document_extraction_schemas": [
                {
                    "name": "invoice_fields",
                    "document_class": "Invoice",
                    "description": "Extract invoice fields",
                    "fields": [
                        {
                            "name": "invoice_number",
                            "dtype": "str",
                            "description": "Invoice number",
                            "required": True,
                        },
                        {
                            "name": "labels",
                            "dtype": "list",
                            "description": "Routing labels",
                            "required": False,
                        },
                    ],
                }
            ],
        },
    )

    record = IndexedContentItem(
        content_item_id="file-1",
        folder_uuid="folder-documents",
        relative_path="invoice.pdf",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=42,
    )
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = record
    db.execute.return_value = execute_result

    with (
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(
            TaskQueueService,
            "_processing_duration_ms",
            new=AsyncMock(return_value=123),
        ),
        patch.object(
            TaskQueueService,
            "_update_indexed_content_item",
            new=AsyncMock(),
        ) as update_indexed_file,
        patch.object(
            TaskQueueService,
            "_append_task_audit_event",
            new=AsyncMock(),
        ) as append_audit,
        patch.object(
            TaskQueueService,
            "_enqueue_task_event",
            new=AsyncMock(),
        ),
        patch.object(
            AiSettingsService,
            "get_effective_settings",
            new=AsyncMock(return_value=settings),
        ),
    ):
        ok = await svc.complete_task(
            "task-1",
            "secret-1",
            document_classification={"status": "completed", "label": "Invoice"},
            document_extraction={
                "status": "completed",
                "schema_name": "invoice_fields",
                "document_class": "Invoice",
                "fields": {
                    "invoice_number": {
                        "value": "RE-42",
                        "evidence": [{"doc_refs": ["#/texts/1"]}],
                    },
                    "labels": {
                        "value": ["urgent", "paid"],
                        "item_evidence": [
                            [{"doc_refs": ["#/texts/2"]}],
                            [{"doc_refs": ["#/texts/3"]}],
                        ],
                    },
                },
            },
        )

    assert ok is True
    update_indexed_file.assert_awaited_once()
    assert record.enrichment_state is not None
    assert (
        record.enrichment_state.classification_config_fingerprint
        == document_classification_config_fingerprint(settings)
    )
    assert (
        record.enrichment_state.extraction_config_fingerprint
        == document_extraction_config_fingerprint(settings)
    )
    assert record.enrichment_state.extraction_fields_json["labels"][
        "item_evidence"
    ] == [[{"doc_refs": ["#/texts/2"]}], [{"doc_refs": ["#/texts/3"]}]]
    assert record.enrichment_state.extraction_fields_json["labels"]["evidence"] == [
        {"doc_refs": ["#/texts/2"]},
        {"doc_refs": ["#/texts/3"]},
    ]
    append_audit.assert_awaited_once()
    assert (
        append_audit.await_args.kwargs["event_type"] == "content.processing.completed"
    )


@pytest.mark.asyncio
async def test_complete_content_enrichment_training_task_promotes_registry_entry():
    db = AsyncMock()
    db.add = MagicMock()
    svc = TaskQueueService(db)
    task = TaskQueue(
        id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        folder_uuid="__system__",
        relative_path="content-enrichment-training/job-1",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        metadata_json=(
            '{"training_job_id":"job-1","registry_model_id":"model-1",'
            '"target_kind":"classification","training_method":"lora",'
            '"base_model":"fastino/gliner2-multi-v1","config_fingerprint":"fp"}'
        ),
    )

    with (
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(
            TaskQueueService,
            "_update_training_job_status",
            new=AsyncMock(),
        ) as update_training_job_status,
    ):
        ok = await svc.complete_content_enrichment_training_task(
            "task-1",
            "secret-1",
            artifact_path="models/content-enrichment/model-1/adapter",
            metrics={"accuracy": 0.91},
        )

    assert ok is True
    assert task.status == TaskStatus.COMPLETED
    update_training_job_status.assert_awaited_once()
    assert update_training_job_status.await_args.kwargs["job_status"] == "completed"
    assert update_training_job_status.await_args.kwargs["model_status"] == "ready"
    assert (
        update_training_job_status.await_args.kwargs["artifact_path"]
        == "models/content-enrichment/model-1/adapter"
    )


@pytest.mark.asyncio
async def test_claim_task_marks_training_job_running():
    db = AsyncMock()
    db.add = MagicMock()
    task = TaskQueue(
        id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        folder_uuid="__system__",
        relative_path="content-enrichment-training/job-1",
        status=TaskStatus.PENDING,
        task_secret="secret-1",
        content_item_id="model-1",
        retry_count=0,
        metadata_json=(
            '{"training_job_id":"job-1","registry_model_id":"model-1",'
            '"target_kind":"classification","training_method":"lora",'
            '"base_model":"fastino/gliner2-multi-v1","config_fingerprint":"fp"}'
        ),
    )
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = task
    db.execute.return_value = execute_result
    svc = TaskQueueService(db)

    with patch.object(
        TaskQueueService,
        "_update_training_job_status",
        new=AsyncMock(),
    ) as update_training_job_status:
        claimed = await svc.claim_task("worker-1", ["training"])

    assert claimed is not None
    assert claimed.task_type == "train_content_enrichment_model"
    assert claimed.content_kind == "training"
    assert claimed.metadata["training_job_id"] == "job-1"
    assert task.status == TaskStatus.CLAIMED
    update_training_job_status.assert_awaited_once()
    assert update_training_job_status.await_args.kwargs["job_status"] == "running"
    assert update_training_job_status.await_args.kwargs["model_status"] == "training"


@pytest.mark.asyncio
async def test_get_content_enrichment_task_source_returns_chunks_and_effective_class():
    db = AsyncMock()
    db.add = MagicMock()
    svc = TaskQueueService(db)
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_kind="document",
        folder_uuid="folder-1",
        relative_path="docs/invoice.pdf",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        content_item_id="file-1",
        metadata_json='{"content_item_id":"file-1","processing_config":{"enrichment_only":true}}',
    )
    record = IndexedContentItem(
        content_item_id="file-1",
        folder_uuid="folder-1",
        relative_path="docs/invoice.pdf",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=42,
    )
    record.enrichment_state = ContentItemEnrichmentState(
        content_item_id="file-1",
        classification_system_label="Invoice",
        classification_effective_label="Invoice",
    )
    chunk_rows = [
        (0, "Invoice 42", [1], ["#/pages/1"], [], ["Invoice header"]),
        (1, "Total due", [1], [], [], []),
    ]

    with (
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(
            svc.db,
            "execute",
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=record)),
                MagicMock(all=MagicMock(return_value=chunk_rows)),
            ],
        ),
    ):
        source = await svc.get_content_enrichment_task_source("task-1", "secret-1")

    assert source is not None
    assert source.content_item_id == "file-1"
    assert source.current_document_class == "Invoice"
    assert [chunk.text for chunk in source.chunks] == ["Invoice 42", "Total due"]
    assert source.chunks[0].page_numbers == [1]
    assert source.chunks[0].headings == ["Invoice header"]
    assert source.chunks[1].headings == []


@pytest.mark.asyncio
async def test_fail_task_marks_training_job_failed_without_file_event():
    db = AsyncMock()
    db.add = MagicMock()
    svc = TaskQueueService(db)
    task = TaskQueue(
        id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        folder_uuid="__system__",
        relative_path="content-enrichment-training/job-1",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        retry_count=1,
        max_retries=1,
        metadata_json=(
            '{"training_job_id":"job-1","registry_model_id":"model-1",'
            '"target_kind":"classification","training_method":"lora",'
            '"base_model":"fastino/gliner2-multi-v1","config_fingerprint":"fp"}'
        ),
    )

    with (
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(
            TaskQueueService,
            "_update_training_job_status",
            new=AsyncMock(),
        ) as update_training_job_status,
        patch.object(
            TaskQueueService,
            "_enqueue_task_event",
            new=AsyncMock(),
        ) as enqueue_task_event,
    ):
        result = await svc.fail_task("task-1", "secret-1", "boom")

    assert result.requeued is False
    update_training_job_status.assert_awaited_once()
    assert update_training_job_status.await_args.kwargs["job_status"] == "failed"
    enqueue_task_event.assert_not_awaited()
