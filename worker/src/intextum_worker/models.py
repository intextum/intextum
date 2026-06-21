"""Data models for the worker service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomConfig(BaseModel):
    """Custom configuration for document processing."""

    do_ocr: bool = True
    do_table_structure: bool = True
    force_full_page_ocr: bool = False
    ocr_lang: str | list[str] | None = None
    table_structure_mode: str | None = None
    images_scale: float | None = 2
    image_export_dpi: int = 300


class WebhookPayload(BaseModel):
    """Payload for document processing webhooks."""

    model_config = ConfigDict(extra="ignore")

    document_url: str
    document_type: str | None = None
    event_type: str | None = None


class WorkerInlineDocumentSource(BaseModel):
    """Inline document body materialized locally before Docling processing."""

    model_config = ConfigDict(extra="ignore")

    format: Literal["html", "md"]
    content: str


class WorkerTaskMetadata(BaseModel):
    """Subset of task metadata used directly by the worker runtime."""

    model_config = ConfigDict(extra="ignore")

    content_item_id: str | None = None
    processing_config: dict[str, Any] | None = None
    inline_document_source: WorkerInlineDocumentSource | None = None
    training_job_id: str | None = None
    registry_model_id: str | None = None
    target_kind: Literal["classification"] | None = None
    training_method: Literal["lora"] | None = None
    base_model: str | None = None
    target_name: str | None = None
    config_fingerprint: str | None = None
    reviewed_example_count: int | None = None
    config_snapshot: dict[str, Any] | None = None


class WorkerContentEnrichmentTrainingExample(BaseModel):
    """One reviewed GLiNER2 training example fetched from the backend."""

    model_config = ConfigDict(extra="ignore")

    content_item_id: str
    relative_path: str
    input: str
    output: dict[str, Any]
    review_status: Literal["accepted", "corrected"]
    reviewed_at: str | None = None
    reviewed_by: str | None = None


class WorkerContentEnrichmentTrainingDataset(BaseModel):
    """Worker-authenticated training dataset export for one queued adapter job."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    training_job_id: str
    registry_model_id: str
    target_kind: Literal["classification"]
    training_method: Literal["lora"] = "lora"
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    config_snapshot: dict[str, Any] | None = None
    examples: list[WorkerContentEnrichmentTrainingExample] = Field(default_factory=list)


class WorkerContentEnrichmentSourceChunk(BaseModel):
    """One stored backend chunk reused for enrichment-only reruns."""

    model_config = ConfigDict(extra="ignore")

    chunk_index: int = 0
    text: str
    page_numbers: list[int] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    captions: list[str] = Field(default_factory=list)


class WorkerContentEnrichmentTaskSource(BaseModel):
    """Worker-authenticated chunk/text source for one claimed rerun task."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    content_item_id: str
    relative_path: str
    current_document_class: str | None = None
    chunks: list[WorkerContentEnrichmentSourceChunk] = Field(default_factory=list)


class WorkerContentEnrichmentChunkSearchQuery(BaseModel):
    """One semantic query used to select chunks for extraction."""

    model_config = ConfigDict(extra="ignore")

    key: str
    text: str


class WorkerContentEnrichmentChunkSearchRequest(BaseModel):
    """Task-bound semantic chunk search request."""

    model_config = ConfigDict(extra="ignore")

    queries: list[WorkerContentEnrichmentChunkSearchQuery] = Field(default_factory=list)
    limit_per_query: int = 5
    final_limit: int = 40


class WorkerContentEnrichmentSelectedChunk(WorkerContentEnrichmentSourceChunk):
    """One selected chunk with semantic match metadata."""

    score: float | None = None
    matched_queries: list[str] = Field(default_factory=list)


class WorkerContentEnrichmentChunkSearchResponse(BaseModel):
    """Deduplicated semantic chunk search response."""

    model_config = ConfigDict(extra="ignore")

    chunks: list[WorkerContentEnrichmentSelectedChunk] = Field(default_factory=list)


class WorkerContentEnrichmentRegistryModel(BaseModel):
    """Worker-facing metadata for one ready registry-backed adapter."""

    model_config = ConfigDict(extra="ignore")

    id: str
    target_kind: Literal["classification"]
    training_method: Literal["lora"] = "lora"
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    artifact_path: str


class WorkerRuntimeConfig(BaseModel):
    """Worker-relevant runtime configuration fetched from the backend."""

    model_config = ConfigDict(extra="ignore")

    embedding_max_tokens: int
    embedding_model: str
    picture_description_prompt: str = ""
    picture_description_model: str | None = None
    picture_description_max_tokens: int = 512
    picture_description_timeout_seconds: float = 300.0
    document_classification_enabled: bool = False
    document_classification_provider: str = "gliner2"
    document_classification_model: str = "fastino/gliner2-multi-v1"
    document_classification_labels: list[WorkerDocumentClassificationLabel] = Field(
        default_factory=list
    )
    document_extraction_enabled: bool = False
    document_extraction_model: str = "fastino/gliner2-multi-v1"
    document_extraction_llm_model: str = "qwen3-vl:8b"
    document_extraction_llm_max_output_tokens: int = 16_384
    document_extraction_chunk_strategy: Literal["full", "selected"] = "full"
    document_extraction_chat_max_retries: int = 2
    document_extraction_chat_evidence_required: bool = True
    document_extraction_chat_full_text_threshold_chars: int = 20_000
    content_enrichment_stage_timeout_seconds: float = 300.0
    document_extraction_schema_models: dict[str, str] = Field(default_factory=dict)
    document_extraction_schemas: list[WorkerDocumentExtractionSchema] = Field(
        default_factory=list
    )
    document_extraction_max_chars: int = 12_000


class WorkerRuntimeMetadata(BaseModel):
    """Non-secret runtime details reported by the worker during startup."""

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


class WorkerDocumentClassificationLabel(BaseModel):
    """One configured document class label for GLiNER2 classification."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str
    version: int = Field(default=1, ge=1)
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


