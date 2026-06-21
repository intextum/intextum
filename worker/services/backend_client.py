"""HTTP client for communicating with the backend API."""

import logging
from pathlib import Path
from typing import Any

import requests

from config import get_settings
from models import (
    WorkerAbortTaskRequest,
    WorkerApiStatusResponse,
    WorkerClaimedTask,
    WorkerClaimTaskRequest,
    WorkerCompleteContentEnrichmentTrainingTaskRequest,
    WorkerCompleteTaskRequest,
    WorkerContentEnrichmentChunkSearchQuery,
    WorkerContentEnrichmentChunkSearchRequest,
    WorkerContentEnrichmentChunkSearchResponse,
    WorkerContentEnrichmentRegistryModel,
    WorkerContentEnrichmentTaskSource,
    WorkerContentEnrichmentTrainingArtifactUploadResponse,
    WorkerContentEnrichmentTrainingDataset,
    WorkerContentItemMetadata,
    WorkerDocumentClassificationResult,
    WorkerDocumentExtractionResult,
    WorkerDownloadedSourceFile,
    WorkerEmbeddingsResponse,
    WorkerFailTaskRequest,
    WorkerHeartbeatRequest,
    WorkerRuntimeConfig,
    WorkerRuntimeMetadata,
    WorkerSupersededStatus,
    WorkerTaskFailureResult,
    WorkerTaskSecretRequest,
    WorkerTextsRequest,
    WorkerTokenCountResponse,
    WorkerUploadDirectoryResult,
    WorkerUploadFileResponse,
    WorkerVectorDeleteRequest,
    WorkerVectorDeleteResponse,
    WorkerVectorPoint,
    WorkerVectorUpsertRequest,
    WorkerVectorUpsertResponse,
)
from services.backend_client_api import (
    build_worker_url,
    encode_relative_path,
    model_payload,
    raise_for_status_with_detail,
    resolve_download_target,
    typed_json_response,
    typed_optional_json_response,
    write_download_stream,
)
from services.backend_client_uploads import upload_extracted_directory

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = (10, 300)  # (connect, read) seconds
UPLOAD_TIMEOUT = (10, 120)
API_TIMEOUT = (10, 60)


