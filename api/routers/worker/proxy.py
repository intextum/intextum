"""Worker API service proxy endpoints."""

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.worker_auth import require_worker_token
from clients import get_embedding_client
from config import get_settings
from database import get_db
from models.content.enrichment_training import ContentEnrichmentWorkerRegistryModel
from models.enums import TaskStatus
from models.sqlalchemy_models import IndexedContentItem
from models.worker import (
    ContentEnrichmentChunkSearchRequest,
    ContentEnrichmentChunkSearchResponse,
    ContentEnrichmentChunkSearchResult,
    DeleteRequest,
    EmbeddingsRequest,
    TokenCountRequest,
    UpsertRequest,
    WorkerVlmChatRequest,
    WorkerRuntimeMetadataRequest,
)
from services.ai_settings import AiSettingsService
from services.ai_limits import (
    DEFAULT_CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS,
    acquire_ai_request_slot,
    ai_request_slot,
)
from services.content_enrichment_training import (
    ContentEnrichmentTrainingService,
)
from services.task_queue import TaskQueueService
from services.vector import VectorService
from services.vector_dimensions import (
    VectorDimensionMismatchError,
    validate_embedding_vectors_length,
)
from services.worker import WorkerService
from services.utils import compute_content_item_id
from rls import set_rls_context, worker_task_context
from .helpers import (
    authorize_claimed_process_task_request,
    authorize_task_request,
    get_task_secret_header,
    get_folder,
    validate_file_id,
)
from .proxy_helpers import (
    _build_vlm_payload,
    _chunk_data_from_point,
    _create_embedding_response,
    _document_extraction_llm_upstream_request,
    _empty_vlm_chat_response,
    _effective_registry_model_ids,
    _embeddings_by_index,
    _extract_single_image_data_url,
    _picture_description_chat_completions_url,
    _picture_description_upstream_timeout_seconds,
    _prompt_token_count,
    _resolve_content_enrichment_artifact_file,
    _sorted_embedding_vectors,
    _validate_worker_texts,
    _validated_max_completion_tokens,
    _worker_config_payload,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _sse_error_event(
    *,
    message: str,
    error_type: str,
    status_code: int | None = None,
) -> bytes:
    payload: dict[str, Any] = {
        "error": {
            "message": message,
            "type": error_type,
        }
    }
    if status_code is not None:
        payload["error"]["status_code"] = status_code
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _ok_response(**values: int) -> dict[str, object]:
    return {"status": "ok", **values}


async def _require_existing_content_item_ids(
    db: AsyncSession,
    content_item_ids: set[str],
    *,
    task_secret: str,
    worker_id: str,
) -> None:
    if not content_item_ids:
        return
    result = await db.execute(
        select(IndexedContentItem.content_item_id).where(
            IndexedContentItem.content_item_id.in_(content_item_ids)
        )
    )
    existing_ids = set(result.scalars().all())
    missing_ids = sorted(content_item_ids - existing_ids)
    if missing_ids:
        task_queue = TaskQueueService(db)
        restored_ids: set[str] = set()
        for content_item_id in missing_ids:
            restored = await task_queue.restore_claimed_process_content_item(
                content_item_id=content_item_id,
                task_secret=task_secret,
                worker_id=worker_id,
            )
            if restored:
                restored_ids.add(content_item_id)
        missing_ids = sorted(set(missing_ids) - restored_ids)

    if missing_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot upsert chunks for missing content item",
                "content_item_ids": missing_ids,
            },
        )


async def _authorize_registry_model_request(
    task_id: str,
    model_id: str,
    request: Request,
    *,
    db: AsyncSession,
    worker_id: str,
):
    await _authorize_claimed_process_task_id(
        task_id, request, db=db, worker_id=worker_id
    )
    ai_settings = await AiSettingsService(db).get_effective_settings()
    if model_id not in _effective_registry_model_ids(ai_settings):
        raise HTTPException(
            status_code=403,
            detail="Registry model is not referenced by effective worker config",
        )


