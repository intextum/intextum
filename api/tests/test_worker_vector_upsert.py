"""Tests for worker vector upsert endpoint behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from auth.worker_auth import require_worker_token
from database import get_db
from models.enums import TaskStatus
from models.vector import VectorChunkUpsert, VectorSearchHit
from services.vector_dimensions import VectorDimensionMismatchError

_TASK_SECRET = "test-task-secret"
_TASK_SECRET_HEADER = {"X-Task-Id": "task-1", "X-Task-Secret": _TASK_SECRET}


def _db_result(*, one=None, all_values=None):
    result = SimpleNamespace()
    result.scalar_one_or_none = lambda: one
    result.scalars = lambda: SimpleNamespace(all=lambda: list(all_values or []))
    return result


def _embedding_response(*embeddings):
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=list(embedding))
            for index, embedding in enumerate(embeddings)
        ]
    )


def test_vector_upsert_uses_claimed_task_content_item_for_chunks(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    result = SimpleNamespace()
    result.scalars = lambda: SimpleNamespace(all=lambda: ["23bfe864fab4c490"])
    mock_db.execute.return_value = result

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ) as mock_get_folder,
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        task_secret=_TASK_SECRET,
                        content_item_id="23bfe864fab4c490",
                        folder_uuid="folder-1",
                        relative_path="docs/report.txt",
                    )
                ),
            ) as mock_authorize_task,
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "docs/report.txt",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        },
                        {
                            "id": "chunk-2",
                            "vector": [0.3, 0.4],
                            "payload": {
                                "file_path": "docs/report.txt",
                                "text": "Second",
                                "chunk_index": 1,
                                "images": ["page-1.png"],
                                "index_version": "v1",
                            },
                        },
                        {
                            "id": "chunk-3",
                            "vector": [0.5, 0.6],
                            "payload": {
                                "file_path": "docs/appendix.txt",
                                "text": "Third",
                                "chunk_index": 0,
                                "doc_refs": ["ref-1"],
                                "index_version": "v2",
                            },
                        },
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "upserted": 3}
    mock_get_folder.assert_awaited_once_with("folder-1", mock_db)
    mock_authorize_task.assert_awaited_once()
    await_args = mock_authorize_task.await_args
    assert await_args is not None
    assert await_args.kwargs["db"] is mock_db
    mock_upsert_chunks.assert_awaited_once()
    assert mock_upsert_chunks.await_args.args[1] == "23bfe864fab4c490"
    assert mock_upsert_chunks.await_args.args[2] == [
        VectorChunkUpsert(
            id="chunk-1",
            text="First",
            embedding=[0.1, 0.2],
            chunk_index=0,
            index_version="v1",
        ),
        VectorChunkUpsert(
            id="chunk-2",
            text="Second",
            embedding=[0.3, 0.4],
            chunk_index=1,
            images=["page-1.png"],
            index_version="v1",
        ),
        VectorChunkUpsert(
            id="chunk-3",
            text="Third",
            embedding=[0.5, 0.6],
            chunk_index=0,
            doc_refs=["ref-1"],
            index_version="v2",
        ),
    ]


def test_vector_upsert_maps_vector_dimension_mismatch_to_400(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    result = SimpleNamespace()
    result.scalars = lambda: SimpleNamespace(all=lambda: ["23bfe864fab4c490"])
    mock_db.execute.return_value = result

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        task_secret=_TASK_SECRET,
                        content_item_id="23bfe864fab4c490",
                        folder_uuid="folder-1",
                        relative_path="docs/report.txt",
                    )
                ),
            ),
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new=AsyncMock(
                    side_effect=VectorDimensionMismatchError(
                        "chunk.embedding[0] has 2 dimensions; expected 1024"
                    )
                ),
            ),
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "docs/report.txt",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "chunk.embedding[0] has 2 dimensions; expected 1024"
    )


def test_content_enrichment_chunk_search_dedupes_by_claimed_content_item(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    task = SimpleNamespace(
        id="task-1",
        task_type="process",
        task_secret=_TASK_SECRET,
        status=TaskStatus.CLAIMED,
        claimed_by="worker-1",
        content_item_id="23bfe864fab4c490",
        folder_uuid="folder-1",
        relative_path="docs/report.txt",
    )
    mock_db.execute.return_value = _db_result(one=task)
    embedding_client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(return_value=_embedding_response([0.1, 0.2], [0.3, 0.4]))
        )
    )
    # The endpoint calls the sync embedding client through asyncio.to_thread.
    embedding_client.embeddings.create = lambda **_kwargs: _embedding_response(
        [0.1, 0.2],
        [0.3, 0.4],
    )

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_embedding_client",
                return_value=embedding_client,
            ),
            patch(
                "routers.worker.proxy.VectorService.semantic_search",
                new_callable=AsyncMock,
            ) as mock_search,
        ):
            mock_search.side_effect = [
                [
                    VectorSearchHit(
                        score=0.72,
                        file_path="docs/report.txt",
                        folder_uuid="folder-1",
                        content_item_id="23bfe864fab4c490",
                        text="Invoice date 2026-05-01",
                        chunk_index=2,
                        page_numbers=[1],
                        doc_refs=["#/pages/1"],
                    )
                ],
                [
                    VectorSearchHit(
                        score=0.91,
                        file_path="docs/report.txt",
                        folder_uuid="folder-1",
                        content_item_id="23bfe864fab4c490",
                        text="Invoice date 2026-05-01",
                        chunk_index=2,
                        page_numbers=[1],
                        doc_refs=["#/pages/1"],
                    ),
                    VectorSearchHit(
                        score=0.81,
                        file_path="docs/report.txt",
                        folder_uuid="folder-1",
                        content_item_id="23bfe864fab4c490",
                        text="Customer Demo AG",
                        chunk_index=4,
                    ),
                ],
            ]
            response = test_client.post(
                "/api/worker/tasks/task-1/content-enrichment-chunk-search",
                json={
                    "queries": [
                        {"key": "schema", "text": "Invoice fields"},
                        {"key": "field:invoice_date", "text": "Invoice date"},
                    ],
                    "limit_per_query": 5,
                    "final_limit": 40,
                },
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["chunks"] == [
        {
            "chunk_index": 2,
            "text": "Invoice date 2026-05-01",
            "page_numbers": [1],
            "doc_refs": ["#/pages/1"],
            "images": [],
            "headings": [],
            "score": 0.91,
            "matched_queries": ["schema", "field:invoice_date"],
        },
        {
            "chunk_index": 4,
            "text": "Customer Demo AG",
            "page_numbers": [],
            "doc_refs": [],
            "images": [],
            "headings": [],
            "score": 0.81,
            "matched_queries": ["field:invoice_date"],
        },
    ]
    assert mock_search.await_count == 2
    for call in mock_search.await_args_list:
        assert call.kwargs["file_ids"] == ["23bfe864fab4c490"]


def test_content_enrichment_chunk_search_rejects_invalid_task_secret(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    mock_db.execute.return_value = _db_result(one=None)
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = test_client.post(
            "/api/worker/tasks/task-1/content-enrichment-chunk-search",
            json={"queries": [{"key": "schema", "text": "Invoice"}]},
            headers={"X-Task-Secret": "wrong"},
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 403


def test_vector_upsert_authorizes_exact_task_without_mocking_auth_helper(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    task = SimpleNamespace(
        id="task-1",
        task_type="process",
        task_secret=_TASK_SECRET,
        status=TaskStatus.CLAIMED,
        claimed_by="worker-1",
        content_item_id="23bfe864fab4c490",
        folder_uuid="folder-1",
        relative_path="docs/report.txt",
    )
    mock_db.execute.side_effect = [
        _db_result(one=task),
        _db_result(),
        _db_result(all_values=["23bfe864fab4c490"]),
    ]

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "docs/report.txt",
                                "content_item_id": "stale-content-item-id",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert mock_db.execute.await_count == 3
    mock_upsert_chunks.assert_awaited_once()
    assert mock_upsert_chunks.await_args.args[1] == "23bfe864fab4c490"


def test_vector_upsert_rejects_exact_task_that_left_claimed_state(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    task = SimpleNamespace(
        id="task-1",
        task_type="process",
        task_secret=_TASK_SECRET,
        status=TaskStatus.SUPERSEDED,
        claimed_by="worker-1",
        content_item_id="23bfe864fab4c490",
        folder_uuid="folder-1",
        relative_path="docs/report.txt",
    )
    mock_db.execute.return_value = _db_result(one=task)

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "docs/report.txt",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 409
    assert "no longer active" in response.json()["detail"]
    mock_upsert_chunks.assert_not_awaited()


def test_vector_upsert_ignores_stale_payload_content_item_id(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    result = SimpleNamespace()
    result.scalars = lambda: SimpleNamespace(all=lambda: ["23bfe864fab4c490"])
    mock_db.execute.return_value = result

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        task_secret=_TASK_SECRET,
                        content_item_id="23bfe864fab4c490",
                        folder_uuid="folder-1",
                        relative_path="worker/display/path.txt",
                    )
                ),
            ) as mock_authorize_task,
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "worker/display/path.txt",
                                "content_item_id": "stale-content-item-id",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    mock_authorize_task.assert_awaited_once()
    await_args = mock_authorize_task.await_args
    assert await_args is not None
    mock_upsert_chunks.assert_awaited_once()
    assert mock_upsert_chunks.await_args.args[1] == "23bfe864fab4c490"


def test_vector_upsert_requires_task_id_header(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.TaskQueueService",
            ) as mock_task_queue_service,
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "worker/display/path.txt",
                                "content_item_id": "stale-content-item-id",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-Task-Id header"
    mock_task_queue_service.assert_not_called()
    mock_upsert_chunks.assert_not_awaited()


def test_vector_upsert_rejects_task_for_different_folder(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-2")),
            ),
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        task_secret=_TASK_SECRET,
                        content_item_id="23bfe864fab4c490",
                        folder_uuid="folder-1",
                        relative_path="worker/display/path.txt",
                    )
                ),
            ),
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-2",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "worker/display/path.txt",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Task secret does not match the requested folder"
    )
    mock_upsert_chunks.assert_not_awaited()


def test_vector_upsert_rejects_missing_content_item_before_insert(test_client):
    from main import app

    mock_db = AsyncMock()
    result = SimpleNamespace()
    result.scalars = lambda: SimpleNamespace(all=lambda: [])
    mock_db.execute.return_value = result
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        task_secret=_TASK_SECRET,
                        content_item_id="23bfe864fab4c490",
                        folder_uuid="folder-1",
                        relative_path="worker/display/path.txt",
                    )
                ),
            ),
            patch(
                "routers.worker.proxy.TaskQueueService.restore_claimed_process_content_item",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "worker/display/path.txt",
                                "content_item_id": "23bfe864fab4c490",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Cannot upsert chunks for missing content item",
        "content_item_ids": ["23bfe864fab4c490"],
    }
    mock_upsert_chunks.assert_not_awaited()


def test_vector_upsert_restores_missing_content_item_from_claimed_task(test_client):
    from main import app

    mock_db = AsyncMock()
    result = SimpleNamespace()
    result.scalars = lambda: SimpleNamespace(all=lambda: [])
    mock_db.execute.return_value = result
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ),
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        task_secret=_TASK_SECRET,
                        content_item_id="23bfe864fab4c490",
                        folder_uuid="folder-1",
                        relative_path="worker/display/path.txt",
                    )
                ),
            ),
            patch(
                "routers.worker.proxy.TaskQueueService.restore_claimed_process_content_item",
                new=AsyncMock(return_value=True),
            ) as mock_restore,
            patch(
                "routers.worker.proxy.VectorService.upsert_chunks",
                new_callable=AsyncMock,
            ) as mock_upsert_chunks,
        ):
            response = test_client.post(
                "/api/worker/vector/upsert",
                json={
                    "folder_uuid": "folder-1",
                    "points": [
                        {
                            "id": "chunk-1",
                            "vector": [0.1, 0.2],
                            "payload": {
                                "file_path": "worker/display/path.txt",
                                "content_item_id": "23bfe864fab4c490",
                                "text": "First",
                                "chunk_index": 0,
                                "index_version": "v1",
                            },
                        }
                    ],
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    mock_restore.assert_awaited_once_with(
        content_item_id="23bfe864fab4c490",
        task_secret=_TASK_SECRET,
        worker_id="worker-1",
    )
    mock_upsert_chunks.assert_awaited_once()
