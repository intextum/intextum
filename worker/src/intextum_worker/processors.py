"""Business logic for file processing.

Each processor handles a specific file type and can be tested independently.
"""

import time
from pathlib import Path

from intextum_worker.config import get_settings
from intextum_worker.models import WorkerDownloadedSourceFile, WorkerProcessorContext
from intextum_worker.processor_docling import (
    chunk_docling_document,
    maybe_describe_standalone_image,
)
from intextum_worker.processor_runtime import (
    JobContext,
    LoggerType,
    ProcessingResult,
    ProcessingStage,
    SimpleChunk,
    _abort_if_superseded,
    _build_document_fallback_text,
    _document_text_from_chunks,
    _fallback_chunk_if_empty,
    _processing_flag,
    _run_content_enrichment,
)
from intextum_worker.services.api_client import ApiClient
from intextum_worker.services.docling import (
    describe_image_via_vlm,
    get_custom_config,
    run_asr_conversion,
    run_docling_conversion,
)
from intextum_worker.services.docling_enrichment import (
    extract_picture_enrichments,
    inject_standalone_image_as_picture,
)
from intextum_worker.services.docling_output import save_conversion_results
from intextum_worker.services.tokenizer import ApiEmbeddingTokenizer
from intextum_worker.services.vector import push_to_vector

settings = get_settings()


def download_source_file(
    relative_path: str,
    folder_uuid: str,
    task_secret: str,
    *,
    content_item_id: str | None = None,
) -> WorkerDownloadedSourceFile:
    """Download a source file from the backend into the worker input directory.

    Downloads from backend to WORK_DIR/input/.
    """
    work_input = Path(settings.WORK_DIR) / "input"
    client = ApiClient()
    return client.download_file(
        folder_uuid,
        relative_path,
        work_input,
        task_secret,
        download_key=content_item_id,
    )


def get_output_dir(content_item_id: str) -> Path:
    """Determine output directory using the backend file id.

    Writes to WORK_DIR/output/{content_item_id}.
    """
    return Path(settings.WORK_DIR) / "output" / content_item_id


def _maybe_describe_standalone_image(
    document_dict: dict,
    *,
    file_path: Path,
    output_dir: Path,
    task_id: str,
    task_secret: str,
    content_item_id: str,
    log: LoggerType,
) -> None:
    """Describe a standalone image file via VLM and inject it as a picture."""
    maybe_describe_standalone_image(
        document_dict,
        file_path=file_path,
        output_dir=output_dir,
        task_id=task_id,
        task_secret=task_secret,
        content_item_id=content_item_id,
        log=log,
        describe_image=describe_image_via_vlm,
        inject_picture=inject_standalone_image_as_picture,
    )


def _chunk_docling_document(
    document_dict: dict, *, task_id: str, task_secret: str
) -> tuple[object, list, str]:
    """Build doc chunks via Docling's hybrid chunker and backend token counting."""
    return chunk_docling_document(
        document_dict,
        api_client_factory=ApiClient,
        tokenizer_cls=ApiEmbeddingTokenizer,
        task_id=task_id,
        task_secret=task_secret,
    )


# pylint: disable=too-many-locals
def process_video_metadata(
    file_path: Path,
    relative_path: str,
    context: WorkerProcessorContext,
    job_ctx: JobContext,
    log: LoggerType,
) -> ProcessingResult:
    """Lightweight video processor that only indexes metadata."""
    start_time = time.time()
    metadata = context.processing_metadata()

    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before video processing",
        result_message="Superseded before video processing",
    )
    if aborted is not None:
        return aborted

    job_ctx.set_stage(ProcessingStage.INDEXING)
    log.info("Indexing video metadata only")
    summary = f"Video File: {file_path.name}\nPath: {relative_path}"
    chunks = [SimpleChunk(summary)]

    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before video vector upsert",
        result_message="Superseded before vector upsert",
    )
    if aborted is not None:
        return aborted

    job_ctx.set_stage(ProcessingStage.EMBEDDING)
    push_to_vector(
        file_path=relative_path,
        chunks=chunks,
        doc=None,
        metadata=metadata,
        folder_uuid=context.folder_uuid,
        task_id=context.task_id,
        task_secret=context.task_secret,
    )

    processing_time = int((time.time() - start_time) * 1000)

    return ProcessingResult(
        status="completed",
        file_path=relative_path,
        message="Video metadata indexed",
        chunks_created=len(chunks),
        processing_time_ms=processing_time,
    )


