"""Tests for the poll loop task processing logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic import ValidationError

from models import (
    WorkerClaimedTask,
    WorkerContentEnrichmentSourceChunk,
    WorkerContentEnrichmentTaskSource,
    WorkerDocumentClassificationResult,
    WorkerDocumentExtractionResult,
    WorkerDownloadedSourceFile,
    WorkerProcessorContext,
    WorkerTaskMetadata,
)
from poll_loop import (
    AUDIO_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    HttpJobContext,
    _process_task,
)
from processors import ProcessingResult, SimpleChunk


def downloaded_source_file(
    path: Path, *, content_item_id: str = "abc123"
) -> WorkerDownloadedSourceFile:
    """Build a downloaded source file for poll-loop tests."""
    return WorkerDownloadedSourceFile(
        relative_path=path.name,
        local_path=path,
        content_item_id=content_item_id,
    )


def test_processor_context_prefers_top_level_content_item_id_for_metadata():
    context = WorkerProcessorContext(
        task_id="task-1",
        folder_uuid="folder-uuid",
        task_secret="secret-1",
        content_item_id="current-file",
        metadata=WorkerTaskMetadata(content_item_id="stale-file"),
    )

    assert context.resolved_file_id == "current-file"
    assert context.processing_metadata()["content_item_id"] == "current-file"


def test_claimed_task_processor_context_preserves_task_identity():
    task = WorkerClaimedTask(
        task_id="task-current",
        task_type="process",
        folder_uuid="folder-uuid",
        relative_path="document.pdf",
        task_secret="secret-current",
        content_item_id="file-current",
        metadata=WorkerTaskMetadata(content_item_id="file-stale"),
    )

    context = task.processor_context()

    assert context.task_id == "task-current"
    assert context.task_secret == "secret-current"
    assert context.resolved_file_id == "file-current"
    assert context.processing_metadata()["content_item_id"] == "file-current"


@pytest.fixture(autouse=True)
def patch_settings(mock_settings):
    mock_settings.WORK_DIR = "/tmp/worker"
    with (
        patch("poll_loop.settings", mock_settings),
        patch("processors.settings", mock_settings),
    ):
        yield


class TestHttpJobContext:
    def test_is_superseded_returns_false_when_not_superseded(self):
        client = MagicMock()
        client.check_superseded.return_value = False

        ctx = HttpJobContext(
            task_id="task-1",
            task_secret="secret-1",
            correlation_id="test-cid",
            _client=client,
        )

        assert ctx.is_superseded() is False
        client.check_superseded.assert_called_once_with("task-1", "secret-1")

    def test_is_superseded_returns_true_when_superseded(self):
        client = MagicMock()
        client.check_superseded.return_value = True

        ctx = HttpJobContext(
            task_id="task-1",
            task_secret="secret-1",
            correlation_id="test-cid",
            _client=client,
        )

        assert ctx.is_superseded() is True

    def test_is_superseded_returns_false_on_error(self):
        client = MagicMock()
        client.check_superseded.side_effect = Exception("Network error")

        ctx = HttpJobContext(
            task_id="task-1",
            task_secret="secret-1",
            correlation_id="test-cid",
            _client=client,
        )

        assert ctx.is_superseded() is False

    def test_is_superseded_returns_true_when_task_identity_is_invalid(self):
        client = MagicMock()
        error = requests.exceptions.HTTPError("Task not found")
        response = requests.Response()
        response.status_code = 404
        error.response = response
        client.check_superseded.side_effect = error

        ctx = HttpJobContext(
            task_id="task-1",
            task_secret="secret-1",
            correlation_id="test-cid",
            _client=client,
        )

        assert ctx.is_superseded() is True


class TestSimpleChunk:
    def test_simple_chunk_has_text(self):
        chunk = SimpleChunk("test text")
        assert chunk.text == "test text"
        assert chunk.meta is None


class TestProcessTask:
    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_routes_pdf_to_document_processor(
        self, mock_get_path, mock_process, tmp_path
    ):
        test_file = tmp_path / "test.pdf"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="test.pdf",
            message="Processed",
            chunks_created=5,
        )

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        mock_process.assert_called_once()
        client.complete_task.assert_called_once_with("task-1", "secret-1")

    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_accepts_typed_claimed_task(self, mock_get_path, mock_process, tmp_path):
        test_file = tmp_path / "typed.pdf"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="typed.pdf",
            message="Processed",
            chunks_created=1,
        )

        client = MagicMock()
        task = WorkerClaimedTask(
            task_id="task-typed",
            task_type="process",
            task_secret="secret-typed",
            relative_path="typed.pdf",
            folder_uuid="folder-uuid",
            content_item_id="abc123",
        )

        _process_task(client, task)

        client.complete_task.assert_called_once_with("task-typed", "secret-typed")

    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_forwards_processing_config_on_completion(
        self, mock_get_path, mock_process, tmp_path
    ):
        test_file = tmp_path / "test.pdf"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="test.pdf",
            message="Processed",
            chunks_created=5,
            metadata={"processing_config": {"do_ocr": False}},
        )

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        client.complete_task.assert_called_once_with(
            "task-1",
            "secret-1",
            processing_config={"do_ocr": False},
        )

    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_materializes_inline_email_document_without_backend_download(
        self, mock_get_path, mock_process, tmp_path
    ):
        inline_html = (
            "<html><body><h1>Quarterly update</h1><p>Hello team</p></body></html>"
        )
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="Inbox/message.eml",
            message="Processed",
            chunks_created=2,
        )

        with (
            patch("poll_loop.settings.WORK_DIR", str(tmp_path)),
            patch("poll_loop.WorkerTaskRun.cleanup", autospec=True) as mock_cleanup,
        ):
            client = MagicMock()
            task = {
                "task_id": "task-inline",
                "task_type": "process",
                "task_secret": "secret-inline",
                "relative_path": "Inbox/message.eml",
                "folder_uuid": "folder-uuid",
                "content_item_id": "mail-123",
                "metadata": {
                    "content_item_id": "mail-123",
                    "inline_document_source": {
                        "format": "html",
                        "content": inline_html,
                    },
                },
            }

            _process_task(client, task)

        mock_get_path.assert_not_called()
        mock_cleanup.assert_called_once()
        mock_process.assert_called_once()
        inline_path = mock_process.call_args.args[0]
        assert inline_path.suffix == ".html"
        assert inline_path.read_text(encoding="utf-8") == inline_html
        client.complete_task.assert_called_once_with("task-inline", "secret-inline")

    @patch("poll_loop.process_video_metadata")
    @patch("poll_loop.download_source_file")
    def test_routes_video_to_video_processor(
        self, mock_get_path, mock_process, tmp_path
    ):
        test_file = tmp_path / "test.mp4"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="test.mp4",
            message="Processed",
            chunks_created=1,
        )

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.mp4",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        mock_process.assert_called_once()
        client.complete_task.assert_called_once()

    @patch("poll_loop.process_audio")
    @patch("poll_loop.download_source_file")
    def test_routes_audio_to_audio_processor(
        self, mock_get_path, mock_process, tmp_path
    ):
        test_file = tmp_path / "test.mp3"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="test.mp3",
            message="Processed",
            chunks_created=1,
        )

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.mp3",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        mock_process.assert_called_once()
        client.complete_task.assert_called_once()

    @patch("poll_loop.download_source_file")
    def test_completes_for_missing_file(self, mock_get_path, tmp_path):
        mock_get_path.return_value = downloaded_source_file(tmp_path / "missing.pdf")

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "missing.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        client.complete_task.assert_called_once()

    @patch("poll_loop.download_source_file")
    def test_completes_for_unsupported_type(self, mock_get_path, tmp_path):
        test_file = tmp_path / "test.xyz"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.xyz",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        client.complete_task.assert_called_once()

    @patch("poll_loop._upload_extracted_output")
    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_upload_failure_stops_before_completion(
        self,
        mock_get_path,
        mock_process,
        mock_upload,
        tmp_path,
    ):
        test_file = tmp_path / "test.pdf"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="completed",
            file_path="test.pdf",
            message="Processed",
            chunks_created=1,
        )
        response = requests.Response()
        response.status_code = 409
        upload_error = requests.exceptions.HTTPError("HTTP 409")
        upload_error.response = response
        mock_upload.side_effect = upload_error

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        client.complete_task.assert_not_called()
        client.fail_task.assert_called_once_with(
            "task-1",
            "secret-1",
            "FATAL: non-retryable upstream error (409): HTTP 409",
        )

    def test_worker_claimed_task_rejects_removed_delete_type(self):
        with pytest.raises(ValidationError):
            WorkerClaimedTask(
                task_id="task-1",
                task_type="delete",
                task_secret="secret-1",
                relative_path="test/file.pdf",
                folder_uuid="folder-uuid",
                content_item_id="abc123",
            )

    @patch("poll_loop.execute_content_enrichment_training_task")
    @patch("poll_loop.download_source_file")
    def test_training_task_routes_to_training_executor(
        self,
        mock_get_path,
        mock_execute_training,
    ):
        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "train_content_enrichment_model",
            "content_kind": "training",
            "task_secret": "secret-1",
            "relative_path": "content-enrichment-training/job-1",
            "folder_uuid": "__system__",
            "content_item_id": "model-1",
            "metadata": {
                "training_job_id": "job-1",
                "registry_model_id": "model-1",
                "target_kind": "classification",
                "training_method": "lora",
                "base_model": "fastino/gliner2-multi-v1",
                "config_fingerprint": "fp",
            },
        }

        _process_task(client, task)

        mock_execute_training.assert_called_once()
        mock_get_path.assert_not_called()
        client.complete_task.assert_not_called()
        client.fail_task.assert_not_called()

    @patch("poll_loop._run_content_enrichment")
    @patch("poll_loop.download_source_file")
    def test_enrichment_only_task_reruns_without_downloading_source(
        self,
        mock_get_path,
        mock_run_content_enrichment,
    ):
        mock_run_content_enrichment.return_value = (
            WorkerDocumentClassificationResult(
                status="completed",
                label="Invoice",
                model="registry:model-1",
            ),
            WorkerDocumentExtractionResult(
                status="completed",
                schema_name="invoice_fields",
                document_class="Invoice",
                model="registry:model-2",
            ),
        )
        client = MagicMock()
        client.get_content_enrichment_task_source.return_value = (
            WorkerContentEnrichmentTaskSource(
                task_id="task-1",
                content_item_id="file-1",
                relative_path="docs/invoice.pdf",
                current_document_class="Invoice",
                chunks=[
                    WorkerContentEnrichmentSourceChunk(
                        chunk_index=0,
                        text="Invoice 42",
                        page_numbers=[1],
                        doc_refs=["#/pages/1"],
                        images=[],
                    )
                ],
            )
        )
        client.get_config.return_value = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "content_kind": "document",
            "task_secret": "secret-1",
            "relative_path": "docs/invoice.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "file-1",
            "metadata": {
                "content_item_id": "file-1",
                "processing_config": {
                    "enrichment_only": True,
                    "document_enrichment": True,
                },
            },
        }

        _process_task(client, task)

        mock_get_path.assert_not_called()
        client.get_content_enrichment_task_source.assert_called_once_with(
            "task-1",
            "secret-1",
        )
        client.get_config.assert_called_once_with(force_refresh=True)
        client.complete_task.assert_called_once()
        kwargs = client.complete_task.call_args.kwargs
        assert kwargs["processing_config"] == {
            "enrichment_only": True,
            "document_enrichment": True,
        }
        assert kwargs["document_classification"].label == "Invoice"
        assert kwargs["document_extraction"].schema_name == "invoice_fields"

    @patch("poll_loop._run_content_enrichment")
    @patch("poll_loop.download_source_file")
    def test_forced_enrichment_only_task_reports_skipped_classification(
        self,
        mock_get_path,
        mock_run_content_enrichment,
    ):
        classification = WorkerDocumentClassificationResult(
            status="skipped",
            source="forced_class",
            label="Invoice",
            model="classifier",
        )
        extraction = WorkerDocumentExtractionResult(
            status="completed",
            schema_name="invoice_fields",
            document_class="Invoice",
            model="extractor",
        )
        mock_run_content_enrichment.return_value = (classification, extraction)
        client = MagicMock()
        client.get_content_enrichment_task_source.return_value = (
            WorkerContentEnrichmentTaskSource(
                task_id="task-1",
                content_item_id="file-1",
                relative_path="docs/invoice.pdf",
                current_document_class="Invoice",
                chunks=[
                    WorkerContentEnrichmentSourceChunk(
                        chunk_index=0,
                        text="Invoice 42",
                    )
                ],
            )
        )
        client.get_config.return_value = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "content_kind": "document",
            "task_secret": "secret-1",
            "relative_path": "docs/invoice.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "file-1",
            "metadata": {
                "content_item_id": "file-1",
                "processing_config": {
                    "enrichment_only": True,
                    "document_enrichment": True,
                    "forced_document_class_id": "class-invoice",
                    "forced_document_class_label": "Invoice",
                },
            },
        }

        _process_task(client, task)

        mock_get_path.assert_not_called()
        client.complete_task.assert_called_once()
        kwargs = client.complete_task.call_args.kwargs
        assert kwargs["document_classification"] is classification
        assert kwargs["document_extraction"] is extraction

    @patch("poll_loop.execute_content_enrichment_training_task")
    def test_training_task_reports_failure_when_executor_raises(
        self,
        mock_execute_training,
    ):
        mock_execute_training.side_effect = RuntimeError("training failed")
        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "train_content_enrichment_model",
            "content_kind": "training",
            "task_secret": "secret-1",
            "relative_path": "content-enrichment-training/job-1",
            "folder_uuid": "__system__",
            "content_item_id": "model-1",
            "metadata": {
                "training_job_id": "job-1",
                "registry_model_id": "model-1",
                "target_kind": "classification",
                "training_method": "lora",
                "base_model": "fastino/gliner2-multi-v1",
                "config_fingerprint": "fp",
            },
        }

        _process_task(client, task)

        client.fail_task.assert_called_once()

    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_reports_failure_on_exception(self, mock_get_path, mock_process, tmp_path):
        test_file = tmp_path / "test.pdf"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.side_effect = Exception("Processing error")

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        client.fail_task.assert_called_once()

    @patch("poll_loop.process_document")
    @patch("poll_loop.download_source_file")
    def test_aborted_result_reports_abort_not_completion(
        self, mock_get_path, mock_process, tmp_path
    ):
        test_file = tmp_path / "test.pdf"
        test_file.touch()
        mock_get_path.return_value = downloaded_source_file(test_file)
        mock_process.return_value = ProcessingResult(
            status="aborted",
            file_path="test.pdf",
            message="Superseded before conversion",
            aborted=True,
        )

        client = MagicMock()
        task = {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "test.pdf",
            "folder_uuid": "folder-uuid",
            "content_item_id": "abc123",
            "metadata": {"content_item_id": "abc123"},
        }

        _process_task(client, task)

        client.abort_task.assert_called_once_with(
            "task-1",
            "secret-1",
            reason="Superseded before conversion",
        )
        client.complete_task.assert_not_called()
        client.fail_task.assert_not_called()


class TestExtensionSets:
    def test_video_extensions(self):
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mov" in VIDEO_EXTENSIONS
        assert ".mp3" not in VIDEO_EXTENSIONS

    def test_audio_extensions(self):
        assert ".mp3" in AUDIO_EXTENSIONS
        assert ".wav" in AUDIO_EXTENSIONS
        assert ".m4a" in AUDIO_EXTENSIONS

    def test_image_extensions(self):
        assert ".jpg" in IMAGE_EXTENSIONS
        assert ".png" in IMAGE_EXTENSIONS

    def test_document_extensions(self):
        assert ".pdf" in DOCUMENT_EXTENSIONS
        assert ".docx" in DOCUMENT_EXTENSIONS
        assert ".md" in DOCUMENT_EXTENSIONS
