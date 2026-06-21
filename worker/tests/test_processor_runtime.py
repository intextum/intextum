"""Focused tests for shared worker processor helpers."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models import (
    WorkerDocumentClassificationResult,
    WorkerDocumentExtractionResult,
    WorkerDocumentExtractionSchema,
    WorkerRuntimeConfig,
)
from processor_runtime import (
    ContentEnrichmentStageTimeout,
    SimpleChunk,
    _enrichment_stage_deadline,
    _fallback_chunk_if_empty,
    _processing_flag,
    _run_content_enrichment,
)


def runtime_config(**overrides) -> WorkerRuntimeConfig:
    """Build a minimal runtime config for processor helper tests."""
    return WorkerRuntimeConfig(
        embedding_max_tokens=512,
        embedding_model="test-embedding-model",
        **overrides,
    )


def test_processing_flag_prefers_boolean_override():
    metadata = {
        "processing_config": {
            "document_enrichment": True,
            "unrelated_flag": "yes",
        }
    }

    assert _processing_flag(metadata, "document_enrichment", default=False) is True
    assert _processing_flag(metadata, "unrelated_flag", default=False) is False


def test_fallback_chunk_if_empty_creates_synthetic_chunk():
    log = MagicMock()

    chunks = _fallback_chunk_if_empty(
        [],
        fallback_text="Synthetic fallback",
        log=log,
        log_message="Created fallback chunk",
    )

    assert len(chunks) == 1
    assert isinstance(chunks[0], SimpleChunk)
    assert chunks[0].text == "Synthetic fallback"
    log.info.assert_called_once_with("Created fallback chunk")


def test_enrichment_stage_deadline_fires_off_main_thread():
    """The watchdog must interrupt slow stages even when not on the main thread."""
    import threading

    timed_out: list[bool] = []

    def _run() -> None:
        try:
            with _enrichment_stage_deadline("background-stage", timeout_seconds=0.05):
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    # Busy-loop in pure Python so the async exception can be delivered.
                    pass
        except ContentEnrichmentStageTimeout:
            timed_out.append(True)

    worker = threading.Thread(target=_run)
    worker.start()
    worker.join(timeout=2.0)

    assert not worker.is_alive(), "stage deadline failed to interrupt off-main thread"
    assert timed_out == [True]


def test_run_content_enrichment_skips_when_disabled():
    log = MagicMock()

    classification, extraction = _run_content_enrichment(
        text="Document text",
        chunks=[SimpleChunk("chunk")],
        metadata={},
        runtime_config=runtime_config(),
        log=log,
    )

    assert classification.status == "skipped"
    assert extraction.status == "skipped"


def test_run_content_enrichment_marks_failed_classification():
    log = MagicMock()
    extraction_result = WorkerDocumentExtractionResult(
        status="completed",
        model="extractor",
        schema_name="fallback_fields",
    )

    with (
        patch("processor_runtime.classify_document", side_effect=RuntimeError("boom")),
        patch(
            "processor_runtime.extract_document_data", return_value=extraction_result
        ),
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={"processing_config": {"document_enrichment": True}},
            runtime_config=runtime_config(),
            log=log,
        )

    assert classification.status == "failed"
    assert classification.error == "boom"
    assert extraction.status == "completed"
    log.warning.assert_called_once()


def test_run_content_enrichment_marks_timed_out_classification():
    log = MagicMock()
    extraction_result = WorkerDocumentExtractionResult(
        status="skipped",
        model="extractor",
        error="No document class selected for schema-based extraction",
    )

    def slow_classification(*_args, **_kwargs):
        time.sleep(1)

    with (
        patch(
            "processor_runtime.get_settings",
            return_value=SimpleNamespace(CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS=0.01),
        ),
        patch("processor_runtime.classify_document", side_effect=slow_classification),
        patch(
            "processor_runtime.extract_document_data",
            return_value=extraction_result,
        ),
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={"processing_config": {"document_enrichment": True}},
            runtime_config=runtime_config(
                document_classification_enabled=True,
                document_extraction_enabled=True,
                content_enrichment_stage_timeout_seconds=0.01,
            ),
            log=log,
        )

    assert classification.status == "failed"
    assert classification.source == "timeout"
    assert "timed out" in (classification.error or "")
    assert extraction.status == "skipped"
    log.warning.assert_called_once()


def test_run_content_enrichment_marks_timed_out_extraction():
    log = MagicMock()
    classification_result = WorkerDocumentClassificationResult(
        status="completed",
        source="model",
        model="classifier",
        label="permit",
        class_id="class-permit",
    )

    def slow_extraction(*_args, **_kwargs):
        time.sleep(1)

    with (
        patch(
            "processor_runtime.get_settings",
            return_value=SimpleNamespace(CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS=0.01),
        ),
        patch(
            "processor_runtime.classify_document",
            return_value=classification_result,
        ),
        patch("processor_runtime.extract_document_data", side_effect=slow_extraction),
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={},
            runtime_config=runtime_config(
                document_classification_enabled=True,
                document_extraction_enabled=True,
                content_enrichment_stage_timeout_seconds=0.01,
            ),
            log=log,
        )

    assert classification.label == "permit"
    assert extraction.status == "failed"
    assert extraction.document_class == "permit"
    assert extraction.document_class_id == "class-permit"
    assert "timed out" in (extraction.error or "")
    log.warning.assert_called_once()


def test_run_content_enrichment_passes_classification_label_to_extraction():
    log = MagicMock()
    classification_result = WorkerDocumentClassificationResult(
        status="completed",
        source="model",
        model="classifier",
        label="permit",
    )
    extraction_result = WorkerDocumentExtractionResult(
        status="completed",
        model="extractor",
        schema_name="permit_core",
        document_class="permit",
    )

    with (
        patch(
            "processor_runtime.classify_document",
            return_value=classification_result,
        ) as mock_classify,
        patch(
            "processor_runtime.extract_document_data",
            return_value=extraction_result,
        ) as mock_extract,
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={},
            runtime_config=runtime_config(
                document_classification_enabled=True,
                document_extraction_enabled=True,
                document_extraction_chunk_strategy="selected",
            ),
            log=log,
        )

    assert classification.label == "permit"
    assert extraction.schema_name == "permit_core"
    mock_classify.assert_called_once()
    mock_extract.assert_called_once()
    assert mock_extract.call_args.kwargs["document_class"] == "permit"
    assert mock_extract.call_args.kwargs["chunk_strategy"] == "selected"


def test_run_content_enrichment_uses_current_document_class_when_classifier_has_no_label():
    log = MagicMock()
    classification_result = WorkerDocumentClassificationResult(
        status="completed",
        source="model",
        model="classifier",
    )
    extraction_result = WorkerDocumentExtractionResult(
        status="completed",
        model="extractor",
        schema_name="invoice_fields",
        document_class="Invoice",
    )

    with (
        patch(
            "processor_runtime.classify_document", return_value=classification_result
        ),
        patch(
            "processor_runtime.extract_document_data",
            return_value=extraction_result,
        ) as mock_extract,
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={
                "current_document_class": "Invoice",
                "processing_config": {"document_enrichment": True},
            },
            runtime_config=runtime_config(),
            log=log,
        )

    assert classification.status == "completed"
    assert extraction.schema_name == "invoice_fields"
    assert mock_extract.call_args.kwargs["document_class"] == "Invoice"


def test_run_content_enrichment_forced_class_skips_classification():
    log = MagicMock()
    extraction_result = WorkerDocumentExtractionResult(
        status="completed",
        model="extractor",
        schema_name="invoice_fields",
        document_class="Invoice",
    )

    with (
        patch("processor_runtime.classify_document") as mock_classify,
        patch(
            "processor_runtime.extract_document_data",
            return_value=extraction_result,
        ) as mock_extract,
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={
                "processing_config": {
                    "document_enrichment": True,
                    "forced_document_class_id": "class-invoice",
                    "forced_document_class_label": "Invoice",
                },
            },
            runtime_config=runtime_config(),
            log=log,
        )

    assert classification.status == "skipped"
    assert classification.source == "forced_class"
    assert classification.class_id == "class-invoice"
    assert classification.label == "Invoice"
    assert extraction.schema_name == "invoice_fields"
    mock_classify.assert_not_called()
    assert mock_extract.call_args.kwargs["document_class"] == "Invoice"
    assert mock_extract.call_args.kwargs["document_class_id"] == "class-invoice"


def test_run_content_enrichment_extraction_only_runs_on_existing_class():
    """Extraction must run on an existing class even when classification is off."""
    log = MagicMock()
    extraction_result = WorkerDocumentExtractionResult(
        status="completed",
        model="extractor",
        schema_name="invoice_fields",
        document_class="Invoice",
    )

    with (
        patch("processor_runtime.classify_document") as mock_classify,
        patch(
            "processor_runtime.extract_document_data",
            return_value=extraction_result,
        ) as mock_extract,
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={"current_document_class": "Invoice"},
            runtime_config=runtime_config(
                document_classification_enabled=False,
                document_extraction_enabled=True,
            ),
            log=log,
        )

    mock_classify.assert_not_called()
    assert classification.status == "skipped"
    assert extraction.schema_name == "invoice_fields"
    assert mock_extract.call_args.kwargs["document_class"] == "Invoice"


def test_run_content_enrichment_classification_only_skips_extraction():
    """Classification must run while extraction stays skipped when disabled."""
    log = MagicMock()
    classification_result = WorkerDocumentClassificationResult(
        status="completed",
        source="model",
        model="classifier",
        label="permit",
    )

    with (
        patch(
            "processor_runtime.classify_document",
            return_value=classification_result,
        ) as mock_classify,
        patch("processor_runtime.extract_document_data") as mock_extract,
    ):
        classification, extraction = _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={},
            runtime_config=runtime_config(
                document_classification_enabled=True,
                document_extraction_enabled=False,
            ),
            log=log,
        )

    mock_classify.assert_called_once()
    mock_extract.assert_not_called()
    assert classification.label == "permit"
    assert extraction.status == "skipped"


def test_run_content_enrichment_logs_chat_extraction_provider_plan():
    log = MagicMock()
    extraction_result = WorkerDocumentExtractionResult(
        status="completed",
        provider="langgraph_extract",
        model="qwen3-vl:8b",
        schema_name="invoice_fields",
        document_class="Invoice",
    )

    with (
        patch("processor_runtime.classify_document") as mock_classify,
        patch(
            "processor_runtime.extract_document_data",
            return_value=extraction_result,
        ),
    ):
        _run_content_enrichment(
            text="Document text",
            chunks=[SimpleChunk("chunk")],
            metadata={
                "processing_config": {
                    "document_enrichment": True,
                    "forced_document_class_id": "class-invoice",
                    "forced_document_class_label": "Invoice",
                },
            },
            runtime_config=runtime_config(
                document_extraction_enabled=True,
                document_extraction_llm_model="qwen3-vl:8b",
                document_extraction_schemas=[
                    WorkerDocumentExtractionSchema.model_validate(
                        {
                            "name": "invoice_fields",
                            "document_class_id": "class-invoice",
                            "document_class": "Invoice",
                            "fields": [
                                {
                                    "name": "invoice_number",
                                    "dtype": "str",
                                    "description": "Invoice number",
                                }
                            ],
                        }
                    )
                ],
            ),
            log=log,
        )

    mock_classify.assert_not_called()
    started_call = next(
        call
        for call in log.info.call_args_list
        if call.args[0] == "Structured extraction started"
    )
    started_extra = started_call.kwargs["extra"]
    assert started_extra["provider"] == "langgraph_extract"
    assert started_extra["providers"] == ["langgraph_extract"]
    assert started_extra["default_provider"] == "langgraph_extract"
    assert started_extra["model"] == "qwen3-vl:8b"
    assert started_extra["schema_matched"] is True
    assert started_extra["schema_name"] == "invoice_fields"
    assert started_extra["field_groups"] == [
        {
            "provider": "langgraph_extract",
            "model": "qwen3-vl:8b",
            "field_count": 1,
            "fields": ["invoice_number"],
        }
    ]