class BackendClient:
    """Authenticated HTTP client for the backend worker API."""

    def __init__(self):
        settings = get_settings()
        if not settings.WORKER_TOKEN.strip():
            raise ValueError("WORKER_TOKEN must be configured for worker API access")
        self._base_url = settings.BACKEND_URL.rstrip("/")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {settings.WORKER_TOKEN}"
        self._config_cache: WorkerRuntimeConfig | None = None

    def _get_typed(
        self,
        path: str,
        model_cls: type,
        *,
        timeout: tuple[int, int],
        headers: dict[str, str] | None = None,
    ):
        """Execute one GET request and validate the typed response payload."""
        request_kwargs: dict[str, Any] = {"timeout": timeout}
        if headers is not None:
            request_kwargs["headers"] = headers
        resp = self._session.get(
            build_worker_url(self._base_url, path),
            **request_kwargs,
        )
        return typed_json_response(resp, model_cls)

    def _post_typed(
        self,
        path: str,
        payload: object,
        model_cls: type,
        *,
        timeout: tuple[int, int],
        headers: dict[str, str] | None = None,
        exclude_none: bool = True,
    ):
        """Execute one JSON POST request and validate the typed response payload."""
        request_kwargs: dict[str, Any] = {
            "json": model_payload(payload, exclude_none=exclude_none),
            "timeout": timeout,
        }
        if headers is not None:
            request_kwargs["headers"] = headers
        resp = self._session.post(
            build_worker_url(self._base_url, path),
            **request_kwargs,
        )
        return typed_json_response(resp, model_cls)

    def report_runtime_metadata(
        self, metadata: WorkerRuntimeMetadata
    ) -> WorkerApiStatusResponse:
        """Report non-secret runtime metadata for admin visibility."""
        return self._post_typed(
            "/api/worker/runtime-metadata",
            metadata,
            WorkerApiStatusResponse,
            timeout=API_TIMEOUT,
            exclude_none=False,
        )

    def download_file(
        self,
        folder_uuid: str,
        relative_path: str,
        local_dir: Path,
        task_secret: str,
        *,
        download_key: str | None = None,
    ) -> WorkerDownloadedSourceFile:
        """Download a source file from the backend to a local directory."""
        encoded_path = encode_relative_path(relative_path)
        url = build_worker_url(
            self._base_url,
            f"/api/worker/download/{folder_uuid}/{encoded_path}",
        )
        local_path = resolve_download_target(
            local_dir,
            relative_path,
            download_key=download_key,
        )

        logger.info("Downloading %s to %s", relative_path, local_path)
        resp = self._session.get(
            url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )
        raise_for_status_with_detail(resp)
        write_download_stream(resp, local_path)

        logger.info(
            "Downloaded %s (%d bytes)", relative_path, local_path.stat().st_size
        )
        return WorkerDownloadedSourceFile(
            relative_path=relative_path,
            local_path=local_path,
            content_item_id=download_key,
        )

    def get_content_item_metadata(
        self, folder_uuid: str, relative_path: str, task_secret: str
    ) -> WorkerContentItemMetadata:
        """Get content item metadata including content_item_id from the backend."""
        encoded_path = encode_relative_path(relative_path)
        return self._get_typed(
            f"/api/worker/file-metadata/{folder_uuid}/{encoded_path}",
            WorkerContentItemMetadata,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )

    def get_content_enrichment_training_dataset(
        self,
        task_id: str,
        task_secret: str,
    ) -> WorkerContentEnrichmentTrainingDataset:
        """Fetch the reviewed GLiNER2 training dataset for one claimed task."""
        return self._get_typed(
            f"/api/worker/tasks/{task_id}/content-enrichment-training-dataset",
            WorkerContentEnrichmentTrainingDataset,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )

    def get_content_enrichment_task_source(
        self,
        task_id: str,
        task_secret: str,
    ) -> WorkerContentEnrichmentTaskSource:
        """Fetch stored chunks for one claimed enrichment-only rerun task."""
        return self._get_typed(
            f"/api/worker/tasks/{task_id}/content-enrichment-source",
            WorkerContentEnrichmentTaskSource,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )

    def search_content_enrichment_chunks(
        self,
        task_id: str,
        task_secret: str,
        *,
        queries: list[WorkerContentEnrichmentChunkSearchQuery],
        limit_per_query: int,
        final_limit: int,
    ) -> WorkerContentEnrichmentChunkSearchResponse:
        """Search stored chunks for one claimed extraction task."""
        payload = WorkerContentEnrichmentChunkSearchRequest(
            queries=queries,
            limit_per_query=limit_per_query,
            final_limit=final_limit,
        )
        return self._post_typed(
            f"/api/worker/tasks/{task_id}/content-enrichment-chunk-search",
            payload,
            WorkerContentEnrichmentChunkSearchResponse,
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
            exclude_none=False,
        )

    def get_content_enrichment_registry_model(
        self,
        model_id: str,
        task_id: str,
        task_secret: str,
    ) -> WorkerContentEnrichmentRegistryModel:
        """Fetch one ready registry-backed model definition for inference loading."""
        return self._get_typed(
            f"/api/worker/tasks/{task_id}/content-enrichment-models/{model_id}",
            WorkerContentEnrichmentRegistryModel,
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )

    def download_content_enrichment_model_artifact(
        self,
        model_id: str,
        local_file: Path,
        task_id: str,
        task_secret: str,
    ) -> Path:
        """Download one registry model artifact archive to a local file path."""
        local_file.parent.mkdir(parents=True, exist_ok=True)
        resp = self._session.get(
            build_worker_url(
                self._base_url,
                f"/api/worker/tasks/{task_id}/content-enrichment-models/{model_id}/artifact",
            ),
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )
        raise_for_status_with_detail(resp)
        write_download_stream(resp, local_file)
        return local_file

    def upload_content_enrichment_training_artifact(
        self,
        task_id: str,
        local_file: Path,
        task_secret: str,
    ) -> WorkerContentEnrichmentTrainingArtifactUploadResponse:
        """Upload one adapter artifact bundle for a claimed training task."""
        url = build_worker_url(
            self._base_url,
            f"/api/worker/tasks/{task_id}/content-enrichment-training-artifact",
        )
        with open(local_file, "rb") as handle:
            resp = self._session.post(
                url,
                files={"file": (local_file.name, handle)},
                timeout=UPLOAD_TIMEOUT,
                headers={"X-Task-Secret": task_secret},
            )
        return typed_json_response(
            resp,
            WorkerContentEnrichmentTrainingArtifactUploadResponse,
        )

    def upload_extracted_file(
        self,
        content_item_id: str,
        sub_path: str,
        local_file: Path,
        task_id: str,
        task_secret: str,
    ) -> WorkerUploadFileResponse:
        """Upload a single extracted file to the backend."""
        url = build_worker_url(
            self._base_url,
            f"/api/worker/upload-extracted/{content_item_id}",
        )

        with open(local_file, "rb") as handle:
            resp = self._session.post(
                url,
                data={"sub_path": sub_path},
                files={"file": (local_file.name, handle)},
                timeout=UPLOAD_TIMEOUT,
                headers={"X-Task-Id": task_id, "X-Task-Secret": task_secret},
            )
        return typed_json_response(resp, WorkerUploadFileResponse)

    def upload_extracted_directory(
        self,
        content_item_id: str,
        local_dir: Path,
        task_id: str,
        task_secret: str,
        batch_size: int = 10,
    ) -> WorkerUploadDirectoryResult:
        """Upload all files in a directory to the backend using batching."""
        return upload_extracted_directory(
            self._session,
            self._base_url,
            content_item_id,
            local_dir,
            task_id,
            task_secret,
            timeout=UPLOAD_TIMEOUT,
            batch_size=batch_size,
        )

    def get_config(self, *, force_refresh: bool = False) -> WorkerRuntimeConfig:
        """Get worker-relevant config from the backend. Cached per client instance."""
        if self._config_cache is not None and not force_refresh:
            return self._config_cache
        self._config_cache = self._get_typed(
            "/api/worker/config",
            WorkerRuntimeConfig,
            timeout=API_TIMEOUT,
        )
        return self._config_cache

    def get_embeddings(
        self, texts: list[str], *, task_id: str, task_secret: str
    ) -> list[list[float]]:
        """Generate embeddings for texts via the backend proxy."""
        payload = WorkerTextsRequest(texts=texts)
        response = self._post_typed(
            f"/api/worker/tasks/{task_id}/embeddings",
            payload,
            WorkerEmbeddingsResponse,
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
            exclude_none=False,
        )
        return response.embeddings

    def get_token_counts(
        self, texts: list[str], *, task_id: str, task_secret: str
    ) -> list[int]:
        """Estimate token counts for texts via backend embedding proxy."""
        payload = WorkerTextsRequest(texts=texts)
        response = self._post_typed(
            f"/api/worker/tasks/{task_id}/token-count",
            payload,
            WorkerTokenCountResponse,
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
            exclude_none=False,
        )
        return response.counts

    def upsert_points(
        self,
        points: list[WorkerVectorPoint],
        folder_uuid: str,
        task_id: str,
        task_secret: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> WorkerVectorUpsertResponse:
        """Upsert points into Vector DB via the backend proxy."""
        payload = WorkerVectorUpsertRequest(
            points=[point.to_request_point(metadata=metadata) for point in points],
            folder_uuid=folder_uuid,
        )
        return self._post_typed(
            "/api/worker/vector/upsert",
            payload,
            WorkerVectorUpsertResponse,
            timeout=API_TIMEOUT,
            headers={"X-Task-Id": task_id, "X-Task-Secret": task_secret},
        )

    def delete_points(
        self,
        file_path: str,
        *,
        folder_uuid: str,
        task_secret: str,
        content_item_id: str | None = None,
        exclude_version: str | None = None,
    ) -> WorkerVectorDeleteResponse:
        """Delete Vector DB points by file_path via the backend proxy."""
        payload = WorkerVectorDeleteRequest(
            file_path=file_path,
            folder_uuid=folder_uuid,
            content_item_id=content_item_id,
            exclude_version=exclude_version,
        )
        return self._post_typed(
            "/api/worker/vector/delete",
            payload,
            WorkerVectorDeleteResponse,
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": task_secret},
        )

    # --- HTTP Task Queue methods ---

    def claim_task(self, capabilities: list[str]) -> WorkerClaimedTask | None:
        """Claim the next available task matching capabilities."""
        payload = WorkerClaimTaskRequest(capabilities=capabilities)
        resp = self._session.post(
            build_worker_url(self._base_url, "/api/worker/tasks/claim"),
            json=model_payload(payload, exclude_none=False),
            timeout=API_TIMEOUT,
        )
        return typed_optional_json_response(
            resp,
            WorkerClaimedTask,
            none_status=204,
        )

    def complete_task(
        self,
        task_id: str,
        task_secret: str,
        *,
        processing_config: dict[str, object] | None = None,
        document_classification: WorkerDocumentClassificationResult | None = None,
        document_extraction: WorkerDocumentExtractionResult | None = None,
    ) -> WorkerApiStatusResponse:
        """Mark a task as completed."""
        payload = WorkerCompleteTaskRequest(
            task_secret=task_secret,
            processing_config=processing_config,
            document_classification=document_classification,
            document_extraction=document_extraction,
        )
        return self._post_typed(
            f"/api/worker/tasks/{task_id}/complete",
            payload,
            WorkerApiStatusResponse,
            timeout=API_TIMEOUT,
        )

    def complete_content_enrichment_training_task(
        self,
        task_id: str,
        task_secret: str,
        *,
        artifact_path: str,
        metrics: dict[str, object] | None = None,
    ) -> WorkerApiStatusResponse:
        """Mark a training task as completed and promote its registry entry."""
        payload = WorkerCompleteContentEnrichmentTrainingTaskRequest(
            task_secret=task_secret,
            artifact_path=artifact_path,
            metrics=metrics,
        )
        return self._post_typed(
            f"/api/worker/tasks/{task_id}/content-enrichment-training-complete",
            payload,
            WorkerApiStatusResponse,
            timeout=API_TIMEOUT,
        )

    def heartbeat_task(
        self, task_id: str, task_secret: str, stage: str | None = None
    ) -> WorkerApiStatusResponse:
        """Refresh task claim heartbeat to keep long-running jobs active."""
        payload = WorkerHeartbeatRequest(task_secret=task_secret, stage=stage)
        return self._post_typed(
            f"/api/worker/tasks/{task_id}/heartbeat",
            payload,
            WorkerApiStatusResponse,
            timeout=API_TIMEOUT,
            exclude_none=False,
        )

    def fail_task(
        self,
        task_id: str,
        task_secret: str,
        error_message: str,
    ) -> WorkerTaskFailureResult:
        """Report a task failure. Returns {requeued, retry_count, new_task_secret?}."""
        payload = WorkerFailTaskRequest(
            task_secret=task_secret,
            error_message=error_message,
        )
        return self._post_typed(
            f"/api/worker/tasks/{task_id}/fail",
            payload,
            WorkerTaskFailureResult,
            timeout=API_TIMEOUT,
            exclude_none=False,
        )

    def abort_task(
        self, task_id: str, task_secret: str, reason: str = "Aborted by worker"
    ) -> WorkerApiStatusResponse:
        """Explicitly abort a task."""
        payload = WorkerAbortTaskRequest(task_secret=task_secret, reason=reason)
        return self._post_typed(
            f"/api/worker/tasks/{task_id}/abort",
            payload,
            WorkerApiStatusResponse,
            timeout=API_TIMEOUT,
            exclude_none=False,
        )

    def check_superseded(self, task_id: str, task_secret: str) -> bool:
        """Check if a task has been superseded. Returns True if superseded."""
        payload = WorkerTaskSecretRequest(task_secret=task_secret)
        response = self._post_typed(
            f"/api/worker/tasks/{task_id}/superseded",
            payload,
            WorkerSupersededStatus,
            timeout=API_TIMEOUT,
            exclude_none=False,
        )
        return response.superseded
