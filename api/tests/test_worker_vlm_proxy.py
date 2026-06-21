"""Tests for task-bound worker VLM proxy endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import HTTPException

from auth.worker_auth import require_worker_token
from models.ai_settings import EffectiveAiSettings
from models.content.enrichment_training import ContentEnrichmentWorkerRegistryModel

_TASK_SECRET = "test-task-secret"
_TASK_SECRET_HEADER = {"X-Task-Id": "task-1", "X-Task-Secret": _TASK_SECRET}
_IMAGE_URL = "data:image/png;base64,ZmFrZS1pbWFnZQ=="


def _runtime_metadata_payload() -> dict:
    return {
        "runtime_profile": "macos-mps",
        "capabilities": ["document", "image"],
        "classification_device": "mps",
        "python_version": "3.12.3",
        "platform_system": "Darwin",
        "platform_machine": "arm64",
        "platform_release": "25.0.0",
        "torch_version": "2.6.0",
        "torch_mps_available": True,
        "torch_cuda_available": False,
        "torch_cuda_device_count": 0,
        "docling_ocr_engine": "ocrmac",
        "work_dir": "/tmp/intextum-worker",
        "startup_at": "2026-05-09T00:00:00+00:00",
        "executable": "/path/to/python",
    }


def _valid_payload() -> dict:
    return {
        "content_item_id": "abc123",
        "model": "ignored-model",
        "seed": 7,
        "max_completion_tokens": 120,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _IMAGE_URL}},
                    {"type": "text", "text": "ignore this prompt"},
                ],
            }
        ],
    }


def _openai_like_response(content: str) -> bytes:
    return (
        "{"
        '"id":"chatcmpl-1",'
        '"model":"vlm-model",'
        '"created":1,'
        '"choices":[{"index":0,"message":{"role":"assistant","content":"'
        + content
        + '"},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}'
        "}"
    ).encode("utf-8")


def _json_schema_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "extract",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    }


def test_vlm_proxy_requires_task_secret_header(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.post(
            "/api/worker/vlm/chat/completions",
            json=_valid_payload(),
            headers={"X-Task-Id": "task-1"},
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-Task-Secret header"


def test_vlm_proxy_requires_task_id_header(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.post(
            "/api/worker/vlm/chat/completions",
            json=_valid_payload(),
            headers={"X-Task-Secret": _TASK_SECRET},
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-Task-Id header"


def test_get_content_enrichment_model_returns_registry_payload(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_registry_model_request",
                new=AsyncMock(),
            ) as mock_authorize_model,
            patch(
                "routers.worker.proxy.ContentEnrichmentTrainingService.get_worker_registry_model",
                new=AsyncMock(
                    return_value=ContentEnrichmentWorkerRegistryModel(
                        id="model-1",
                        target_kind="classification",
                        training_method="lora",
                        base_model="fastino/gliner2-multi-v1",
                        config_fingerprint="fp-1",
                        artifact_path="content-enrichment/model-1/adapter.tar.gz",
                    )
                ),
            ),
        ):
            response = test_client.get(
                "/api/worker/tasks/task-1/content-enrichment-models/model-1",
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json()["id"] == "model-1"
    mock_authorize_model.assert_awaited_once()


def test_worker_wide_content_enrichment_model_routes_are_removed(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        model_response = test_client.get(
            "/api/worker/content-enrichment-models/model-1"
        )
        artifact_response = test_client.get(
            "/api/worker/content-enrichment-models/model-1/artifact"
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert model_response.status_code == 404
    assert artifact_response.status_code == 404


def test_get_content_enrichment_model_rejects_unconfigured_registry_model(
    test_client,
):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "routers.worker.proxy.AiSettingsService.get_effective_settings",
                new=AsyncMock(
                    return_value=MagicMock(
                        document_classification_model="fastino/gliner2-multi-v1",
                        document_extraction_model="fastino/gliner2-multi-v1",
                        document_extraction_schema_models={},
                    )
                ),
            ),
            patch(
                "routers.worker.proxy.ContentEnrichmentTrainingService.get_worker_registry_model",
                new=AsyncMock(),
            ) as mock_get_model,
        ):
            response = test_client.get(
                "/api/worker/tasks/task-1/content-enrichment-models/model-1",
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 403
    mock_get_model.assert_not_awaited()


def test_runtime_metadata_requires_worker_token(test_client):
    response = test_client.post(
        "/api/worker/runtime-metadata",
        json=_runtime_metadata_payload(),
    )

    assert response.status_code == 401


def test_runtime_metadata_updates_worker_config(test_client):
    from main import app

    payload = _runtime_metadata_payload()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with patch("routers.worker.proxy.WorkerService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.update_config = AsyncMock()
            mock_service_cls.return_value = mock_service

            response = test_client.post(
                "/api/worker/runtime-metadata",
                json=payload,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_service.update_config.assert_awaited_once_with("worker-1", payload)


def test_download_content_enrichment_model_artifact_returns_file(
    test_client,
    temp_data_dir,
):
    artifact_root = temp_data_dir / "model-artifacts"
    artifact_file = artifact_root / "content-enrichment" / "model-1" / "adapter.tar.gz"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_bytes(b"adapter")
    settings = MagicMock()
    settings.MODEL_ARTIFACTS_DIR = str(artifact_root)

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy._authorize_registry_model_request",
                new=AsyncMock(),
            ) as mock_authorize_model,
            patch(
                "routers.worker.proxy.ContentEnrichmentTrainingService.get_worker_registry_model",
                new=AsyncMock(
                    return_value=ContentEnrichmentWorkerRegistryModel(
                        id="model-1",
                        target_kind="classification",
                        training_method="lora",
                        base_model="fastino/gliner2-multi-v1",
                        config_fingerprint="fp-1",
                        artifact_path="content-enrichment/model-1/adapter.tar.gz",
                    )
                ),
            ),
        ):
            response = test_client.get(
                "/api/worker/tasks/task-1/content-enrichment-models/model-1/artifact",
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.content == b"adapter"
    mock_authorize_model.assert_awaited_once()


def test_vlm_proxy_rejects_arbitrary_chat_payload(test_client):
    from main import app

    bad_payload = {
        "content_item_id": "abc123",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    }
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.post(
            "/api/worker/vlm/chat/completions",
            json=bad_payload,
            headers=_TASK_SECRET_HEADER,
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 400
    assert "Exactly one image_url" in response.json()["detail"]


def test_vlm_proxy_sanitizes_payload_and_requires_task_access(test_client):
    from main import app

    settings = MagicMock()
    settings.PICTURE_DESCRIPTION_URL = "http://vlm-service:8000"
    ai_settings = EffectiveAiSettings(
        chat_model="chat-model",
        chat_system_prompt="System prompt",
        chat_tool_prompt="Tool prompt",
        chat_search_limit=8,
        chat_document_max_chars=30000,
        picture_description_model="backend-vlm-model",
        picture_description_prompt="Describe the image accurately.",
        document_classification_enabled=False,
        document_classification_labels=[],
        document_extraction_enabled=False,
        document_extraction_schemas=[],
    )

    upstream_response = MagicMock(
        status_code=200,
        content=_openai_like_response("A test description."),
        headers={"Content-Type": "application/json"},
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=MagicMock(
                        task_secret=_TASK_SECRET,
                        content_item_id="abc123",
                        folder_uuid="folder-1",
                        relative_path="document.pdf",
                    )
                ),
            ) as mock_authorize_task,
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.AiSettingsService.get_effective_settings",
                new=AsyncMock(return_value=ai_settings),
            ),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=upstream_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/vlm/chat/completions",
                json=_valid_payload(),
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "A test description."

    mock_authorize_task.assert_awaited_once()
    mock_client.post.assert_awaited_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert kwargs["json"]["model"] == "backend-vlm-model"
    assert kwargs["json"]["max_tokens"] == 120
    assert kwargs["json"]["seed"] == 7
    assert kwargs["json"]["messages"][0]["content"][0]["image_url"]["url"] == _IMAGE_URL
    assert kwargs["json"]["messages"][0]["content"][1]["text"] == (
        "Describe the image accurately."
    )
    assert "content_item_id" not in kwargs["json"]


def test_vlm_proxy_accepts_openai_v1_base_url(test_client):
    from main import app

    settings = MagicMock()
    settings.PICTURE_DESCRIPTION_URL = "http://vlm-service:8000/v1"
    ai_settings = EffectiveAiSettings(
        chat_model="chat-model",
        chat_system_prompt="System prompt",
        chat_tool_prompt="Tool prompt",
        chat_search_limit=8,
        chat_document_max_chars=30000,
        picture_description_model="backend-vlm-model",
        picture_description_prompt="Describe the image accurately.",
        document_classification_enabled=False,
        document_classification_labels=[],
        document_extraction_enabled=False,
        document_extraction_schemas=[],
    )
    upstream_response = MagicMock(
        status_code=200,
        content=_openai_like_response("A test description."),
        headers={"Content-Type": "application/json"},
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=MagicMock(
                        task_secret=_TASK_SECRET,
                        content_item_id="abc123",
                        folder_uuid="folder-1",
                        relative_path="document.pdf",
                    )
                ),
            ),
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.AiSettingsService.get_effective_settings",
                new=AsyncMock(return_value=ai_settings),
            ),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=upstream_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/vlm/chat/completions",
                json=_valid_payload(),
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    mock_client.post.assert_awaited_once()
    assert mock_client.post.call_args.args[0] == (
        "http://vlm-service:8000/v1/chat/completions"
    )


def test_vlm_proxy_rejects_mismatched_task_content_item(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with patch(
            "routers.worker.proxy.authorize_claimed_process_task_request",
            new=AsyncMock(
                return_value=MagicMock(
                    task_secret=_TASK_SECRET,
                    content_item_id="different-file",
                    folder_uuid="folder-1",
                    relative_path="document.pdf",
                )
            ),
        ):
            response = test_client.post(
                "/api/worker/vlm/chat/completions",
                json=_valid_payload(),
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": ""}
    assert payload["metadata"]["reason"] == (
        "Task secret does not match the requested content item"
    )


def test_vlm_proxy_returns_empty_openai_response_for_invalidated_task(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=403,
                        detail="Task secret does not match any active processing task",
                    )
                ),
            ),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            response = test_client.post(
                "/api/worker/vlm/chat/completions",
                json=_valid_payload(),
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": ""}
    assert payload["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    assert payload["metadata"]["skipped"] is True
    mock_client_cls.assert_not_called()


def test_worker_config_returns_effective_picture_settings(test_client):
    from main import app

    settings = MagicMock()
    settings.EMBEDDING_MODEL = "embed-model"
    settings.EMBEDDING_MAX_TOKENS = 8192
    settings.EMBEDDING_VECTOR_SIZE = 1024
    ai_settings = EffectiveAiSettings(
        chat_model="chat-model",
        chat_system_prompt="System prompt",
        chat_tool_prompt="Tool prompt",
        chat_search_limit=8,
        chat_document_max_chars=30000,
        picture_description_model="effective-vlm-model",
        picture_description_prompt="Use the effective prompt.",
        document_classification_enabled=True,
        document_classification_model="fastino/gliner2-multi-v1",
        document_classification_labels=[
            {
                "name": "Permit",
                "version": 2,
                "description": "Permit documents",
                "aliases": [],
            }
        ],
        document_extraction_enabled=True,
        document_extraction_model="fastino/gliner2-multi-v1",
        document_extraction_schema_models={"permit_core": "registry:model-2"},
        document_extraction_schemas=[
            {
                "name": "permit_core",
                "version": 4,
                "document_class": "Permit",
                "description": "Permit metadata",
                "fields": [
                    {"name": "authority", "dtype": "str", "description": "Authority"}
                ],
            }
        ],
        document_extraction_max_chars=9000,
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.AiSettingsService.get_effective_settings",
                new=AsyncMock(return_value=ai_settings),
            ),
        ):
            response = test_client.get("/api/worker/config")
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {
        "embedding_model": "embed-model",
        "embedding_max_tokens": 8192,
        "embedding_vector_size": 1024,
        "picture_description_model": "effective-vlm-model",
        "picture_description_prompt": "Use the effective prompt.",
        "picture_description_max_tokens": 512,
        "picture_description_timeout_seconds": 300.0,
        "document_classification_provider": "gliner2",
        "document_classification_enabled": True,
        "document_classification_model": "fastino/gliner2-multi-v1",
        "document_classification_labels": [
            {
                "id": "257cfe1345cc5aa7823a422be75072e2",
                "name": "Permit",
                "version": 2,
                "description": "Permit documents",
                "aliases": [],
            }
        ],
        "document_extraction_enabled": True,
        "document_extraction_model": "fastino/gliner2-multi-v1",
        "document_extraction_llm_model": "qwen3-vl:8b",
        "document_extraction_llm_max_output_tokens": 16_384,
        "document_extraction_chunk_strategy": "full",
        "document_extraction_chat_max_retries": 2,
        "document_extraction_chat_evidence_required": True,
        "document_extraction_chat_full_text_threshold_chars": 20_000,
        "content_enrichment_stage_timeout_seconds": 300.0,
        "document_extraction_schema_models": {"permit_core": "registry:model-2"},
        "document_extraction_schemas": [
            {
                "id": "c90b4aa032c65c4bb5a000ac8f1696d2",
                "name": "permit_core",
                "document_class_id": "",
                "version": 4,
                "document_class": "Permit",
                "description": "Permit metadata",
                "fields": [
                    {
                        "name": "authority",
                        "dtype": "str",
                        "description": "Authority",
                        "required": False,
                        "fields": [],
                        "examples": [],
                        "heading_aliases": [],
                        "clustered_under_heading": True,
                    }
                ],
                "scenes": [],
                "section_boundary_terms": [],
            }
        ],
        "document_extraction_max_chars": 9000,
    }


def test_document_extraction_llm_proxy_forwards_without_exposing_key(
    test_client, mock_settings
):
    from main import app

    upstream_response = MagicMock(
        status_code=200,
        content=_openai_like_response("Landkreis"),
        headers={"Content-Type": "application/json"},
    )
    payload = {
        "model": "extract-model",
        "messages": [{"role": "user", "content": "Extract permit metadata"}],
        "response_format": _json_schema_response_format(),
        "stream": False,
    }

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock(task_secret=_TASK_SECRET)),
            ) as mock_authorize_task,
            patch("routers.worker.proxy.get_settings", return_value=mock_settings),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=upstream_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/tasks/task-1/document-extraction-llm/chat/completions",
                json=payload,
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Landkreis"
    mock_authorize_task.assert_awaited_once()
    mock_client.post.assert_awaited_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"] == payload
    assert kwargs["headers"] == {
        "Authorization": "Bearer test-chat-key",
        "Content-Type": "application/json",
    }


def test_document_extraction_llm_proxy_rejects_inactive_task_before_upstream(
    test_client, mock_settings
):
    from main import app

    payload = {
        "model": "extract-model",
        "messages": [{"role": "user", "content": "Extract permit metadata"}],
        "response_format": _json_schema_response_format(),
        "stream": False,
    }

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=409,
                        detail="Processing task is no longer active: completed",
                    )
                ),
            ) as mock_authorize_task,
            patch("routers.worker.proxy.get_settings", return_value=mock_settings),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            response = test_client.post(
                "/api/worker/tasks/task-1/document-extraction-llm/chat/completions",
                json=payload,
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 409
    assert response.json()["detail"] == "Processing task is no longer active: completed"
    mock_authorize_task.assert_awaited_once()
    mock_client_cls.assert_not_called()


def test_document_extraction_llm_proxy_disables_timeout_when_stage_timeout_is_zero(
    test_client, mock_settings
):
    from main import app

    mock_settings.CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS = 0
    upstream_response = MagicMock(
        status_code=200,
        content=_openai_like_response("Oak"),
        headers={"Content-Type": "application/json"},
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock(task_secret=_TASK_SECRET)),
            ),
            patch("routers.worker.proxy.get_settings", return_value=mock_settings),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=upstream_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/tasks/task-1/document-extraction-llm/chat/completions",
                json={
                    "model": "extract-model",
                    "messages": [{"role": "user", "content": "Extract material"}],
                    "stream": False,
                },
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert mock_client_cls.call_args.kwargs["timeout"] is None


def test_document_extraction_llm_proxy_forwards_streaming(test_client, mock_settings):
    from main import app

    upstream_chunks = [
        b'data: {"choices":[{"delta":{"content":"{\\"value\\":"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" 42}"}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    async def _aiter_bytes():
        for chunk in upstream_chunks:
            yield chunk

    class _StreamResponse:
        status_code = 200

        async def aread(self):
            return b"".join(upstream_chunks)

        def aiter_bytes(self):
            return _aiter_bytes()

    stream_response = _StreamResponse()

    class _StreamCtx:
        async def __aenter__(self):
            return stream_response

        async def __aexit__(self, *exc):
            return False

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock(task_secret=_TASK_SECRET)),
            ),
            patch("routers.worker.proxy.get_settings", return_value=mock_settings),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.stream = MagicMock(return_value=_StreamCtx())
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/tasks/task-1/document-extraction-llm/chat/completions",
                json={
                    "model": "extract-model",
                    "messages": [{"role": "user", "content": "Extract"}],
                    "response_format": _json_schema_response_format(),
                    "stream": True,
                },
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    body = response.content
    assert b'"choices"' in body
    assert b"[DONE]" in body
    # Upstream call must have been made with stream=True passthrough.
    mock_client.stream.assert_called_once()
    call_args = mock_client.stream.call_args
    assert call_args.args[0] == "POST"
    assert call_args.kwargs["json"]["stream"] is True
    assert call_args.kwargs["json"]["response_format"]["type"] == "json_schema"


def test_document_extraction_llm_proxy_streams_upstream_error_event(
    test_client, mock_settings
):
    from main import app

    class _StreamResponse:
        status_code = 400

        async def aread(self):
            return b'{"error":{"message":"response_format json_schema unsupported"}}'

        def aiter_bytes(self):
            raise AssertionError("error responses should be read once")

    class _StreamCtx:
        async def __aenter__(self):
            return _StreamResponse()

        async def __aexit__(self, *exc):
            return False

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy._authorize_claimed_process_task_id",
                new=AsyncMock(return_value=MagicMock(task_secret=_TASK_SECRET)),
            ),
            patch("routers.worker.proxy.get_settings", return_value=mock_settings),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.stream = MagicMock(return_value=_StreamCtx())
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/tasks/task-1/document-extraction-llm/chat/completions",
                json={
                    "model": "extract-model",
                    "messages": [{"role": "user", "content": "Extract"}],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "extract",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {"value": {"type": "string"}},
                                "required": ["value"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "stream": True,
                },
                headers={"X-Task-Secret": _TASK_SECRET},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert b"data:" in response.content
    assert b"upstream_error" in response.content
    assert b"json_schema unsupported" in response.content


def test_vlm_proxy_returns_empty_openai_response_for_upstream_timeout(test_client):
    from main import app

    settings = MagicMock()
    settings.PICTURE_DESCRIPTION_URL = "http://vlm-service:8000"
    settings.PICTURE_DESCRIPTION_TIMEOUT_SECONDS = 180
    ai_settings = EffectiveAiSettings(
        chat_model="chat-model",
        chat_system_prompt="System prompt",
        chat_tool_prompt="Tool prompt",
        chat_search_limit=8,
        chat_document_max_chars=30000,
        picture_description_model="backend-vlm-model",
        picture_description_prompt="Describe the image accurately.",
        document_classification_enabled=False,
        document_classification_labels=[],
        document_extraction_enabled=False,
        document_extraction_schemas=[],
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=MagicMock(
                        task_secret=_TASK_SECRET,
                        content_item_id="abc123",
                        folder_uuid="folder-1",
                        relative_path="document.pdf",
                    )
                ),
            ),
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.AiSettingsService.get_effective_settings",
                new=AsyncMock(return_value=ai_settings),
            ),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("slow"))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/vlm/chat/completions",
                json=_valid_payload(),
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "picture-description-unavailable"
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": ""}
    assert payload["metadata"]["reason"] == "Upstream model request timed out"
    assert mock_client_cls.call_args.kwargs["timeout"] == 170


def test_vlm_proxy_returns_empty_openai_response_for_upstream_error(test_client):
    from main import app

    settings = MagicMock()
    settings.PICTURE_DESCRIPTION_URL = "http://vlm-service:8000"
    ai_settings = EffectiveAiSettings(
        chat_model="chat-model",
        chat_system_prompt="System prompt",
        chat_tool_prompt="Tool prompt",
        chat_search_limit=8,
        chat_document_max_chars=30000,
        picture_description_model="backend-vlm-model",
        picture_description_prompt="Describe the image accurately.",
        document_classification_enabled=False,
        document_classification_labels=[],
        document_extraction_enabled=False,
        document_extraction_schemas=[],
    )
    upstream_response = MagicMock(
        status_code=504,
        content=b'{"detail":"slow"}',
        headers={"Content-Type": "application/json"},
    )

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.proxy.authorize_claimed_process_task_request",
                new=AsyncMock(
                    return_value=MagicMock(
                        task_secret=_TASK_SECRET,
                        content_item_id="abc123",
                        folder_uuid="folder-1",
                        relative_path="document.pdf",
                    )
                ),
            ),
            patch("routers.worker.proxy.get_settings", return_value=settings),
            patch(
                "routers.worker.proxy.AiSettingsService.get_effective_settings",
                new=AsyncMock(return_value=ai_settings),
            ),
            patch("routers.worker.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=upstream_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            response = test_client.post(
                "/api/worker/vlm/chat/completions",
                json=_valid_payload(),
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "picture-description-unavailable"
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": ""}
    assert payload["metadata"]["reason"] == "Upstream model returned HTTP 504"