class WorkerDocumentExtractionChildField(BaseModel):
    """One child field inside a repeating structured extraction object."""

    model_config = ConfigDict(extra="ignore")

    name: str
    dtype: Literal["str", "int", "float", "bool", "list", "date", "currency"] = "str"
    description: str
    required: bool = False


class WorkerDocumentExtractionExample(BaseModel):
    """One few-shot example for a configured extraction field."""

    model_config = ConfigDict(extra="ignore")

    text: str
    value: Any = None
    extraction_text: str | None = None


class WorkerDocumentExtractionField(BaseModel):
    """One field definition inside a structured extraction schema."""

    model_config = ConfigDict(extra="ignore")

    name: str
    dtype: Literal[
        "str", "int", "float", "bool", "list", "date", "currency", "object_list"
    ] = "str"
    description: str
    required: bool = False
    fields: list[WorkerDocumentExtractionChildField] = Field(default_factory=list)
    examples: list[WorkerDocumentExtractionExample] = Field(default_factory=list)
    heading_aliases: list[str] = Field(default_factory=list)
    clustered_under_heading: bool = True


class WorkerDocumentExtractionSceneExtraction(BaseModel):
    """One grounded row inside a shared multi-field example scene."""

    model_config = ConfigDict(extra="ignore")

    field: str
    extraction_text: str
    value: Any = None


class WorkerDocumentExtractionScene(BaseModel):
    """One shared passage with multiple anchored extractions across fields."""

    model_config = ConfigDict(extra="ignore")

    text: str
    extractions: list[WorkerDocumentExtractionSceneExtraction] = Field(
        default_factory=list
    )


class WorkerDocumentExtractionSchema(BaseModel):
    """One configured structured extraction schema."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str
    version: int = Field(default=1, ge=1)
    document_class_id: str = ""
    document_class: str
    description: str = ""
    fields: list[WorkerDocumentExtractionField] = Field(default_factory=list)
    scenes: list[WorkerDocumentExtractionScene] = Field(default_factory=list)
    section_boundary_terms: list[str] = Field(default_factory=list)


class WorkerDocumentEvidence(BaseModel):
    """Grounding metadata for one classification or extraction hit."""

    model_config = ConfigDict(extra="ignore")

    chunk_index: int | None = None
    page_numbers: list[int] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    snippet: str | None = None
    score: float | None = None
    matched_queries: list[str] = Field(default_factory=list)
    source: str | None = None


class WorkerDocumentExtractionFieldResult(BaseModel):
    """Resolved value plus evidence for one extracted field."""

    model_config = ConfigDict(extra="ignore")

    value: Any = None
    dtype: Literal[
        "str", "int", "float", "bool", "list", "date", "currency", "object_list"
    ] = "str"
    required: bool = False
    evidence: list[WorkerDocumentEvidence] = Field(default_factory=list)
    item_evidence: list[list[WorkerDocumentEvidence]] = Field(default_factory=list)
    candidate_values: list[Any] = Field(default_factory=list)
    conflict: bool = False
    confidence: float | None = None
    validation_errors: list[str] = Field(default_factory=list)
    missing_reason: str | None = None
    items_without_evidence: int = 0


class WorkerDocumentExtractionSummary(BaseModel):
    """Small review-oriented summary for one extraction result."""

    model_config = ConfigDict(extra="ignore")

    missing_required_fields: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    conflicted_fields: list[str] = Field(default_factory=list)
    fields_without_evidence: list[str] = Field(default_factory=list)
    fields_with_evidence: int = 0
    needs_review: bool = False


class WorkerDocumentClassificationResult(BaseModel):
    """Normalized worker-side document classification result."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["completed", "skipped", "failed"]
    source: str | None = None
    provider: str | None = None
    model: str | None = None
    class_id: str | None = None
    label: str | None = None
    confidence: float | None = None
    evidence: list[WorkerDocumentEvidence] = Field(default_factory=list)
    raw_output: dict[str, Any] | None = None
    error: str | None = None


