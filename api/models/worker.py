"""Worker data models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkerCreate(BaseModel):
    """Request model for creating a worker."""

    name: str
    description: str = ""


class WorkerUpdate(BaseModel):
    """Request model for updating a worker."""

    name: str | None = None
    description: str | None = None


class WorkerResponse(BaseModel):
    """Response model for a worker."""

    id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    last_seen: str | None
    config: dict
    status: str


class WorkerCreateResponse(BaseModel):
    """Response model for worker creation (includes token shown only once)."""

    worker: WorkerResponse
    token: str


class WorkerListResponse(BaseModel):
    """Response model for listing workers."""

    workers: list[WorkerResponse]
    total: int


class WorkerTaskQueueItem(BaseModel):
    """Admin-facing summary of one backend queue task."""

    id: str
    task_type: str
    content_kind: str | None = None
    content_item_id: str | None = None
    folder_uuid: str
    relative_path: str
    status: str
    stage: str | None = None
    requested_by_sub: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    claim_age_seconds: int | None = None
    stale_after_seconds: int
    is_stale: bool = False
    retry_count: int
    max_retries: int
    error_message: str | None = None
    created_at: str
    updated_at: str


class WorkerTaskQueueListResponse(BaseModel):
    """Response model for queue task visibility."""

    tasks: list[WorkerTaskQueueItem]
    total: int


class WorkerTaskQueueCleanupResponse(BaseModel):
    """Response model for manual stale queue cleanup."""

    total: int
    requeued: int
    failed: int


class WorkerRuntimeMetadataRequest(BaseModel):
    """Non-secret runtime details reported by an authenticated worker."""

    model_config = ConfigDict(extra="ignore")

    runtime_profile: Literal["cpu", "cuda", "macos-mps"]
    capabilities: list[str] = Field(default_factory=list)
    classification_device: str
    python_version: str
    platform_system: str
    platform_machine: str
    platform_release: str
    torch_version: str | None = None
    torch_mps_available: bool = False
    torch_cuda_available: bool = False
    torch_cuda_device_count: int = 0
    docling_ocr_engine: str
    work_dir: str
    startup_at: str
    executable: str


class DeleteRequest(BaseModel):
    """Request model for deleting vector points by file path."""

    file_path: str
    folder_uuid: str
    content_item_id: str | None = None
    exclude_version: str | None = None


class ClaimTaskRequest(BaseModel):
    """Request model for claiming queued tasks."""

    capabilities: list[str]


class CompleteTaskRequest(BaseModel):
    """Request model for completing a task."""

    task_secret: str
    processing_config: dict[str, Any] | None = None
    document_classification: dict[str, Any] | None = None
    document_extraction: dict[str, Any] | None = None


class CompleteContentEnrichmentTrainingTaskRequest(BaseModel):
    """Request model for completing a content enrichment training task."""

    task_secret: str
    artifact_path: str
    metrics: dict[str, Any] | None = None


class ContentEnrichmentTrainingArtifactUploadResponse(BaseModel):
    """Response model for uploading one content enrichment training artifact."""

    status: Literal["ok"]
    registry_model_id: str
    artifact_path: str
    size: int


class ContentEnrichmentSourceChunk(BaseModel):
    """One stored text chunk reused for enrichment-only reruns."""

    chunk_index: int = 0
    text: str
    page_numbers: list[int] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)


class ContentEnrichmentTaskSourceResponse(BaseModel):
    """Worker-authenticated chunk/text source for one claimed enrichment rerun task."""

    task_id: str
    content_item_id: str
    relative_path: str
    current_document_class: str | None = None
    chunks: list[ContentEnrichmentSourceChunk] = Field(default_factory=list)


class ContentEnrichmentChunkSearchQuery(BaseModel):
    """One semantic query used to select chunks for structured extraction."""

    key: str
    text: str


class ContentEnrichmentChunkSearchRequest(BaseModel):
    """Task-bound semantic chunk search request for content enrichment."""

    queries: list[ContentEnrichmentChunkSearchQuery] = Field(default_factory=list)
    limit_per_query: int = Field(default=5, ge=1, le=20)
    final_limit: int = Field(default=40, ge=1, le=200)


class ContentEnrichmentChunkSearchResult(ContentEnrichmentSourceChunk):
    """One selected chunk with semantic score and matched query metadata."""

    score: float | None = None
    matched_queries: list[str] = Field(default_factory=list)


class ContentEnrichmentChunkSearchResponse(BaseModel):
    """Deduplicated chunks selected for one extraction pass."""

    chunks: list[ContentEnrichmentChunkSearchResult] = Field(default_factory=list)


class HeartbeatTaskRequest(BaseModel):
    """Request model for refreshing a claimed task heartbeat."""

    task_secret: str
    stage: str | None = None


class FailTaskRequest(BaseModel):
    """Request model for reporting a task failure."""

    task_secret: str
    error_message: str


class AbortTaskRequest(BaseModel):
    """Request model for aborting a task."""

    task_secret: str
    reason: str | None = "Aborted by worker"


class CheckSupersededRequest(BaseModel):
    """Request model for checking if a task has been superseded."""

    task_secret: str


class EmbeddingsRequest(BaseModel):
    """Request model for embedding generation."""

    texts: list[str]


class TokenCountRequest(BaseModel):
    """Request model for token count estimation via embedding backend."""

    texts: list[str]


class WorkerVlmImageUrl(BaseModel):
    """Image URL wrapper for OpenAI-style VLM content items."""

    model_config = ConfigDict(extra="ignore")

    url: str


class WorkerVlmImageContent(BaseModel):
    """Image content item accepted by the worker VLM proxy."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["image_url"]
    image_url: WorkerVlmImageUrl


class WorkerVlmTextContent(BaseModel):
    """Text content item accepted by the worker VLM proxy."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["text"]
    text: str


WorkerVlmContentItem = WorkerVlmImageContent | WorkerVlmTextContent


class WorkerVlmMessage(BaseModel):
    """OpenAI-style chat message accepted by the worker VLM proxy."""

    model_config = ConfigDict(extra="ignore")

    role: str
    content: list[WorkerVlmContentItem] = Field(default_factory=list)


class WorkerVlmChatRequest(BaseModel):
    """Request model for worker VLM image description."""

    model_config = ConfigDict(extra="ignore")

    content_item_id: str
    messages: list[WorkerVlmMessage]
    seed: int | None = None
    max_completion_tokens: int | None = None
    stream: bool | None = None


class WorkerVlmProxyPayload(BaseModel):
    """Sanitized upstream payload sent to the picture-description service."""

    model_config = ConfigDict(extra="ignore")

    model: str
    seed: int
    max_tokens: int
    chat_template_kwargs: dict[str, bool]
    messages: list[WorkerVlmMessage]


class WorkerVectorPointPayload(BaseModel):
    """Normalized per-point payload accepted from worker vector upserts."""

    model_config = ConfigDict(extra="ignore")

    file_path: str
    content_item_id: str | None = None
    text: str
    chunk_index: int = 0
    page_numbers: list[int] | None = None
    headings: list[str] | None = None
    images: list[str] | None = None
    doc_refs: list[str] | None = None
    index_version: str


class VectorPoint(BaseModel):
    """Vector upsert payload model."""

    model_config = ConfigDict(extra="ignore")

    id: str
    vector: list[float]
    payload: WorkerVectorPointPayload


class UpsertRequest(BaseModel):
    """Request model for vector upserts."""

    points: list[VectorPoint]
    folder_uuid: str