async def _authorize_claimed_process_task_id(
    task_id: str,
    request: Request,
    *,
    db: AsyncSession,
    worker_id: str,
):
    """Resolve one claimed process task from a path task id and task secret."""
    task_secret = get_task_secret_header(request)
    task = await TaskQueueService(db).get_authorized_task(
        task_id, task_secret, worker_id=worker_id
    )
    if (
        task is None
        or task.task_type != "process"
        or not isinstance(task.content_item_id, str)
        or not task.content_item_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Task secret does not match any active processing task",
        )
    if task.status != TaskStatus.CLAIMED:
        raise HTTPException(
            status_code=409,
            detail=f"Processing task is no longer active: {task.status}",
        )
    await set_rls_context(
        db,
        worker_task_context(
            worker_id=worker_id,
            task_id=task_id,
            content_item_id=task.content_item_id,
        ),
    )
    return task


async def _validated_worker_texts_for_task(
    *,
    task_id: str,
    raw_request: Request,
    db: AsyncSession,
    worker_id: str,
    raw_texts: list[str],
) -> tuple[object, list[str]]:
    settings = get_settings()
    texts = _validate_worker_texts(raw_texts, settings)
    await _authorize_claimed_process_task_id(
        task_id, raw_request, db=db, worker_id=worker_id
    )
    return settings, texts


@router.get("/config")
async def get_worker_config(
    db: AsyncSession = Depends(get_db),
    _worker_id: str = Depends(require_worker_token),
):
    """Return worker-relevant configuration from the backend."""
    settings = get_settings()
    ai_settings = await AiSettingsService(db).get_effective_settings()
    return _worker_config_payload(settings, ai_settings)


