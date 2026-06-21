"""Tests for content enrichment training admin routes."""

from unittest.mock import AsyncMock, patch

from auth.dependencies import require_admin
from models.content.enrichment_training import (
    ContentEnrichmentFineTuneJobEntry,
    ContentEnrichmentModelRegistryEntry,
    ContentEnrichmentTrainingDatasetSummary,
    ContentEnrichmentTrainingOverviewResponse,
)
from models.user import User


def _admin_user() -> User:
    return User(username="admin", sub="sub-admin", groups=["admins"])


def _overview() -> ContentEnrichmentTrainingOverviewResponse:
    return ContentEnrichmentTrainingOverviewResponse(
        jobs=[
            ContentEnrichmentFineTuneJobEntry(
                id="job-1",
                registry_model_id="model-1",
                queue_task_id="task-1",
                status="queued",
                target_kind="classification",
                training_method="lora",
                base_model="fastino/gliner2-multi-v1",
                target_name=None,
                config_fingerprint="fingerprint-1",
                dataset_summary=ContentEnrichmentTrainingDatasetSummary(
                    reviewed_example_count=12
                ),
                requested_by="admin",
                requested_by_sub="sub-admin",
                created_at="2026-04-26T18:45:00",
                updated_at="2026-04-26T18:45:00",
            )
        ],
        models=[
            ContentEnrichmentModelRegistryEntry(
                id="model-1",
                target_kind="classification",
                training_method="lora",
                status="training",
                base_model="fastino/gliner2-multi-v1",
                config_fingerprint="fingerprint-1",
                reviewed_example_count=12,
                created_by="admin",
                is_active=False,
                created_at="2026-04-26T18:45:00",
                updated_at="2026-04-26T18:45:00",
            )
        ],
    )


def _queued_job() -> ContentEnrichmentFineTuneJobEntry:
    return _overview().jobs[0]


def test_get_content_enrichment_training_overview_returns_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.get_overview",
            new=AsyncMock(return_value=_overview()),
        ):
            response = test_client.get("/api/content-enrichment-training")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"][0]["id"] == "job-1"
    assert payload["models"][0]["id"] == "model-1"


def test_post_content_enrichment_training_job_queues_request(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.create_job",
            new=AsyncMock(return_value=_queued_job()),
        ) as create_job:
            response = test_client.post(
                "/api/content-enrichment-training/jobs",
                json={"target_kind": "classification", "training_method": "lora"},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["queue_task_id"] == "task-1"
    assert create_job.await_args.kwargs["requested_by"] == "admin"
    assert create_job.await_args.kwargs["requested_by_sub"] == "sub-admin"


def test_post_content_enrichment_training_job_returns_validation_error(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.create_job",
            new=AsyncMock(
                side_effect=ValueError(
                    "No reviewed classification examples are available for training"
                )
            ),
        ):
            response = test_client.post(
                "/api/content-enrichment-training/jobs",
                json={
                    "target_kind": "classification",
                    "training_method": "lora",
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "No reviewed classification examples are available for training"
    )


def test_post_content_enrichment_training_job_retry_returns_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.retry_job",
            new=AsyncMock(return_value=_queued_job()),
        ) as retry_job:
            response = test_client.post(
                "/api/content-enrichment-training/jobs/job-1/retry"
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["id"] == "job-1"
    assert retry_job.await_args.kwargs["requested_by"] == "admin"
    assert retry_job.await_args.kwargs["requested_by_sub"] == "sub-admin"


def test_post_content_enrichment_training_job_cancel_returns_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.cancel_job",
            new=AsyncMock(
                return_value=_queued_job().model_copy(update={"status": "failed"})
            ),
        ) as cancel_job:
            response = test_client.post(
                "/api/content-enrichment-training/jobs/job-1/cancel"
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert cancel_job.await_args.kwargs["cancelled_by"] == "admin"


def test_post_content_enrichment_training_model_promote_returns_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.promote_model",
            new=AsyncMock(
                return_value={
                    "model_id": "model-1",
                    "target_kind": "classification",
                    "target_name": None,
                    "setting_key": "document_classification_model",
                    "setting_value": "registry:model-1",
                    "stale_file_count": 9,
                    "newly_stale_file_count": 4,
                }
            ),
        ) as promote_model:
            response = test_client.post(
                "/api/content-enrichment-training/models/model-1/promote"
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["setting_value"] == "registry:model-1"
    assert response.json()["stale_file_count"] == 9
    assert promote_model.await_args.kwargs["updated_by"] == "admin"


def test_post_content_enrichment_training_model_promote_returns_validation_error(
    test_client,
):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.promote_model",
            new=AsyncMock(side_effect=ValueError("Only ready models can be promoted")),
        ):
            response = test_client.post(
                "/api/content-enrichment-training/models/model-2/promote"
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Only ready models can be promoted"


def test_post_content_enrichment_training_model_archive_returns_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_training.ContentEnrichmentTrainingService.archive_model",
            new=AsyncMock(
                return_value=_overview()
                .models[0]
                .model_copy(update={"status": "archived"})
            ),
        ):
            response = test_client.post(
                "/api/content-enrichment-training/models/model-1/archive"
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
