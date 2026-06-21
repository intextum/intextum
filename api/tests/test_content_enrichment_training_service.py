"""Tests for content enrichment fine-tune job service."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.ai_settings import EffectiveAiSettings
from models.content.enrichment_training import (
    CreateContentEnrichmentFineTuneJobRequest,
)
from models.sqlalchemy_models import (
    AppSetting,
    ContentEnrichmentFineTuneJob,
    ContentEnrichmentModelRegistry,
    ContentItemEnrichmentState,
    TaskQueue,
)
from services.content_enrichment_training import (
    ContentEnrichmentTrainingService,
)
from services.content_enrichment_training.refs import (
    content_enrichment_registry_model_ref,
)


def _effective_settings() -> EffectiveAiSettings:
    return EffectiveAiSettings.model_validate(
        {
            "chat_model": "test-chat-model",
            "chat_system_prompt": "You are a helpful assistant.",
            "chat_tool_prompt": "Use the available tools when needed.",
            "chat_search_limit": 10,
            "chat_document_max_chars": 30000,
            "picture_description_model": "test-picture-model",
            "picture_description_prompt": "Describe the image accurately.",
            "document_classification_enabled": True,
            "document_classification_model": "fastino/gliner2-multi-v1",
            "document_classification_labels": [
                {"name": "Permit", "description": "Permit documents", "aliases": []},
                {"name": "Invoice", "description": "Invoice documents", "aliases": []},
            ],
            "document_extraction_enabled": True,
            "document_extraction_model": "fastino/gliner2-multi-v1",
            "document_extraction_schemas": [
                {
                    "name": "permit_core",
                    "document_class": "Permit",
                    "description": "Permit fields",
                    "fields": [
                        {
                            "name": "file_number",
                            "dtype": "str",
                            "description": "Permit file number",
                            "required": False,
                        }
                    ],
                }
            ],
            "document_extraction_max_chars": 12000,
        }
    )


def _db_with_counts(*counts: int) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    execute_results = []
    for count in counts:
        result = MagicMock()
        result.scalar_one.return_value = count
        execute_results.append(result)
    db.execute.side_effect = execute_results

    async def _refresh(row):
        if isinstance(row, ContentEnrichmentFineTuneJob):
            now = datetime.fromisoformat("2026-04-26T18:45:00")
            row.created_at = now
            row.updated_at = now

    db.refresh = AsyncMock(side_effect=_refresh)
    return db


@pytest.mark.asyncio
async def test_create_job_queues_classification_training_and_registry_entry():
    db = _db_with_counts(17)
    settings = _effective_settings()

    with (
        patch(
            "services.content_enrichment_training.service.AiSettingsService.get_effective_settings",
            new=AsyncMock(return_value=settings),
        ),
        patch(
            "services.content_enrichment_training.service.TaskQueueService.enqueue_content_enrichment_training",
            new=AsyncMock(return_value="task-123"),
        ) as enqueue_training,
    ):
        job = await ContentEnrichmentTrainingService(db).create_job(
            CreateContentEnrichmentFineTuneJobRequest(target_kind="classification"),
            requested_by="admin",
            requested_by_sub="sub-admin",
        )

    assert job.status == "queued"
    assert job.queue_task_id == "task-123"
    assert job.base_model == "fastino/gliner2-multi-v1"
    assert job.target_kind == "classification"
    assert job.dataset_summary.reviewed_example_count == 17
    assert db.add.call_count == 2
    enqueue_training.assert_awaited_once()
    assert enqueue_training.await_args.kwargs["target_kind"] == "classification"
    assert enqueue_training.await_args.kwargs["reviewed_example_count"] == 17


@pytest.mark.asyncio
async def test_retry_job_requeues_failed_scope():
    db = AsyncMock()
    failed_job = SimpleNamespace(
        id="job-1",
        status="failed",
        target_kind="classification",
        training_method="lora",
        target_name=None,
        base_model="fastino/gliner2-multi-v1",
    )
    service = ContentEnrichmentTrainingService(db)

    with (
        patch.object(
            service,
            "_load_job_row",
            new=AsyncMock(return_value=failed_job),
        ),
        patch.object(
            service,
            "create_job",
            new=AsyncMock(return_value=SimpleNamespace(id="job-2", status="queued")),
        ) as create_job,
    ):
        result = await service.retry_job(
            "job-1",
            requested_by="admin",
            requested_by_sub="sub-admin",
        )

    assert result.id == "job-2"
    request = create_job.await_args.args[0]
    assert request.target_kind == "classification"
    assert request.training_method == "lora"
    assert request.base_model == "fastino/gliner2-multi-v1"
    assert create_job.await_args.kwargs["requested_by"] == "admin"
    assert create_job.await_args.kwargs["requested_by_sub"] == "sub-admin"


@pytest.mark.asyncio
async def test_cancel_job_marks_queue_job_and_model_failed():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    now = datetime.fromisoformat("2026-04-27T09:30:00")
    queued_task = TaskQueue(
        id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        folder_uuid="training",
        relative_path="content-enrichment/job-1",
        status="PENDING",
        task_secret="secret-1",
    )
    job_row = ContentEnrichmentFineTuneJob(
        id="job-1",
        registry_model_id="model-1",
        queue_task_id="task-1",
        status="queued",
        target_kind="classification",
        training_method="lora",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        dataset_summary_json={"reviewed_example_count": 12},
        created_at=now,
        updated_at=now,
    )
    model_row = ContentEnrichmentModelRegistry(
        id="model-1",
        target_kind="classification",
        training_method="lora",
        status="training",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        reviewed_example_count=12,
        created_at=now,
        updated_at=now,
    )
    service = ContentEnrichmentTrainingService(db)

    with (
        patch.object(service, "_load_job_row", new=AsyncMock(return_value=job_row)),
        patch.object(
            service,
            "_load_registry_model_row",
            new=AsyncMock(return_value=model_row),
        ),
        patch.object(
            service,
            "_load_queue_task_row",
            new=AsyncMock(return_value=queued_task),
        ),
    ):
        result = await service.cancel_job("job-1", cancelled_by="admin")

    assert result.status == "failed"
    assert queued_task.status == "FAILED"
    assert queued_task.task_secret is None
    assert job_row.error_message == "Cancelled by admin"
    assert model_row.status == "failed"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(job_row)


@pytest.mark.asyncio
async def test_archive_model_rejects_active_registry_entry():
    db = AsyncMock()
    model_row = ContentEnrichmentModelRegistry(
        id="model-1",
        target_kind="classification",
        training_method="lora",
        status="ready",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        reviewed_example_count=12,
    )
    service = ContentEnrichmentTrainingService(db)

    with (
        patch.object(
            service,
            "_load_registry_model_row",
            new=AsyncMock(return_value=model_row),
        ),
        patch.object(
            service,
            "_active_model_ids",
            new=AsyncMock(return_value={"model-1"}),
        ),
    ):
        with pytest.raises(ValueError, match="Active models cannot be archived"):
            await service.archive_model("model-1")


@pytest.mark.asyncio
async def test_archive_model_marks_inactive_failed_model_archived():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    now = datetime.fromisoformat("2026-04-27T09:30:00")
    model_row = ContentEnrichmentModelRegistry(
        id="model-1",
        target_kind="classification",
        training_method="lora",
        status="failed",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        reviewed_example_count=12,
        created_at=now,
        updated_at=now,
    )
    service = ContentEnrichmentTrainingService(db)

    with (
        patch.object(
            service,
            "_load_registry_model_row",
            new=AsyncMock(return_value=model_row),
        ),
        patch.object(
            service,
            "_active_model_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        result = await service.archive_model("model-1")

    assert result.status == "archived"
    assert model_row.status == "archived"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(model_row)


@pytest.mark.asyncio
async def test_delete_job_removes_failed_job_and_placeholder_registry_model():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    now = datetime.fromisoformat("2026-04-27T09:30:00")
    queue_task = TaskQueue(
        id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        folder_uuid="training",
        relative_path="content-enrichment/job-1",
        status="FAILED",
    )
    job_row = ContentEnrichmentFineTuneJob(
        id="job-1",
        registry_model_id="model-1",
        queue_task_id="task-1",
        status="failed",
        target_kind="classification",
        training_method="lora",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        dataset_summary_json={"reviewed_example_count": 8},
        created_at=now,
        updated_at=now,
    )
    model_row = ContentEnrichmentModelRegistry(
        id="model-1",
        target_kind="classification",
        training_method="lora",
        status="failed",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        reviewed_example_count=8,
        created_at=now,
        updated_at=now,
    )
    service = ContentEnrichmentTrainingService(db)

    with (
        patch.object(service, "_load_job_row", new=AsyncMock(return_value=job_row)),
        patch.object(
            service,
            "_load_queue_task_row",
            new=AsyncMock(return_value=queue_task),
        ),
        patch.object(
            service,
            "_load_registry_model_row",
            new=AsyncMock(return_value=model_row),
        ),
        patch.object(
            service,
            "_active_model_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        await service.delete_job("job-1")

    deleted = [call.args[0] for call in db.delete.await_args_list]
    assert queue_task in deleted
    assert model_row in deleted
    # Registry deletion cascades to the job row via FK ON DELETE CASCADE.
    assert job_row not in deleted
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_job_rejects_active_jobs():
    db = AsyncMock()
    now = datetime.fromisoformat("2026-04-27T09:30:00")
    job_row = ContentEnrichmentFineTuneJob(
        id="job-1",
        registry_model_id="model-1",
        status="queued",
        target_kind="classification",
        training_method="lora",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        dataset_summary_json={},
        created_at=now,
        updated_at=now,
    )
    service = ContentEnrichmentTrainingService(db)

    with patch.object(service, "_load_job_row", new=AsyncMock(return_value=job_row)):
        with pytest.raises(ValueError, match="Only failed"):
            await service.delete_job("job-1")


@pytest.mark.asyncio
async def test_delete_job_keeps_registry_when_model_is_active():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    now = datetime.fromisoformat("2026-04-27T09:30:00")
    job_row = ContentEnrichmentFineTuneJob(
        id="job-1",
        registry_model_id="model-1",
        queue_task_id=None,
        status="failed",
        target_kind="classification",
        training_method="lora",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        dataset_summary_json={},
        created_at=now,
        updated_at=now,
    )
    model_row = ContentEnrichmentModelRegistry(
        id="model-1",
        target_kind="classification",
        training_method="lora",
        status="ready",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fingerprint-1",
        reviewed_example_count=8,
        created_at=now,
        updated_at=now,
    )
    service = ContentEnrichmentTrainingService(db)

    with (
        patch.object(service, "_load_job_row", new=AsyncMock(return_value=job_row)),
        patch.object(
            service,
            "_load_queue_task_row",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            service,
            "_load_registry_model_row",
            new=AsyncMock(return_value=model_row),
        ),
        patch.object(
            service,
            "_active_model_ids",
            new=AsyncMock(return_value={"model-1"}),
        ),
    ):
        await service.delete_job("job-1")

    deleted = [call.args[0] for call in db.delete.await_args_list]
    assert job_row in deleted
    assert model_row not in deleted
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_job_rejects_empty_reviewed_classification_dataset():
    db = _db_with_counts(0)
    settings = _effective_settings()

    with patch(
        "services.content_enrichment_training.service.AiSettingsService.get_effective_settings",
        new=AsyncMock(return_value=settings),
    ):
        with pytest.raises(
            ValueError,
            match="No reviewed classification examples are available for training",
        ):
            await ContentEnrichmentTrainingService(db).create_job(
                CreateContentEnrichmentFineTuneJobRequest(target_kind="classification"),
                requested_by="admin",
                requested_by_sub="sub-admin",
            )


@pytest.mark.asyncio
async def test_get_overview_returns_jobs_and_models():
    db = AsyncMock()
    jobs_result = MagicMock()
    jobs_result.scalars.return_value.all.return_value = [
        SimpleNamespace(
            id="job-1",
            registry_model_id="model-1",
            queue_task_id="task-1",
            status="queued",
            target_kind="classification",
            training_method="lora",
            base_model="fastino/gliner2-multi-v1",
            target_name=None,
            config_fingerprint="fingerprint-1",
            dataset_summary_json={"reviewed_example_count": 12},
            error_message=None,
            requested_by="admin",
            requested_by_sub="sub-admin",
            created_at=datetime.fromisoformat("2026-04-26T18:45:00"),
            updated_at=datetime.fromisoformat("2026-04-26T18:45:00"),
            started_at=None,
            completed_at=None,
        )
    ]
    models_result = MagicMock()
    models_result.scalars.return_value.all.return_value = [
        SimpleNamespace(
            id="model-1",
            target_kind="classification",
            training_method="lora",
            status="training",
            base_model="fastino/gliner2-multi-v1",
            target_name=None,
            config_fingerprint="fingerprint-1",
            reviewed_example_count=12,
            artifact_path=None,
            metrics_json=None,
            created_by="admin",
            created_at=datetime.fromisoformat("2026-04-26T18:45:00"),
            updated_at=datetime.fromisoformat("2026-04-26T18:45:00"),
        )
    ]
    classification_count_result = MagicMock()
    classification_count_result.scalar_one.return_value = 14
    db.execute.side_effect = [
        classification_count_result,
        jobs_result,
        models_result,
    ]

    with patch(
        "services.content_enrichment_training.service.AiSettingsService.get_effective_settings",
        new=AsyncMock(
            return_value=_effective_settings().model_copy(
                update={
                    "document_classification_model": content_enrichment_registry_model_ref(
                        "model-1"
                    )
                }
            )
        ),
    ):
        overview = await ContentEnrichmentTrainingService(db).get_overview()

    assert overview.jobs[0].id == "job-1"
    assert overview.jobs[0].dataset_summary.reviewed_example_count == 12
    assert overview.models[0].id == "model-1"
    assert overview.models[0].status == "training"
    assert overview.models[0].is_active is True
    assert overview.current_examples.classification == 14


@pytest.mark.asyncio
async def test_resolved_training_base_model_uses_promoted_registry_base_model():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        id="model-1",
        base_model="fastino/gliner2-base-v1",
    )
    db.execute.return_value = result
    settings = _effective_settings().model_copy(
        update={
            "document_classification_model": content_enrichment_registry_model_ref(
                "model-1"
            )
        }
    )

    base_model = await ContentEnrichmentTrainingService(
        db
    )._resolved_training_base_model(
        CreateContentEnrichmentFineTuneJobRequest(target_kind="classification"),
        settings,
    )

    assert base_model == "fastino/gliner2-base-v1"


@pytest.mark.asyncio
async def test_get_worker_training_dataset_builds_reviewed_classification_examples():
    db = AsyncMock()
    task_row = SimpleNamespace(
        id="task-1",
        status="CLAIMED",
        task_type="train_content_enrichment_model",
        metadata_json="""
        {
          "training_job_id": "job-1",
          "registry_model_id": "model-1",
          "target_kind": "classification",
          "training_method": "lora",
          "base_model": "fastino/gliner2-multi-v1",
          "config_fingerprint": "fingerprint-1",
          "config_snapshot": {
            "document_classification_labels": [
              {"name": "Invoice", "description": "Invoice documents"},
              {"name": "Permit", "description": "Permit documents"}
            ]
          }
        }
        """,
    )
    records_result = MagicMock()
    records_result.scalars.return_value.all.return_value = [
        SimpleNamespace(
            content_item_id="file-1",
            relative_path="docs/invoice.pdf",
            enrichment_state=ContentItemEnrichmentState(
                content_item_id="file-1",
                classification_system_label="Invoice",
                classification_effective_label="Invoice",
                classification_review_status="accepted",
                classification_reviewed_by="Reviewer",
                classification_reviewed_at=datetime.fromisoformat(
                    "2026-04-26T18:45:00"
                ),
            ),
        )
    ]
    chunks_result = MagicMock()
    chunks_result.all.return_value = [
        ("file-1", "Invoice 42", []),
        ("file-1", "Customer ACME", []),
    ]
    db.execute.side_effect = [records_result, chunks_result]

    with patch.object(
        ContentEnrichmentTrainingService,
        "_load_authorized_training_task",
        new=AsyncMock(return_value=task_row),
    ):
        dataset = await ContentEnrichmentTrainingService(
            db
        ).get_worker_training_dataset(
            "task-1",
            "secret-1",
        )

    assert dataset is not None
    assert dataset.training_job_id == "job-1"
    assert len(dataset.examples) == 1
    assert dataset.examples[0].input == "Invoice 42\n\nCustomer ACME"
    assert dataset.examples[0].output == {
        "classifications": [
            {
                "task": "document_class",
                "labels": ["Invoice", "Permit"],
                "true_label": "Invoice",
            }
        ]
    }


@pytest.mark.asyncio
async def test_get_worker_training_artifact_upload_target_normalizes_filename():
    db = AsyncMock()
    task_row = SimpleNamespace(
        id="task-1",
        status="CLAIMED",
        task_type="train_content_enrichment_model",
        metadata_json='{"registry_model_id": "model-1"}',
    )

    with patch.object(
        ContentEnrichmentTrainingService,
        "_load_authorized_training_task",
        new=AsyncMock(return_value=task_row),
    ):
        target = await ContentEnrichmentTrainingService(
            db
        ).get_worker_training_artifact_upload_target(
            "task-1",
            "secret-1",
            filename="../adapter.tar.gz",
        )

    assert target is not None
    assert target.registry_model_id == "model-1"
    assert target.filename == "adapter.tar.gz"
    assert target.artifact_path == "content-enrichment/model-1/adapter.tar.gz"


@pytest.mark.asyncio
async def test_promote_model_updates_runtime_setting():
    db = AsyncMock()
    db.add = MagicMock()
    model_result = MagicMock()
    model_result.scalar_one_or_none.return_value = SimpleNamespace(
        id="model-1",
        target_kind="classification",
        target_name=None,
        status="ready",
        artifact_path="content-enrichment/model-1/adapter.tar.gz",
    )
    setting_result = MagicMock()
    setting_result.scalar_one_or_none.return_value = None
    db.execute.side_effect = [model_result, setting_result]

    service = ContentEnrichmentTrainingService(db)
    with (
        patch(
            "services.content_enrichment_training.service.AiSettingsService.get_effective_settings",
            new=AsyncMock(return_value=_effective_settings()),
        ),
        patch.object(
            service,
            "_stale_file_count_for_settings",
            new=AsyncMock(side_effect=[3, 11]),
        ),
    ):
        response = await service.promote_model(
            "model-1",
            updated_by="admin",
        )

    assert response.model_id == "model-1"
    assert response.setting_key == "document_classification_model"
    assert response.setting_value == "registry:model-1"
    assert response.stale_file_count == 11
    assert response.newly_stale_file_count == 8
    db.add.assert_called_once()
    added_row = db.add.call_args.args[0]
    assert isinstance(added_row, AppSetting)
    assert added_row.key == "document_classification_model"
    assert added_row.value_json == "registry:model-1"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_worker_registry_model_requires_ready_artifact():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        id="model-1",
        target_kind="classification",
        training_method="lora",
        status="ready",
        base_model="fastino/gliner2-multi-v1",
        target_name=None,
        config_fingerprint="fp-1",
        artifact_path="content-enrichment/model-1/adapter.tar.gz",
    )
    db.execute.return_value = result

    model = await ContentEnrichmentTrainingService(db).get_worker_registry_model(
        "model-1"
    )

    assert model is not None
    assert model.id == "model-1"
    assert model.artifact_path == "content-enrichment/model-1/adapter.tar.gz"
