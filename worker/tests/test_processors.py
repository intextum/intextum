"""Tests for current processor behavior."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models import (
    WorkerDownloadedSourceFile,
    WorkerProcessorContext,
    WorkerRuntimeConfig,
)
from processors import (
    ProcessingResult,
    SimpleChunk,
    download_source_file,
    get_output_dir,
    process_audio,
    process_document,
    process_video_metadata,
)


class MockJobContext:
    """Simple job context test double."""

    def __init__(self, superseded: bool = False):
        self._superseded = superseded
        self.correlation_id = "test-correlation-id"
        self.stages: list[str] = []

    def is_superseded(self) -> bool:
        return self._superseded

    def set_stage(self, stage: str) -> None:
        self.stages.append(stage)


class SequenceJobContext:
    """Job context test double with deterministic supersession sequence."""

    def __init__(self, superseded_sequence: list[bool]):
        self._superseded_sequence = list(superseded_sequence)
        self.correlation_id = "test-correlation-id"
        self.stages: list[str] = []

    def is_superseded(self) -> bool:
        if self._superseded_sequence:
            return self._superseded_sequence.pop(0)
        return False

    def set_stage(self, stage: str) -> None:
        self.stages.append(stage)


def build_context(
    content_item_id: str | None = "test-file-id",
    *,
    processing_config: dict | None = None,
) -> WorkerProcessorContext:
    """Create a standard processor context for tests."""
    return WorkerProcessorContext(
        task_id="task-id",
        folder_uuid="folder-uuid",
        task_secret="task-secret",
        content_item_id=content_item_id,
        metadata={"processing_config": processing_config},
    )


@pytest.fixture
def mock_logger():
    """Create a mock logger for tests."""
    return MagicMock(spec=logging.Logger)


@pytest.fixture(autouse=True)
def patch_settings(mock_settings):
    """Patch global settings used by the processors module."""
    mock_settings.WORK_DIR = "/tmp/worker"
    with patch("processors.settings", mock_settings):
        yield


class TestModels:
    def test_processing_result_defaults(self):
        result = ProcessingResult(
            status="completed",
            file_path="test.pdf",
            message="ok",
        )
        assert result.status == "completed"
        assert result.chunks_created == 0
        assert result.images_classified == 0
        assert result.processing_time_ms == 0
        assert result.aborted is False
        assert result.error is None
        assert result.metadata == {}

    def test_simple_chunk(self):
        chunk = SimpleChunk("test content")
        assert chunk.text == "test content"
        assert chunk.meta is None


class TestPathHelpers:
    @patch("processors.BackendClient")
    def test_download_source_file_downloads_from_backend(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.download_file.return_value = WorkerDownloadedSourceFile(
            relative_path="documents/test.pdf",
            local_path=Path("/tmp/worker/input/test.pdf"),
        )

        result = download_source_file(
            "documents/test.pdf",
            "folder-uuid-123",
            "task-secret",
        )

        mock_client.download_file.assert_called_once_with(
            "folder-uuid-123",
            "documents/test.pdf",
            Path("/tmp/worker/input"),
            "task-secret",
            download_key=None,
        )
        assert result.local_path == Path("/tmp/worker/input/test.pdf")
        assert result.relative_path == "documents/test.pdf"

    @patch("processors.BackendClient")
    def test_download_source_file_scopes_downloads_by_file_id(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.download_file.return_value = WorkerDownloadedSourceFile(
            relative_path="documents/test.pdf",
            local_path=Path("/tmp/worker/input/abc123/test.pdf"),
            content_item_id="abc123",
        )

        result = download_source_file(
            "documents/test.pdf",
            "folder-uuid-123",
            "task-secret",
            content_item_id="abc123",
        )

        mock_client.download_file.assert_called_once_with(
            "folder-uuid-123",
            "documents/test.pdf",
            Path("/tmp/worker/input"),
            "task-secret",
            download_key="abc123",
        )
        assert result.local_path == Path("/tmp/worker/input/abc123/test.pdf")
        assert result.content_item_id == "abc123"

    def test_get_output_dir_uses_file_id(self):
        result = get_output_dir("abc123")
        assert result == Path("/tmp/worker/output/abc123")


class TestVideoProcessor:
    @patch("processors.push_to_vector")
    def test_video_metadata_success(self, mock_push, mock_logger, tmp_path):
        file_path = tmp_path / "video.mp4"
        file_path.touch()
        job_ctx = MockJobContext(superseded=False)

        result = process_video_metadata(
            file_path,
            "video.mp4",
            build_context(content_item_id="vid123"),
            job_ctx,
            mock_logger,
        )

        assert result.status == "completed"
        assert result.chunks_created == 1
        mock_push.assert_called_once()
        assert mock_push.call_args.kwargs["task_id"] == "task-id"
        assert mock_push.call_args.kwargs["task_secret"] == "task-secret"
        assert mock_push.call_args.kwargs["folder_uuid"] == "folder-uuid"
        # Stage is reported to the heartbeat as the processor advances.
        assert job_ctx.stages == ["indexing", "embedding"]

    @patch("processors.push_to_vector")
    def test_video_metadata_aborts_when_superseded(
        self, mock_push, mock_logger, tmp_path
    ):
        file_path = tmp_path / "video.mp4"
        job_ctx = MockJobContext(superseded=True)

        result = process_video_metadata(
            file_path,
            "video.mp4",
            build_context(content_item_id="vid123"),
            job_ctx,
            mock_logger,
        )

        assert result.status == "aborted"
        assert result.aborted is True
        mock_push.assert_not_called()

    @patch("processors.push_to_vector")
    def test_video_metadata_aborts_before_vector_when_late_superseded(
        self, mock_push, mock_logger, tmp_path
    ):
        file_path = tmp_path / "video.mp4"
        file_path.touch()
        job_ctx = SequenceJobContext([False, True])

        result = process_video_metadata(
            file_path,
            "video.mp4",
            build_context(content_item_id="vid123"),
            job_ctx,
            mock_logger,
        )

        assert result.status == "aborted"
        assert result.message == "Superseded before vector upsert"
        mock_push.assert_not_called()

    def test_document_context_requires_file_id(self, mock_logger, tmp_path):
        file_path = tmp_path / "video.mp4"
        job_ctx = MockJobContext(superseded=False)

        with pytest.raises(ValueError, match=r"metadata\.content_item_id is required"):
            process_document(
                file_path,
                "video.mp4",
                build_context(content_item_id=None),
                job_ctx,
                mock_logger,
            )


class TestDocumentProcessor:
    @patch("processors.run_docling_conversion")
    def test_document_aborts_before_conversion(
        self, mock_convert, mock_logger, tmp_path
    ):
        file_path = tmp_path / "document.pdf"
        job_ctx = MockJobContext(superseded=True)

        result = process_document(
            file_path,
            "document.pdf",
            build_context(content_item_id="doc123"),
            job_ctx,
            mock_logger,
        )

        assert result.status == "aborted"
        assert result.aborted is True
        mock_convert.assert_not_called()

    @patch("processors.push_to_vector")
    @patch("processors._run_content_enrichment")
    @patch("processors.BackendEmbeddingTokenizer")
    @patch("processors.BackendClient")
    @patch("processors.extract_picture_enrichments")
    @patch("processors.save_conversion_results")
    @patch("processors.run_docling_conversion")
    @patch("pathlib.Path.mkdir")
    def test_document_success_pdf(
        self,
        _mock_mkdir,
        mock_convert,
        mock_save,
        mock_enrichments,
        mock_client_cls,
        mock_tokenizer_cls,
        mock_run_enrichment,
        mock_push,
        mock_logger,
        tmp_path,
    ):
        mock_convert.return_value = MagicMock()
        mock_save.return_value = ({"pages": {}, "pictures": []}, [])
        mock_enrichments.return_value = {}
        mock_run_enrichment.return_value = (
            {"status": "completed", "label": "Permit"},
            {"status": "completed", "schema_name": "permit_core"},
        )

        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
        )
        mock_client_cls.return_value = mock_client
        mock_tokenizer_cls.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "docling.datamodel.document": MagicMock(),
                "docling.chunking": MagicMock(),
            },
        ):
            import sys

            mock_doc = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "Test chunk"
            sys.modules[
                "docling.datamodel.document"
            ].DoclingDocument.model_validate.return_value = mock_doc
            sys.modules[
                "docling.chunking"
            ].HybridChunker.return_value.chunk.return_value = [mock_chunk]

            file_path = tmp_path / "document.pdf"
            file_path.touch()
            job_ctx = MockJobContext(superseded=False)

            result = process_document(
                file_path,
                "document.pdf",
                build_context(
                    content_item_id="doc123",
                    processing_config={"embedding_model": "custom-override-model"},
                ),
                job_ctx,
                mock_logger,
            )

        assert result.status == "completed"
        assert result.chunks_created == 1
        mock_push.assert_called_once()
        assert mock_push.call_args.kwargs["task_id"] == "task-id"
        assert mock_push.call_args.kwargs["task_secret"] == "task-secret"
        assert mock_push.call_args.kwargs["folder_uuid"] == "folder-uuid"
        tokenizer_kwargs = mock_tokenizer_cls.call_args.kwargs
        assert "embedding_model" not in tokenizer_kwargs
        assert "embedding_model_name" not in mock_push.call_args.kwargs
        assert result.metadata["processing_config"]["embedding_model"] == (
            "test-embedding-model"
        )
        assert result.metadata["document_classification"]["label"] == "Permit"
        assert result.metadata["document_extraction"]["schema_name"] == "permit_core"

    @patch("processors.push_to_vector")
    @patch("processors._run_content_enrichment")
    @patch("processors.BackendEmbeddingTokenizer")
    @patch("processors.BackendClient")
    @patch("processors.extract_picture_enrichments")
    @patch("processors.save_conversion_results")
    @patch("processors.run_docling_conversion")
    @patch("pathlib.Path.mkdir")
    def test_document_aborts_before_vector_when_late_superseded(
        self,
        _mock_mkdir,
        mock_convert,
        mock_save,
        mock_enrichments,
        mock_client_cls,
        mock_tokenizer_cls,
        mock_run_enrichment,
        mock_push,
        mock_logger,
        tmp_path,
    ):
        mock_convert.return_value = MagicMock()
        mock_save.return_value = ({"pages": {}, "pictures": []}, [])
        mock_enrichments.return_value = {}
        mock_run_enrichment.return_value = (None, None)
        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
        )
        mock_client_cls.return_value = mock_client
        mock_tokenizer_cls.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "docling.datamodel.document": MagicMock(),
                "docling.chunking": MagicMock(),
            },
        ):
            import sys

            mock_doc = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "Test chunk"
            sys.modules[
                "docling.datamodel.document"
            ].DoclingDocument.model_validate.return_value = mock_doc
            sys.modules[
                "docling.chunking"
            ].HybridChunker.return_value.chunk.return_value = [mock_chunk]

            file_path = tmp_path / "document.pdf"
            file_path.touch()
            result = process_document(
                file_path,
                "document.pdf",
                build_context(content_item_id="doc123"),
                SequenceJobContext([False, False, False, True]),
                mock_logger,
            )

        assert result.status == "aborted"
        assert result.message == "Superseded before vector upsert"
        mock_push.assert_not_called()


class TestAudioProcessor:
    @patch("processors.run_asr_conversion")
    def test_audio_aborts_before_conversion(self, mock_asr, mock_logger, tmp_path):
        file_path = tmp_path / "audio.mp3"
        job_ctx = MockJobContext(superseded=True)

        result = process_audio(
            file_path,
            "audio.mp3",
            build_context(content_item_id="aud123"),
            job_ctx,
            mock_logger,
        )

        assert result.status == "aborted"
        assert result.aborted is True
        mock_asr.assert_not_called()

    @patch("processors.push_to_vector")
    @patch("processors.BackendEmbeddingTokenizer")
    @patch("processors.BackendClient")
    @patch("processors.save_conversion_results")
    @patch("processors.run_asr_conversion")
    @patch("pathlib.Path.mkdir")
    def test_audio_success(
        self,
        _mock_mkdir,
        mock_asr,
        mock_save,
        mock_client_cls,
        mock_tokenizer_cls,
        mock_push,
        mock_logger,
        tmp_path,
    ):
        mock_asr.return_value = MagicMock()
        mock_save.return_value = ({}, [])

        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
        )
        mock_client_cls.return_value = mock_client
        mock_tokenizer_cls.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "docling.datamodel.document": MagicMock(),
                "docling.chunking": MagicMock(),
            },
        ):
            import sys

            mock_doc = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "Transcript chunk"
            sys.modules[
                "docling.datamodel.document"
            ].DoclingDocument.model_validate.return_value = mock_doc
            sys.modules[
                "docling.chunking"
            ].HybridChunker.return_value.chunk.return_value = [mock_chunk]

            file_path = tmp_path / "audio.mp3"
            file_path.touch()
            job_ctx = MockJobContext(superseded=False)

            result = process_audio(
                file_path,
                "audio.mp3",
                build_context(
                    content_item_id="aud123",
                    processing_config={"embedding_model": "custom-override-model"},
                ),
                job_ctx,
                mock_logger,
            )

        assert result.status == "completed"
        assert result.chunks_created == 1
        mock_push.assert_called_once()
        assert mock_push.call_args.kwargs["task_id"] == "task-id"
        assert mock_push.call_args.kwargs["task_secret"] == "task-secret"
        assert mock_push.call_args.kwargs["folder_uuid"] == "folder-uuid"
        tokenizer_kwargs = mock_tokenizer_cls.call_args.kwargs
        assert "embedding_model" not in tokenizer_kwargs
        assert "embedding_model_name" not in mock_push.call_args.kwargs
        assert result.metadata["processing_config"]["embedding_model"] == (
            "test-embedding-model"
        )

    @patch("processors.push_to_vector")
    @patch("processors.BackendEmbeddingTokenizer")
    @patch("processors.BackendClient")
    @patch("processors.save_conversion_results")
    @patch("processors.run_asr_conversion")
    @patch("pathlib.Path.mkdir")
    def test_audio_aborts_before_vector_when_late_superseded(
        self,
        _mock_mkdir,
        mock_asr,
        mock_save,
        mock_client_cls,
        mock_tokenizer_cls,
        mock_push,
        mock_logger,
        tmp_path,
    ):
        mock_asr.return_value = MagicMock()
        mock_save.return_value = ({}, [])
        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
        )
        mock_client_cls.return_value = mock_client
        mock_tokenizer_cls.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "docling.datamodel.document": MagicMock(),
                "docling.chunking": MagicMock(),
            },
        ):
            import sys

            mock_doc = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "Transcript chunk"
            sys.modules[
                "docling.datamodel.document"
            ].DoclingDocument.model_validate.return_value = mock_doc
            sys.modules[
                "docling.chunking"
            ].HybridChunker.return_value.chunk.return_value = [mock_chunk]

            file_path = tmp_path / "audio.mp3"
            file_path.touch()
            result = process_audio(
                file_path,
                "audio.mp3",
                build_context(content_item_id="aud123"),
                SequenceJobContext([False, False, False, True]),
                mock_logger,
            )

        assert result.status == "aborted"
        assert result.message == "Superseded before vector upsert"
        mock_push.assert_not_called()
