"""Tests for the backend client."""

from unittest.mock import MagicMock, patch

from intextum_worker.models import (
    WorkerApiStatusResponse,
    WorkerClaimedTask,
    WorkerContentEnrichmentChunkSearchQuery,
    WorkerContentEnrichmentChunkSearchResponse,
    WorkerContentEnrichmentRegistryModel,
    WorkerContentEnrichmentTaskSource,
    WorkerContentEnrichmentTrainingArtifactUploadResponse,
    WorkerContentEnrichmentTrainingDataset,
    WorkerContentItemMetadata,
    WorkerRuntimeConfig,
    WorkerRuntimeMetadata,
    WorkerTaskFailureResult,
    WorkerUploadDirectoryResult,
    WorkerUploadFileResponse,
    WorkerVectorChunkPayload,
    WorkerVectorDeleteResponse,
    WorkerVectorPoint,
    WorkerVectorUpsertResponse,
)
from intextum_worker.services.api_client import API_TIMEOUT, ApiClient


def _mock_session() -> MagicMock:
    """Create a mock requests session with mutable headers."""
    session = MagicMock()
    session.headers = {}
    return session


class TestApiClientConfig:
    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_config_returns_typed_runtime_config_and_caches_per_instance(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "embedding_max_tokens": "512",
            "embedding_model": "test-embedding-model",
            "picture_description_prompt": "Describe this image.",
            "picture_description_model": "gpt-4o-mini",
            "document_classification_enabled": True,
            "document_classification_labels": [
                {
                    "name": "Permit",
                    "version": 2,
                    "description": "Permit documents",
                    "aliases": [],
                }
            ],
            "document_extraction_enabled": True,
            "document_extraction_schemas": [
                {
                    "name": "permit_core",
                    "version": 3,
                    "document_class": "Permit",
                    "description": "Permit metadata",
                    "fields": [
                        {
                            "name": "authority",
                            "dtype": "str",
                            "description": "Authority",
                        }
                    ],
                }
            ],
            "document_extraction_chunk_strategy": "selected",
            "document_extraction_max_chars": 9000,
        }
        session.get.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        first = client.get_config()
        second = client.get_config()

        assert isinstance(first, WorkerRuntimeConfig)
        assert first is second
        assert first.embedding_max_tokens == 512
        assert first.embedding_model == "test-embedding-model"
        assert first.picture_description_prompt == "Describe this image."
        assert first.document_classification_enabled is True
        assert first.document_classification_labels[0].name == "Permit"
        assert first.document_classification_labels[0].version == 2
        assert first.document_extraction_chunk_strategy == "selected"
        assert first.document_extraction_enabled is True
        assert first.document_extraction_schemas[0].name == "permit_core"
        assert first.document_extraction_schemas[0].version == 3
        session.get.assert_called_once_with(
            "http://localhost:8000/api/worker/config",
            timeout=API_TIMEOUT,
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_config_force_refresh_reloads_runtime_config(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        first_response = MagicMock()
        first_response.json.return_value = {
            "embedding_max_tokens": 512,
            "embedding_model": "model-a",
        }
        second_response = MagicMock()
        second_response.json.return_value = {
            "embedding_max_tokens": 1024,
            "embedding_model": "model-b",
        }
        session.get.side_effect = [first_response, second_response]
        mock_session_cls.return_value = session

        client = ApiClient()
        first = client.get_config()
        second = client.get_config(force_refresh=True)

        assert first.embedding_model == "model-a"
        assert second.embedding_model == "model-b"
        assert session.get.call_count == 2

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_config_cache_is_not_shared_between_instances(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings

        session_a = _mock_session()
        response_a = MagicMock()
        response_a.json.return_value = {
            "embedding_max_tokens": 512,
            "embedding_model": "model-a",
            "picture_description_prompt": "Prompt A",
            "document_classification_enabled": False,
        }
        session_a.get.return_value = response_a

        session_b = _mock_session()
        response_b = MagicMock()
        response_b.json.return_value = {
            "embedding_max_tokens": 1024,
            "embedding_model": "model-b",
            "picture_description_prompt": "Prompt B",
            "document_classification_enabled": True,
        }
        session_b.get.return_value = response_b

        mock_session_cls.side_effect = [session_a, session_b]

        client_a = ApiClient()
        client_b = ApiClient()

        config_a_first = client_a.get_config()
        config_a_second = client_a.get_config()
        config_b_first = client_b.get_config()
        config_b_second = client_b.get_config()

        assert config_a_first is config_a_second
        assert config_b_first is config_b_second
        assert config_a_first.embedding_model == "model-a"
        assert config_b_first.embedding_model == "model-b"
        assert session_a.get.call_count == 1
        assert session_b.get.call_count == 1

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_report_runtime_metadata_posts_typed_payload(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"status": "ok"}
        session.post.return_value = response
        mock_session_cls.return_value = session

        metadata = WorkerRuntimeMetadata(
            runtime_profile="macos-mps",
            capabilities=["document"],
            classification_device="mps",
            python_version="3.12.3",
            platform_system="Darwin",
            platform_machine="arm64",
            platform_release="25.0.0",
            torch_version="2.6.0",
            torch_mps_available=True,
            torch_cuda_available=False,
            torch_cuda_device_count=0,
            docling_ocr_engine="ocrmac",
            work_dir="/tmp/intextum-worker",
            startup_at="2026-05-09T00:00:00+00:00",
            executable="/path/to/python",
        )

        result = ApiClient().report_runtime_metadata(metadata)

        assert isinstance(result, WorkerApiStatusResponse)
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/runtime-metadata",
            json=metadata.model_dump(exclude_none=False),
            timeout=API_TIMEOUT,
        )


class TestApiClientTaskLifecycle:
    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_claim_task_serializes_capabilities_and_parses_task(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "task_id": "task-1",
            "task_type": "process",
            "content_kind": "document",
            "content_item_id": "file-1",
            "folder_uuid": "folder-1",
            "relative_path": "docs/test.pdf",
            "metadata": {"content_item_id": "file-1"},
            "task_secret": "secret-1",
            "retry_count": 0,
        }
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        task = client.claim_task(["document", "image"])

        assert isinstance(task, WorkerClaimedTask)
        assert task.task_id == "task-1"
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/claim",
            json={"capabilities": ["document", "image"]},
            timeout=API_TIMEOUT,
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_content_enrichment_training_dataset_returns_typed_payload(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "task_id": "task-1",
            "training_job_id": "job-1",
            "registry_model_id": "model-1",
            "target_kind": "classification",
            "training_method": "lora",
            "base_model": "fastino/gliner2-multi-v1",
            "config_fingerprint": "fingerprint-1",
            "config_snapshot": {
                "document_classification_labels": [
                    {"name": "Invoice", "description": "Invoice documents"}
                ]
            },
            "examples": [
                {
                    "content_item_id": "file-1",
                    "relative_path": "docs/invoice.pdf",
                    "input": "Invoice 42",
                    "output": {
                        "classifications": [
                            {
                                "task": "document_class",
                                "labels": ["Invoice"],
                                "true_label": "Invoice",
                            }
                        ]
                    },
                    "review_status": "accepted",
                }
            ],
        }
        session.get.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        dataset = client.get_content_enrichment_training_dataset("task-1", "secret-1")

        assert isinstance(dataset, WorkerContentEnrichmentTrainingDataset)
        assert dataset.training_job_id == "job-1"
        assert dataset.examples[0].relative_path == "docs/invoice.pdf"
        session.get.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/content-enrichment-training-dataset",
            timeout=(10, 300),
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_content_enrichment_registry_model_returns_typed_payload(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "id": "model-1",
            "target_kind": "classification",
            "training_method": "lora",
            "base_model": "fastino/gliner2-multi-v1",
            "config_fingerprint": "fingerprint-1",
            "artifact_path": "content-enrichment/model-1/adapter.tar.gz",
        }
        session.get.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        model = client.get_content_enrichment_registry_model(
            "model-1", "task-1", "secret-1"
        )

        assert isinstance(model, WorkerContentEnrichmentRegistryModel)
        assert model.id == "model-1"
        session.get.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/content-enrichment-models/model-1",
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_content_enrichment_task_source_returns_typed_payload(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "task_id": "task-1",
            "content_item_id": "file-1",
            "relative_path": "docs/invoice.pdf",
            "current_document_class": "Invoice",
            "chunks": [
                {
                    "chunk_index": 0,
                    "text": "Invoice 42",
                    "page_numbers": [1],
                    "doc_refs": ["#/pages/1"],
                    "images": [],
                }
            ],
        }
        session.get.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        source = client.get_content_enrichment_task_source("task-1", "secret-1")

        assert isinstance(source, WorkerContentEnrichmentTaskSource)
        assert source.current_document_class == "Invoice"
        assert source.chunks[0].text == "Invoice 42"
        session.get.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/content-enrichment-source",
            timeout=(10, 300),
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_search_content_enrichment_chunks_returns_typed_payload(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "chunks": [
                {
                    "chunk_index": 7,
                    "text": "Invoice date 2026-05-01",
                    "page_numbers": [2],
                    "doc_refs": ["#/pages/2"],
                    "images": [],
                    "score": 0.88,
                    "matched_queries": ["field:invoice_date"],
                }
            ]
        }
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.search_content_enrichment_chunks(
            "task-1",
            "secret-1",
            queries=[
                WorkerContentEnrichmentChunkSearchQuery(
                    key="field:invoice_date",
                    text="Invoice date",
                )
            ],
            limit_per_query=5,
            final_limit=40,
        )

        assert isinstance(result, WorkerContentEnrichmentChunkSearchResponse)
        assert result.chunks[0].chunk_index == 7
        assert result.chunks[0].score == 0.88
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/content-enrichment-chunk-search",
            json={
                "queries": [{"key": "field:invoice_date", "text": "Invoice date"}],
                "limit_per_query": 5,
                "final_limit": 40,
            },
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_download_content_enrichment_model_artifact_writes_local_file(
        self, mock_session_cls, mock_get_settings, mock_settings, tmp_path
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.iter_content.return_value = [b"adapter"]
        session.get.return_value = response
        mock_session_cls.return_value = session

        target = tmp_path / "model-1" / "adapter.tar.gz"
        client = ApiClient()
        local_file = client.download_content_enrichment_model_artifact(
            "model-1", target, "task-1", "secret-1"
        )

        assert local_file == target
        assert target.read_bytes() == b"adapter"
        session.get.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/content-enrichment-models/model-1/artifact",
            stream=True,
            timeout=(10, 300),
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_complete_task_returns_status_response(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"status": "ok"}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.complete_task(
            "task-1",
            "secret-1",
            processing_config={"do_ocr": False},
        )

        assert isinstance(result, WorkerApiStatusResponse)
        assert result.status == "ok"
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/complete",
            json={"task_secret": "secret-1", "processing_config": {"do_ocr": False}},
            timeout=API_TIMEOUT,
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_complete_content_enrichment_training_task_returns_status_response(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"status": "ok"}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.complete_content_enrichment_training_task(
            "task-1",
            "secret-1",
            artifact_path="models/content-enrichment/model-1/adapter",
            metrics={"accuracy": 0.91},
        )

        assert isinstance(result, WorkerApiStatusResponse)
        assert result.status == "ok"
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/content-enrichment-training-complete",
            json={
                "task_secret": "secret-1",
                "artifact_path": "models/content-enrichment/model-1/adapter",
                "metrics": {"accuracy": 0.91},
            },
            timeout=API_TIMEOUT,
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_upload_content_enrichment_training_artifact_returns_typed_response(
        self, mock_session_cls, mock_get_settings, mock_settings, tmp_path
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "status": "ok",
            "registry_model_id": "model-1",
            "artifact_path": "content-enrichment/model-1/adapter.tar.gz",
            "size": 7,
        }
        session.post.return_value = response
        mock_session_cls.return_value = session

        local_file = tmp_path / "adapter.tar.gz"
        local_file.write_bytes(b"adapter")

        client = ApiClient()
        result = client.upload_content_enrichment_training_artifact(
            "task-1",
            local_file,
            "secret-1",
        )

        assert isinstance(
            result,
            WorkerContentEnrichmentTrainingArtifactUploadResponse,
        )
        assert result.artifact_path == "content-enrichment/model-1/adapter.tar.gz"
        session.post.assert_called_once()
        call = session.post.call_args
        assert call.args[0] == (
            "http://localhost:8000/api/worker/tasks/task-1/"
            "content-enrichment-training-artifact"
        )
        assert call.kwargs["timeout"] == (10, 120)
        assert call.kwargs["headers"] == {"X-Task-Secret": "secret-1"}
        assert call.kwargs["files"]["file"][0] == "adapter.tar.gz"

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_complete_task_includes_content_enrichment_payloads(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"status": "ok"}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.complete_task(
            "task-1",
            "secret-1",
            document_classification={"status": "completed", "label": "Permit"},
            document_extraction={"status": "completed", "schema_name": "permit_core"},
        )

        assert isinstance(result, WorkerApiStatusResponse)
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/complete",
            json={
                "task_secret": "secret-1",
                "document_classification": {
                    "status": "completed",
                    "label": "Permit",
                    "evidence": [],
                },
                "document_extraction": {
                    "status": "completed",
                    "schema_name": "permit_core",
                    "fields": {},
                },
            },
            timeout=API_TIMEOUT,
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_fail_task_returns_typed_retry_result(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "requeued": True,
            "retry_count": 2,
            "new_task_secret": "secret-2",
        }
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.fail_task("task-1", "secret-1", "boom")

        assert isinstance(result, WorkerTaskFailureResult)
        assert result.requeued is True
        assert result.retry_count == 2
        assert result.new_task_secret == "secret-2"
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/fail",
            json={"task_secret": "secret-1", "error_message": "boom"},
            timeout=API_TIMEOUT,
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_check_superseded_returns_bool(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"superseded": True}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()

        assert client.check_superseded("task-1", "secret-1") is True
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/superseded",
            json={"task_secret": "secret-1"},
            timeout=API_TIMEOUT,
        )


class TestApiClientFileAndVector:
    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_content_item_metadata_returns_typed_metadata(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "content_item_id": "file-1",
            "size_bytes": 123,
            "file_extension": ".pdf",
            "is_symlink": False,
        }
        session.get.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.get_content_item_metadata(
            "folder-1", "docs/test.pdf", "secret-1"
        )

        assert isinstance(result, WorkerContentItemMetadata)
        assert result.content_item_id == "file-1"
        assert result.size_bytes == 123
        session.get.assert_called_once_with(
            "http://localhost:8000/api/worker/file-metadata/folder-1/docs/test.pdf",
            timeout=(10, 300),
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_upload_extracted_file_returns_typed_response(
        self, mock_session_cls, mock_get_settings, mock_settings, tmp_path
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {
            "status": "ok",
            "path": "file-1/pages/page-1.png",
            "size": 4,
        }
        session.post.return_value = response
        mock_session_cls.return_value = session

        local_file = tmp_path / "page-1.png"
        local_file.write_bytes(b"data")

        client = ApiClient()
        result = client.upload_extracted_file(
            "file-1",
            "pages/page-1.png",
            local_file,
            "task-1",
            "secret-1",
        )

        assert isinstance(result, WorkerUploadFileResponse)
        assert result.path == "file-1/pages/page-1.png"
        assert result.size == 4
        session.post.assert_called_once()
        assert session.post.call_args.kwargs["headers"] == {
            "X-Task-Id": "task-1",
            "X-Task-Secret": "secret-1",
        }

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_upload_extracted_directory_returns_aggregate_result(
        self, mock_session_cls, mock_get_settings, mock_settings, tmp_path
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        first_response = MagicMock()
        first_response.json.return_value = {
            "status": "ok",
            "content_item_id": "file-1",
            "uploaded": 1,
            "files": [{"path": "pages/page-1.png", "size": 4}],
        }
        second_response = MagicMock()
        second_response.json.return_value = {
            "status": "ok",
            "content_item_id": "file-1",
            "uploaded": 1,
            "files": [{"path": "pages/page-2.png", "size": 5}],
        }
        session.post.side_effect = [first_response, second_response]
        mock_session_cls.return_value = session

        local_dir = tmp_path / "output"
        local_dir.mkdir()
        (local_dir / "page-1.png").write_bytes(b"data")
        (local_dir / "page-2.png").write_bytes(b"data2")

        client = ApiClient()
        result = client.upload_extracted_directory(
            "file-1",
            local_dir,
            "task-1",
            "secret-1",
            batch_size=1,
        )

        assert isinstance(result, WorkerUploadDirectoryResult)
        assert result.content_item_id == "file-1"
        assert result.uploaded == 2
        assert [f.path for f in result.files] == [
            "pages/page-1.png",
            "pages/page-2.png",
        ]
        assert len(result.batches) == 2
        assert session.post.call_count == 2
        assert session.post.call_args_list[0].kwargs["headers"] == {
            "X-Task-Id": "task-1",
            "X-Task-Secret": "secret-1",
        }

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_embeddings_parses_typed_response(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        embeddings = client.get_embeddings(
            ["a", "b"], task_id="task-1", task_secret="secret-1"
        )

        assert embeddings == [[0.1, 0.2], [0.3, 0.4]]
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/embeddings",
            json={"texts": ["a", "b"]},
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_get_token_counts_serializes_text_request(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"counts": [3, 5]}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        counts = client.get_token_counts(
            ["alpha", "beta"], task_id="task-1", task_secret="secret-1"
        )

        assert counts == [3, 5]
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/tasks/task-1/token-count",
            json={"texts": ["alpha", "beta"]},
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_upsert_points_returns_typed_response_and_serializes_points(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"status": "ok", "upserted": 2}
        session.post.return_value = response
        mock_session_cls.return_value = session

        point = WorkerVectorPoint(
            id="p1",
            vector=[0.1],
            payload=WorkerVectorChunkPayload(
                file_path="docs/test.pdf",
                text="Chunk text",
                chunk_index=0,
                index_version="v1",
            ),
        )
        client = ApiClient()
        result = client.upsert_points(
            [point],
            folder_uuid="folder-1",
            task_id="task-1",
            task_secret="secret-1",
            metadata={"content_item_id": "file-1", "text": "wrong text"},
        )

        assert isinstance(result, WorkerVectorUpsertResponse)
        assert result.upserted == 2
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/vector/upsert",
            json={
                "points": [
                    {
                        "id": "p1",
                        "vector": [0.1],
                        "payload": {
                            "file_path": "docs/test.pdf",
                            "source": "file_system",
                            "text": "Chunk text",
                            "chunk_index": 0,
                            "index_version": "v1",
                            "content_item_id": "file-1",
                        },
                    }
                ],
                "folder_uuid": "folder-1",
            },
            timeout=API_TIMEOUT,
            headers={"X-Task-Id": "task-1", "X-Task-Secret": "secret-1"},
        )

    @patch("intextum_worker.services.api_client.get_settings")
    @patch("intextum_worker.services.api_client.requests.Session")
    def test_delete_points_returns_typed_response(
        self, mock_session_cls, mock_get_settings, mock_settings
    ):
        mock_get_settings.return_value = mock_settings
        session = _mock_session()
        response = MagicMock()
        response.json.return_value = {"status": "ok", "deleted": 3}
        session.post.return_value = response
        mock_session_cls.return_value = session

        client = ApiClient()
        result = client.delete_points(
            "docs/test.pdf",
            folder_uuid="folder-1",
            task_secret="secret-1",
            content_item_id="file-1",
            exclude_version="v1",
        )

        assert isinstance(result, WorkerVectorDeleteResponse)
        assert result.deleted == 3
        session.post.assert_called_once_with(
            "http://localhost:8000/api/worker/vector/delete",
            json={
                "file_path": "docs/test.pdf",
                "folder_uuid": "folder-1",
                "content_item_id": "file-1",
                "exclude_version": "v1",
            },
            timeout=API_TIMEOUT,
            headers={"X-Task-Secret": "secret-1"},
        )