# pylint: disable=too-many-locals
def process_document(
    file_path: Path,
    relative_path: str,
    context: WorkerProcessorContext,
    job_ctx: JobContext,
    log: LoggerType,
) -> ProcessingResult:
    """Process documents and images via Docling.

    Args:
        file_path: Absolute path to the document
        relative_path: Path relative to watched folder
        context: Normalized processor context
        job_ctx: Job context for abort checking
        log: Logger with correlation context

    Returns:
        ProcessingResult with status and metrics
    """
    start_time = time.time()
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    metadata = context.processing_metadata()
    content_item_id = context.require_file_id()
    custom_config = get_custom_config(metadata)

    # Step 1: Convert with Docling (abortable)
    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before conversion",
        result_message="Superseded before conversion",
    )
    if aborted is not None:
        return aborted

    runtime_config = ApiClient().get_config()
    job_ctx.set_stage(ProcessingStage.CONVERTING)
    log.info("Starting Docling conversion")
    conv_result = run_docling_conversion(
        file_path,
        custom_config=custom_config,
        task_id=context.task_id,
        task_secret=context.task_secret,
        content_item_id=content_item_id,
    )

    output_dir = get_output_dir(content_item_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Save extracted images (abortable)
    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before saving results",
        result_message="Superseded before saving results",
    )
    if aborted is not None:
        return aborted

    job_ctx.set_stage(ProcessingStage.EXTRACTING_IMAGES)
    log.info("Saving conversion results")
    document_dict, doc_images = save_conversion_results(conv_result, output_dir)

    if file_path.suffix.lower() in image_extensions:
        doc_images.append(str(file_path))

    # For image files, describe the full image via VLM and inject as a picture
    if file_path.suffix.lower() in image_extensions:
        _maybe_describe_standalone_image(
            document_dict,
            file_path=file_path,
            output_dir=output_dir,
            task_id=context.task_id,
            task_secret=context.task_secret,
            content_item_id=content_item_id,
            log=log,
        )

    # Step 3: Extract picture enrichments (instant — enrichment happened during conversion)
    image_classifications = extract_picture_enrichments(document_dict)

    # Step 4: Chunk document (abortable)
    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before chunking",
        result_message="Superseded before chunking",
    )
    if aborted is not None:
        return aborted

    job_ctx.set_stage(ProcessingStage.CHUNKING)
    log.info("Chunking document")
    doc, chunks, embedding_model_name = _chunk_docling_document(
        document_dict,
        task_id=context.task_id,
        task_secret=context.task_secret,
    )

    log.info("Document chunked", extra={"chunk_count": len(chunks)})

    # If no chunks were created, create a synthetic chunk with metadata and classification summary
    chunks = _fallback_chunk_if_empty(
        chunks,
        fallback_text=_build_document_fallback_text(file_path, image_classifications),
        log=log,
        log_message="Created synthetic chunk for empty document",
    )

    # Step 5: Push to vector database
    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before vector upsert",
        result_message="Superseded before vector upsert",
    )
    if aborted is not None:
        return aborted

    job_ctx.set_stage(ProcessingStage.EMBEDDING)
    log.info(
        "Pushing to vector database",
        extra={"chunk_count": len(chunks), "image_count": len(image_classifications)},
    )
    push_to_vector(
        file_path=relative_path,
        chunks=chunks,
        doc=doc,
        metadata=metadata,
        folder_uuid=context.folder_uuid,
        task_id=context.task_id,
        task_secret=context.task_secret,
    )

    document_text = _document_text_from_chunks(chunks)
    document_classification, document_extraction = _run_content_enrichment(
        text=document_text,
        chunks=chunks,
        metadata=metadata,
        runtime_config=runtime_config,
        log=log,
        task_id=context.task_id,
        task_secret=context.task_secret,
        on_stage=job_ctx.set_stage,
    )

    processing_time = int((time.time() - start_time) * 1000)

    return ProcessingResult(
        status="completed",
        file_path=relative_path,
        message=f"Document processed: {len(chunks)} chunks created",
        chunks_created=len(chunks),
        images_classified=len(image_classifications),
        processing_time_ms=processing_time,
        metadata={
            "processing_config": {
                **custom_config.model_dump(),
                "embedding_model": embedding_model_name,
                "document_enrichment": _processing_flag(
                    metadata,
                    "document_enrichment",
                    default=(
                        runtime_config.document_classification_enabled
                        or runtime_config.document_extraction_enabled
                    ),
                ),
            },
            "document_classification": document_classification,
            "document_extraction": document_extraction,
        },
    )


def process_audio(
    file_path: Path,
    relative_path: str,
    context: WorkerProcessorContext,
    job_ctx: JobContext,
    log: LoggerType,
) -> ProcessingResult:
    """Process audio files via Docling ASR and index transcript chunks."""
    start_time = time.time()
    metadata = context.processing_metadata()

    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before ASR conversion",
        result_message="Superseded before ASR conversion",
    )
    if aborted is not None:
        return aborted

    log.info("Starting Docling ASR conversion")
    conv_result = run_asr_conversion(file_path)

    output_dir = get_output_dir(context.require_file_id())
    output_dir.mkdir(parents=True, exist_ok=True)

    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before saving ASR results",
        result_message="Superseded before saving ASR results",
    )
    if aborted is not None:
        return aborted

    log.info("Saving ASR conversion results")
    document_dict, _ = save_conversion_results(conv_result, output_dir)

    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before ASR chunking",
        result_message="Superseded before ASR chunking",
    )
    if aborted is not None:
        return aborted

    doc, chunks, embedding_model_name = _chunk_docling_document(
        document_dict,
        task_id=context.task_id,
        task_secret=context.task_secret,
    )

    chunks = _fallback_chunk_if_empty(
        chunks,
        fallback_text=f"Audio File: {file_path.name}\nPath: {relative_path}",
        log=log,
        log_message="Created synthetic ASR chunk for empty transcript",
    )

    log.info(
        "Pushing ASR transcript to vector database", extra={"chunk_count": len(chunks)}
    )
    aborted = _abort_if_superseded(
        job_ctx,
        log,
        relative_path=relative_path,
        log_message="Job superseded before ASR vector upsert",
        result_message="Superseded before vector upsert",
    )
    if aborted is not None:
        return aborted

    push_to_vector(
        file_path=relative_path,
        chunks=chunks,
        doc=doc,
        metadata=metadata,
        folder_uuid=context.folder_uuid,
        task_id=context.task_id,
        task_secret=context.task_secret,
    )

    processing_time = int((time.time() - start_time) * 1000)
    return ProcessingResult(
        status="completed",
        file_path=relative_path,
        message=f"Audio processed: {len(chunks)} chunks created",
        chunks_created=len(chunks),
        images_classified=0,
        processing_time_ms=processing_time,
        metadata={"processing_config": {"embedding_model": embedding_model_name}},
    )
