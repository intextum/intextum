"""Tests for worker embedding proxy endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from fastapi import HTTPException

from auth.worker_auth import require_worker_token


def _embedding(dimensions: int = 1024) -> list[float]:
    return [0.1] * dimensions


def test_embeddings_proxy_uses_configured_model(test_client):
    from main import app

    settings = MagicMock()
    settings.EMBEDDING_MODEL = "backend-fixed-model"
    settings.EMBEDDING_VECTOR_SIZE = 1024

    embed_client = MagicMock()
    embed_client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=_embedding()),
            SimpleNamespace(index=0, embedding=_embedding()),
        ]
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.get_embedding_client", return_value=embed_client
            ),
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock()),
            ) as mock_authorize_task,
        ):
            response = test_client.post(
                "/api/worker/tasks/task-1/embeddings",
                json={"texts": ["one", "two"], "model": "worker-selected-model"},
                headers={"X-Task-Secret": "secret-1"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {"embeddings": [_embedding(), _embedding()]}
    embed_client.embeddings.create.assert_called_once_with(
        model="backend-fixed-model",
        input=["one", "two"],
    )
    mock_authorize_task.assert_awaited_once()


def test_embeddings_proxy_rejects_wrong_provider_vector_dimension(test_client):
    from main import app

    settings = MagicMock()
    settings.EMBEDDING_MODEL = "backend-fixed-model"
    settings.EMBEDDING_VECTOR_SIZE = 1024

    embed_client = MagicMock()
    embed_client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])]
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.get_embedding_client", return_value=embed_client
            ),
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            response = test_client.post(
                "/api/worker/tasks/task-1/embeddings",
                json={"texts": ["one"], "model": "worker-selected-model"},
                headers={"X-Task-Secret": "secret-1"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 502
    assert response.json()["detail"] == "Embedding vector dimension mismatch"


def test_token_count_uses_configured_model(test_client):
    from main import app

    settings = MagicMock()
    settings.EMBEDDING_MODEL = "backend-fixed-model"

    embed_client = MagicMock()
    embed_client.embeddings.create.side_effect = [
        SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3)),
        SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5)),
    ]

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.get_embedding_client", return_value=embed_client
            ),
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock()),
            ) as mock_authorize_task,
        ):
            response = test_client.post(
                "/api/worker/tasks/task-1/token-count",
                json={"texts": ["one", "two"], "model": "worker-selected-model"},
                headers={"X-Task-Secret": "secret-1"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {"counts": [3, 5]}
    assert embed_client.embeddings.create.call_args_list == [
        call(model="backend-fixed-model", input=["one"]),
        call(model="backend-fixed-model", input=["two"]),
    ]
    mock_authorize_task.assert_awaited_once()


def test_worker_wide_embedding_routes_are_removed(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        embedding_response = test_client.post(
            "/api/worker/embeddings",
            json={"texts": ["one"]},
        )
        token_count_response = test_client.post(
            "/api/worker/token-count",
            json={"texts": ["one"]},
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert embedding_response.status_code == 404
    assert token_count_response.status_code == 404


def test_task_scoped_embeddings_reject_empty_texts(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.post(
            "/api/worker/tasks/task-1/embeddings",
            json={"texts": []},
            headers={"X-Task-Secret": "secret-1"},
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 400


def test_task_scoped_embeddings_reject_oversized_texts(test_client):
    from main import app

    settings = MagicMock()
    settings.WORKER_EMBEDDING_MAX_TEXTS = 2
    settings.WORKER_EMBEDDING_MAX_TEXT_CHARS = 4
    settings.WORKER_EMBEDDING_MAX_TOTAL_CHARS = 8

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with patch("routers.worker.proxy.get_settings", return_value=settings):
            response = test_client.post(
                "/api/worker/tasks/task-1/embeddings",
                json={"texts": ["too long"]},
                headers={"X-Task-Secret": "secret-1"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413


def test_task_scoped_token_count_rejects_oversized_texts(test_client):
    from main import app

    settings = MagicMock()
    settings.WORKER_EMBEDDING_MAX_TEXTS = 2
    settings.WORKER_EMBEDDING_MAX_TEXT_CHARS = 100
    settings.WORKER_EMBEDDING_MAX_TOTAL_CHARS = 8

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with patch("routers.worker.proxy.get_settings", return_value=settings):
            response = test_client.post(
                "/api/worker/tasks/task-1/token-count",
                json={"texts": ["12345", "67890"]},
                headers={"X-Task-Secret": "secret-1"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413


def test_task_scoped_token_count_rejects_inactive_task(test_client):
    from main import app

    settings = MagicMock()
    settings.EMBEDDING_MODEL = "backend-fixed-model"

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=409,
                        detail="Processing task is no longer active: completed",
                    )
                ),
            ),
            patch("routers.worker.proxy.get_embedding_client") as mock_get_client,
        ):
            response = test_client.post(
                "/api/worker/tasks/task-1/token-count",
                json={"texts": ["one"]},
                headers={"X-Task-Secret": "secret-1"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 409
    mock_get_client.assert_not_called()
