"""Tests for worker management service helpers."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.sqlalchemy_models import TaskQueue, Worker
from services.worker import WorkerService, _config_from_json, _config_to_json


def test_worker_config_json_helpers_round_trip_and_default_empty_config():
    assert _config_from_json(None) == {}
    assert _config_from_json("") == {}
    assert _config_from_json("{not-json") == {}
    assert _config_from_json('["not", "an", "object"]') == {}

    config = {"runtime_profile": "macos-mps", "capabilities": ["document"]}
    assert _config_from_json(_config_to_json(config)) == config


def test_worker_response_returns_saved_runtime_metadata():
    metadata = {
        "runtime_profile": "macos-mps",
        "classification_device": "mps",
        "capabilities": ["document"],
    }
    worker = Worker(
        id="worker-1",
        name="Host worker",
        description="MPS host",
        created_at=datetime(2026, 5, 9, 5, 0, 0),
        updated_at=datetime(2026, 5, 9, 5, 1, 0),
        last_seen=datetime(2026, 5, 9, 5, 2, 0),
        status="active",
        config=json.dumps(metadata),
    )

    response = WorkerService._model_to_response(worker)

    assert response.config == metadata
    assert response.status == "active"
    assert response.created_at == "2026-05-09T05:00:00+00:00"
    assert response.updated_at == "2026-05-09T05:01:00+00:00"
    assert response.last_seen == "2026-05-09T05:02:00+00:00"


@pytest.mark.asyncio
async def test_list_queue_tasks_returns_admin_summary():
    db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_kind="document",
        content_item_id="content-1",
        folder_uuid="folder-1",
        relative_path="docs/file.pdf",
        status="CLAIMED",
        stage="chunking",
        requested_by_sub="sub:user",
        claimed_by="worker-1",
        claimed_at=datetime(2026, 5, 9, 6, 0, 0),
        retry_count=1,
        max_retries=3,
        error_message=None,
        created_at=datetime(2026, 5, 9, 5, 55, 0),
        updated_at=datetime(2026, 5, 9, 6, 1, 0),
    )
    task_scalars = MagicMock()
    task_scalars.all.return_value = [task]
    task_result = MagicMock()
    task_result.scalars.return_value = task_scalars
    db.execute.side_effect = [count_result, task_result]

    tasks, total = await WorkerService(db).list_queue_tasks(active_only=True)

    assert total == 1
    assert tasks[0].id == "task-1"
    assert tasks[0].relative_path == "docs/file.pdf"
    assert tasks[0].status == "CLAIMED"
    assert tasks[0].stage == "chunking"
    assert tasks[0].claimed_by == "worker-1"
    assert tasks[0].claimed_at == "2026-05-09T06:00:00+00:00"
    assert tasks[0].updated_at == "2026-05-09T06:01:00+00:00"
    assert tasks[0].stale_after_seconds == 1800
    assert tasks[0].claim_age_seconds is not None
    assert tasks[0].retry_count == 1


@pytest.mark.asyncio
async def test_cleanup_stale_tasks_uses_task_queue_cleanup():
    db = AsyncMock()
    task_queue_service = MagicMock()
    task_queue_service.cleanup_stale_claims_detailed = AsyncMock(
        return_value={"total": 2, "requeued": 1, "failed": 1}
    )

    with patch("services.worker.TaskQueueService", return_value=task_queue_service):
        result = await WorkerService(db).cleanup_stale_tasks()

    assert result == {"total": 2, "requeued": 1, "failed": 1}
    task_queue_service.cleanup_stale_claims_detailed.assert_awaited_once()