@router.post("/runtime-metadata")
async def update_worker_runtime_metadata(
    request: WorkerRuntimeMetadataRequest,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Persist non-secret runtime metadata for one authenticated worker."""
    await WorkerService(db).update_config(worker_id, request.model_dump(mode="json"))
    return _ok_response()


@router.post("/tasks/{task_id}/document-extraction-llm/chat/completions")
async def document_extraction_llm_chat_completions(
    task_id: str,
    payload: dict[str, Any],
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Task-bound proxy to the configured chat API for structured extraction.

    Honors ``stream=true`` on the request and forwards an SSE stream from the
    upstream model. Streaming keeps the connection actively producing bytes
    so reverse proxies between us and the model don't enforce idle/read
    timeouts mid-generation.
    """
    if not isinstance(payload.get("messages"), list):
        raise HTTPException(
            status_code=400,
            detail="messages must be an OpenAI-compatible message list",
        )

    await _authorize_claimed_process_task_id(
        task_id, raw_request, db=db, worker_id=worker_id
    )

    settings = get_settings()
    (
        target_url,
        upstream_payload,
        headers,
        timeout_seconds,
        client_requested_stream,
    ) = _document_extraction_llm_upstream_request(
        settings=settings,
        payload=payload,
    )

    if client_requested_stream:
        return await _stream_document_extraction_llm(
            target_url=target_url,
            payload=upstream_payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
            settings=settings,
        )

    async with ai_request_slot(
        settings,
        name="document_extraction_llm",
        concurrency_attr="CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS",
        default_concurrency=DEFAULT_CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS,
        busy_detail="Document extraction LLM service is busy",
    ):
        response = await _post_document_extraction_llm(
            target_url=target_url,
            payload=upstream_payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
    return StreamingResponse(
        iter([response.content]),
        status_code=response.status_code,
        headers={
            "Content-Type": response.headers.get("Content-Type", "application/json")
        },
    )


async def _post_document_extraction_llm(
    *,
    target_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float | None,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False
        ) as client:
            response = await client.post(
                target_url,
                json=payload,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        logger.warning(
            "Document extraction LLM upstream timed out",
            extra={"timeout_seconds": timeout_seconds},
        )
        raise HTTPException(
            status_code=504,
            detail="Document extraction LLM request timed out",
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "Document extraction LLM upstream request failed",
            extra={
                "error": str(exc) or repr(exc),
                "error_type": type(exc).__name__,
                "timeout_seconds": timeout_seconds,
                "target_url": target_url,
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Document extraction LLM request failed",
        ) from exc

    return response


async def _stream_document_extraction_llm(
    *,
    target_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float | None,
    settings: object,
) -> StreamingResponse:
    """Forward a streaming chat-completions request and pipe SSE chunks back."""
    slot = await acquire_ai_request_slot(
        settings,
        name="document_extraction_llm",
        concurrency_attr="CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS",
        default_concurrency=DEFAULT_CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS,
        busy_detail="Document extraction LLM service is busy",
    )

    async def _iter_upstream():
        try:
            async with (
                httpx.AsyncClient(
                    timeout=timeout_seconds, follow_redirects=False
                ) as client,
                client.stream(
                    "POST",
                    target_url,
                    json=payload,
                    headers=headers,
                ) as response,
            ):
                if response.status_code >= 400:
                    body = await response.aread()
                    message = body.decode("utf-8", errors="replace")
                    logger.warning(
                        "Document extraction LLM upstream returned error status",
                        extra={
                            "status_code": response.status_code,
                            "target_url": target_url,
                        },
                    )
                    yield _sse_error_event(
                        message=message,
                        error_type="upstream_error",
                        status_code=response.status_code,
                    )
                    return
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.TimeoutException as exc:
            logger.warning(
                "Document extraction LLM upstream timed out",
                extra={"timeout_seconds": timeout_seconds},
            )
            yield _sse_error_event(
                message="upstream timeout",
                error_type="timeout",
            )
            raise HTTPException(
                status_code=504,
                detail="Document extraction LLM request timed out",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Document extraction LLM upstream request failed",
                extra={
                    "error": str(exc) or repr(exc),
                    "error_type": type(exc).__name__,
                    "timeout_seconds": timeout_seconds,
                    "target_url": target_url,
                },
            )
            yield _sse_error_event(
                message="upstream request failed",
                error_type="request_error",
            )
        finally:
            slot.release()

    return StreamingResponse(
        _iter_upstream(),
        media_type="text/event-stream",
    )


@router.get(
    "/tasks/{task_id}/content-enrichment-models/{model_id}",
    response_model=ContentEnrichmentWorkerRegistryModel,
)
async def get_content_enrichment_model(
    task_id: str,
    model_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Return one task-authorized registry-backed model for worker inference."""
    await _authorize_registry_model_request(
        task_id, model_id, request, db=db, worker_id=worker_id
    )
    model = await ContentEnrichmentTrainingService(db).get_worker_registry_model(
        model_id
    )
    if model is None:
        raise HTTPException(
            status_code=404, detail="Content enrichment model not found"
        )
    return model


@router.get("/tasks/{task_id}/content-enrichment-models/{model_id}/artifact")
async def download_content_enrichment_model_artifact(
    task_id: str,
    model_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Download one task-authorized adapter artifact archive."""
    await _authorize_registry_model_request(
        task_id, model_id, request, db=db, worker_id=worker_id
    )
    model = await ContentEnrichmentTrainingService(db).get_worker_registry_model(
        model_id
    )
    if model is None:
        raise HTTPException(
            status_code=404, detail="Content enrichment model not found"
        )

    settings = get_settings()
    artifacts_root = Path(settings.MODEL_ARTIFACTS_DIR)
    artifact_file = _resolve_content_enrichment_artifact_file(
        artifacts_root,
        model.artifact_path,
    )
    if not artifact_file.is_file():
        raise HTTPException(
            status_code=404, detail="Content enrichment artifact not found"
        )

    return FileResponse(
        path=artifact_file,
        filename=artifact_file.name,
        media_type="application/gzip",
    )


@router.post("/tasks/{task_id}/embeddings")
async def create_embeddings(
    task_id: str,
    request: EmbeddingsRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Generate embeddings for a claimed task via the configured embedding API."""
    settings, texts = await _validated_worker_texts_for_task(
        task_id=task_id,
        raw_request=raw_request,
        db=db,
        worker_id=worker_id,
        raw_texts=request.texts,
    )
    client = get_embedding_client()
    response = await _create_embedding_response(
        client,
        settings,
        model=settings.EMBEDDING_MODEL,
        texts=texts,
    )
    embeddings = _sorted_embedding_vectors(response)
    try:
        validate_embedding_vectors_length(
            embeddings,
            settings,
            context="embedding response",
        )
    except VectorDimensionMismatchError as exc:
        raise HTTPException(
            status_code=502,
            detail="Embedding vector dimension mismatch",
        ) from exc
    return {"embeddings": embeddings}


@router.post("/tasks/{task_id}/token-count")
async def token_count(
    task_id: str,
    request: TokenCountRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Estimate token counts for a claimed task via the embedding backend model."""
    settings, texts = await _validated_worker_texts_for_task(
        task_id=task_id,
        raw_request=raw_request,
        db=db,
        worker_id=worker_id,
        raw_texts=request.texts,
    )
    client = get_embedding_client()
    counts: list[int] = []

    for text in texts:
        response = await _create_embedding_response(
            client,
            settings,
            model=settings.EMBEDDING_MODEL,
            texts=[text],
        )
        counts.append(_prompt_token_count(response))

    return {"counts": counts}


@router.post(
    "/tasks/{task_id}/content-enrichment-chunk-search",
    response_model=ContentEnrichmentChunkSearchResponse,
)
async def content_enrichment_chunk_search(
    task_id: str,
    request: ContentEnrichmentChunkSearchRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    _worker_id: str = Depends(require_worker_token),
):
    """Return semantically relevant chunks for a claimed content enrichment task."""
    task = await _authorize_claimed_process_task_id(
        task_id, raw_request, db=db, worker_id=_worker_id
    )
    queries = [
        query for query in request.queries if query.key.strip() and query.text.strip()
    ]
    if not queries:
        return ContentEnrichmentChunkSearchResponse(chunks=[])

    settings = get_settings()
    client = get_embedding_client()
    embedding_response = await _create_embedding_response(
        client,
        settings,
        model=settings.EMBEDDING_MODEL,
        texts=[query.text for query in queries],
    )
    embeddings_by_index = _embeddings_by_index(embedding_response)

    selected: dict[int, ContentEnrichmentChunkSearchResult] = {}
    for index, query in enumerate(queries):
        embedding = embeddings_by_index.get(index)
        if embedding is None:
            continue
        try:
            hits = await VectorService.semantic_search(
                db,
                embedding,
                request.limit_per_query,
                file_ids=[task.content_item_id],
            )
        except VectorDimensionMismatchError as exc:
            raise HTTPException(
                status_code=502,
                detail="Embedding vector dimension mismatch",
            ) from exc
        for hit in hits:
            existing = selected.get(hit.chunk_index)
            if existing is None:
                selected[hit.chunk_index] = ContentEnrichmentChunkSearchResult(
                    chunk_index=hit.chunk_index,
                    text=hit.text,
                    page_numbers=hit.page_numbers,
                    doc_refs=hit.doc_refs,
                    images=hit.images,
                    headings=hit.headings,
                    score=hit.score,
                    matched_queries=[query.key],
                )
                continue
            if existing.score is None or hit.score > existing.score:
                existing.score = hit.score
            if query.key not in existing.matched_queries:
                existing.matched_queries.append(query.key)

    chunks = sorted(
        selected.values(),
        key=lambda chunk: chunk.score if chunk.score is not None else -1.0,
        reverse=True,
    )[: request.final_limit]
    return ContentEnrichmentChunkSearchResponse(chunks=chunks)


@router.post("/vector/upsert")
async def vector_upsert(
    request: UpsertRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Upsert text chunks into Postgres using pgvector.

    The backend manages ACL fields natively in Postgres via JOINs, so
    worker-supplied ACLs (if any) are ignored.
    """
    if not request.points:
        return _ok_response(upserted=0)

    await get_folder(request.folder_uuid, db)
    task = await authorize_claimed_process_task_request(
        raw_request, db=db, worker_id=worker_id
    )
    if task.folder_uuid != request.folder_uuid:
        raise HTTPException(
            status_code=403,
            detail="Task secret does not match the requested folder",
        )

    content_item_ids = {task.content_item_id}
    await _require_existing_content_item_ids(
        db,
        content_item_ids,
        task_secret=task.task_secret,
        worker_id=worker_id,
    )
    chunks = [_chunk_data_from_point(point) for point in request.points]
    try:
        await VectorService.upsert_chunks(db, task.content_item_id, chunks)
    except VectorDimensionMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _ok_response(upserted=len(request.points))


@router.post("/vector/delete")
async def vector_delete(
    request: DeleteRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Delete chunks matching a content_item_id."""
    await get_folder(request.folder_uuid, db)
    content_item_id = request.content_item_id or compute_content_item_id(
        request.folder_uuid, request.file_path
    )
    await authorize_task_request(
        raw_request,
        content_item_id=content_item_id,
        db=db,
        worker_id=worker_id,
    )

    deleted = await VectorService.delete_chunks(
        db, content_item_id, request.exclude_version
    )
    return _ok_response(deleted=deleted)


@router.post("/vlm/chat/completions")
async def vlm_chat_completions(
    request: WorkerVlmChatRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Task-bound, image-only proxy to configured picture description VLM endpoint."""
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="Streaming is not supported for worker VLM descriptions",
        )

    validate_file_id(request.content_item_id)
    image_data_url = _extract_single_image_data_url(request.messages)
    max_completion_tokens = _validated_max_completion_tokens(
        request.max_completion_tokens
    )
    try:
        task = await authorize_claimed_process_task_request(
            raw_request, db=db, worker_id=worker_id
        )
    except HTTPException as exc:
        if exc.status_code in {403, 409}:
            return _empty_vlm_chat_response(reason=str(exc.detail))
        raise
    if task.content_item_id != request.content_item_id:
        return _empty_vlm_chat_response(
            reason="Task secret does not match the requested content item"
        )

    settings = get_settings()
    ai_settings = await AiSettingsService(db).get_effective_settings()
    target_url = _picture_description_chat_completions_url(settings)
    if not target_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=500,
            detail="PICTURE_DESCRIPTION_URL must use http:// or https:// scheme",
        )
    payload = _build_vlm_payload(
        model=ai_settings.picture_description_model,
        prompt=ai_settings.picture_description_prompt,
        image_data_url=image_data_url,
        max_completion_tokens=max_completion_tokens,
        seed=request.seed,
        enable_thinking=ai_settings.picture_description_enable_thinking,
    )

    try:
        timeout_seconds = _picture_description_upstream_timeout_seconds(settings)
        async with ai_request_slot(
            settings,
            name="picture_description",
            concurrency_attr="PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS",
            default_concurrency=DEFAULT_PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS,
            busy_detail="Picture description service is busy",
        ):
            async with httpx.AsyncClient(
                timeout=timeout_seconds, follow_redirects=False
            ) as client:
                response = await client.post(
                    target_url,
                    json=payload.model_dump(),
                    headers={"Content-Type": "application/json"},
                )
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        logger.warning("Picture description concurrency limit saturated")
        return _empty_vlm_chat_response(
            reason="Picture description service is busy",
            model="picture-description-unavailable",
        )
    except httpx.TimeoutException:
        logger.warning(
            "Picture description upstream timed out",
            extra={"timeout_seconds": timeout_seconds},
        )
        return _empty_vlm_chat_response(
            reason="Upstream model request timed out",
            model="picture-description-unavailable",
        )
    except httpx.RequestError as exc:
        logger.warning(
            "Picture description upstream request failed",
            extra={"error": str(exc)},
        )
        return _empty_vlm_chat_response(
            reason="Upstream model request failed",
            model="picture-description-unavailable",
        )

    if response.status_code >= 400:
        logger.warning(
            "Picture description upstream returned error",
            extra={"status_code": response.status_code},
        )
        return _empty_vlm_chat_response(
            reason=f"Upstream model returned HTTP {response.status_code}",
            model="picture-description-unavailable",
        )

    return StreamingResponse(
        iter([response.content]),
        status_code=response.status_code,
        headers={
            "Content-Type": response.headers.get("Content-Type", "application/json")
        },
    )