class WorkerDocumentExtractionResult(BaseModel):
    """Normalized worker-side structured extraction result."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["completed", "skipped", "failed"]
    provider: str | None = None
    model: str | None = None
    schema_id: str | None = None
    schema_name: str | None = None
    schema_version: int | None = None
    document_class_id: str | None = None
    document_class: str | None = None
    data: dict[str, Any] | list[Any] | None = None
    fields: dict[str, WorkerDocumentExtractionFieldResult] = Field(default_factory=dict)
    summary: WorkerDocumentExtractionSummary | None = None
    raw_output: dict[str, Any] | None = None
    error: str | None = None


class WorkerTextsRequest(BaseModel):
    """Request payload for text-based worker proxy endpoints."""

    texts: list[str]


class WorkerApiStatusResponse(BaseModel):
    """Simple API acknowledgement payload."""

    model_config = ConfigDict(extra="ignore")

    status: str


class WorkerContentItemMetadata(BaseModel):
    """Metadata for one source content item resolved via the backend."""

    model_config = ConfigDict(extra="ignore")

    content_item_id: str
    size_bytes: int | None = None
    modified_time: float | None = None
    created_time: float | None = None
    permissions: str | None = None
    owner_id: int | None = None
    group_id: int | None = None
    access_time: float | None = None
    is_symlink: bool | None = None
    file_extension: str | None = None


class WorkerDownloadedSourceFile(BaseModel):
    """Locally downloaded copy of one backend source file."""

    model_config = ConfigDict(extra="ignore")

    relative_path: str
    local_path: Path
    content_item_id: str | None = None

    def resolve_output_dir(self, work_dir: str | Path) -> Path | None:
        """Return the extracted-output directory for this file when content_item_id is known."""
        if not self.content_item_id:
            return None
        return Path(work_dir) / "output" / self.content_item_id


class WorkerClaimTaskRequest(BaseModel):
    """Request payload for claiming the next worker task."""

    capabilities: list[str]


class WorkerCompleteTaskRequest(BaseModel):
    """Request payload for marking a task complete."""

    task_secret: str
    processing_config: dict[str, object] | None = None
    document_classification: WorkerDocumentClassificationResult | None = None
    document_extraction: WorkerDocumentExtractionResult | None = None


class WorkerCompleteContentEnrichmentTrainingTaskRequest(BaseModel):
    """Request payload for completing a training task with registry metadata."""

    task_secret: str
    artifact_path: str
    metrics: dict[str, object] | None = None


class WorkerContentEnrichmentTrainingArtifactUploadResponse(BaseModel):
    """Response payload for uploading one training artifact bundle."""

    model_config = ConfigDict(extra="ignore")

    status: str
    registry_model_id: str
    artifact_path: str
    size: int


class WorkerTaskSecretRequest(BaseModel):
    """Request payload containing only the per-task secret."""

    task_secret: str


class WorkerHeartbeatRequest(BaseModel):
    """Request payload for a task heartbeat, optionally carrying the live stage."""

    task_secret: str
    stage: str | None = None


class WorkerFailTaskRequest(BaseModel):
    """Request payload for reporting task failure."""

    task_secret: str
    error_message: str


class WorkerAbortTaskRequest(BaseModel):
    """Request payload for explicitly aborting a task."""

    task_secret: str
    reason: str


class WorkerTaskFailureResult(BaseModel):
    """Result payload for one reported task failure."""

    model_config = ConfigDict(extra="ignore")

    requeued: bool
    retry_count: int
    new_task_secret: str | None = None


class WorkerUploadedFile(BaseModel):
    """One uploaded extracted file entry returned by the backend."""

    model_config = ConfigDict(extra="ignore")

    path: str
    size: int


class WorkerUploadFileResponse(BaseModel):
    """Response payload for uploading one extracted file."""

    model_config = ConfigDict(extra="ignore")

    status: str
    path: str
    size: int


class WorkerUploadBatchResponse(BaseModel):
    """Response payload for uploading a batch of extracted files."""

    model_config = ConfigDict(extra="ignore")

    status: str
    content_item_id: str
    uploaded: int
    files: list[WorkerUploadedFile] = Field(default_factory=list)


class WorkerUploadDirectoryResult(BaseModel):
    """Aggregated result for uploading all extracted files in a directory."""

    model_config = ConfigDict(extra="ignore")

    content_item_id: str
    uploaded: int
    files: list[WorkerUploadedFile] = Field(default_factory=list)
    batches: list[WorkerUploadBatchResponse] = Field(default_factory=list)


class WorkerSupersededStatus(BaseModel):
    """Supersession check response for an active task."""

    model_config = ConfigDict(extra="ignore")

    superseded: bool


class WorkerEmbeddingsResponse(BaseModel):
    """Embedding generation response payload."""

    model_config = ConfigDict(extra="ignore")

    embeddings: list[list[float]]


class WorkerTokenCountResponse(BaseModel):
    """Token-count response payload."""

    model_config = ConfigDict(extra="ignore")

    counts: list[int]


class WorkerVectorUpsertResponse(BaseModel):
    """Vector upsert acknowledgement payload."""

    model_config = ConfigDict(extra="ignore")

    status: str
    upserted: int


class WorkerVectorDeleteResponse(BaseModel):
    """Vector delete acknowledgement payload."""

    model_config = ConfigDict(extra="ignore")

    status: str
    deleted: int


class WorkerProcessorContext(BaseModel):
    """Normalized processor input for one claimed task."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    folder_uuid: str
    task_secret: str
    content_item_id: str | None = None
    metadata: WorkerTaskMetadata = Field(default_factory=WorkerTaskMetadata)

    @property
    def resolved_file_id(self) -> str | None:
        """Return the best available backend file identifier."""
        if self.content_item_id:
            return self.content_item_id
        return self.metadata.content_item_id

    def require_file_id(self) -> str:
        """Return the backend file identifier or raise when unavailable."""
        content_item_id = self.resolved_file_id
        if not content_item_id:
            raise ValueError("metadata.content_item_id is required")
        return content_item_id

    def processing_metadata(self) -> dict[str, Any]:
        """Return context metadata normalized for processor and vector calls."""
        payload = self.metadata.model_dump(exclude_none=True)
        content_item_id = self.resolved_file_id
        if content_item_id:
            payload["content_item_id"] = content_item_id
        return payload


class WorkerVectorChunkPayload(BaseModel):
    """Structured payload stored for one vectorized chunk."""

    model_config = ConfigDict(extra="allow")

    file_path: str
    source: Literal["file_system"] = "file_system"
    text: str
    chunk_index: int
    index_version: str
    headings: list[str] | None = None
    page_numbers: list[int] | None = None
    images: list[str] | None = None
    doc_refs: list[str] | None = None

    def to_request_payload(
        self, metadata: dict[str, Any] | None = None
    ) -> WorkerVectorChunkPayload:
        """Return a request-ready payload merged with metadata without clobbering chunk fields."""
        payload = self.model_dump(exclude_none=True)
        if metadata:
            for key, value in metadata.items():
                payload.setdefault(key, value)
        return WorkerVectorChunkPayload.model_validate(payload)


class WorkerVectorPoint(BaseModel):
    """Structured vector upsert point for one chunk embedding."""

    id: str
    vector: list[float]
    payload: WorkerVectorChunkPayload

    def to_request_point(
        self, metadata: dict[str, Any] | None = None
    ) -> WorkerVectorPoint:
        """Return a request-ready point merged with any file-level metadata."""
        return WorkerVectorPoint(
            id=self.id,
            vector=self.vector,
            payload=self.payload.to_request_payload(metadata=metadata),
        )


class WorkerVectorUpsertRequest(BaseModel):
    """Request payload for vector upserts."""

    points: list[WorkerVectorPoint]
    folder_uuid: str


class WorkerVectorDeleteRequest(BaseModel):
    """Request payload for deleting vector points by file path."""

    file_path: str
    folder_uuid: str
    content_item_id: str | None = None
    exclude_version: str | None = None


class WorkerClaimedTask(BaseModel):
    """Claimed task payload returned by the backend task queue."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    task_type: Literal[
        "process",
        "train_content_enrichment_model",
    ]
    content_kind: Literal["document", "image", "video", "training"] | None = None
    content_item_id: str | None = None
    folder_uuid: str
    relative_path: str
    metadata: WorkerTaskMetadata = Field(default_factory=WorkerTaskMetadata)
    task_secret: str
    retry_count: int = 0

    def processing_metadata(self) -> dict[str, Any]:
        """Return task metadata normalized for processor calls."""
        return self.processor_context().processing_metadata()

    def processor_context(self) -> WorkerProcessorContext:
        """Build the normalized processor context for this task."""
        return WorkerProcessorContext(
            task_id=self.task_id,
            folder_uuid=self.folder_uuid,
            task_secret=self.task_secret,
            content_item_id=self.content_item_id,
            metadata=self.metadata,
        )


WorkerTaskMetadata.model_rebuild()
WorkerProcessorContext.model_rebuild()
WorkerClaimedTask.model_rebuild()
WorkerRuntimeConfig.model_rebuild()
