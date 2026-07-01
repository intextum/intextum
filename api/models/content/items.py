"""File and folder models for the file browser."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContentItemType(str, Enum):
    """File type classification."""

    FILE = "file"
    FOLDER = "folder"
    SYMLINK = "symlink"


class ContentItemKind(str, Enum):
    """High-level content kind across connector types."""

    FILE = "file"
    FOLDER = "folder"
    EMAIL_MESSAGE = "email_message"
    ATTACHMENT = "attachment"


ContentReviewState = Literal["stale", "needs_review", "reviewed", "none"]

ContentReviewStatus = Literal["accepted", "corrected", "dismissed", "unreviewed"]
ContentClassificationDismissReason = Literal["not_a_document", "no_fitting_class"]
ContentExtractionDismissReasonInput = Literal["not_extractable", "schema_mismatch"]
ContentExtractionDismissReason = Literal[
    "not_extractable", "schema_mismatch", "no_class"
]


class ContentEnrichmentLifecycleInfo(BaseModel):
    """Lifecycle/status metadata for one enrichment result."""

    stale: bool = False
    reason: (
        Literal["missing_result", "missing_fingerprint", "config_changed"] | None
    ) = None
    current_enabled: bool = False
    current_config_fingerprint: str | None = None
    stored_config_fingerprint: str | None = None


class ContentEnrichmentReviewInfo(BaseModel):
    """Human review status and audit metadata for one enrichment part."""

    status: ContentReviewStatus = "unreviewed"
    reviewed: bool = False
    dismissed_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_by_sub: str | None = None
    reviewed_at: datetime | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class ContentClassificationResult(BaseModel):
    """One typed document classification result."""

    status: Literal["completed", "skipped", "failed"] | None = None
    label: str | None = None
    class_id: str | None = None
    confidence: float | None = None
    provider: str | None = None
    model: str | None = None
    config_fingerprint: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] | None = None
    error: str | None = None


class ContentClassificationView(ContentClassificationResult):
    """Effective document classification plus typed review metadata."""

    source: Literal["system", "user_override"] = "system"
    system: ContentClassificationResult | None = None
    review: ContentEnrichmentReviewInfo = Field(
        default_factory=ContentEnrichmentReviewInfo
    )
    review_status: ContentReviewStatus = "unreviewed"
    reviewed: bool = False
    dismissed_reason: ContentClassificationDismissReason | None = None
    needs_review: bool = False
    review_reasons: list[dict[str, Any]] = Field(default_factory=list)


class ContentExtractionResult(BaseModel):
    """One typed structured extraction result."""

    status: Literal["completed", "skipped", "failed"] | None = None
    schema_id: str | None = None
    schema_name: str | None = None
    schema_version: int | None = None
    document_class_id: str | None = None
    document_class: str | None = None
    provider: str | None = None
    model: str | None = None
    config_fingerprint: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    fields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None
    error: str | None = None


class ContentExtractionView(ContentExtractionResult):
    """Effective structured extraction plus typed review metadata."""

    source: Literal["system", "user_override"] = "system"
    system: ContentExtractionResult | None = None
    review: ContentEnrichmentReviewInfo = Field(
        default_factory=ContentEnrichmentReviewInfo
    )
    review_status: ContentReviewStatus = "unreviewed"
    reviewed: bool = False
    dismissed_reason: ContentExtractionDismissReason | None = None
    needs_review: bool = False


class ContentEnrichmentView(BaseModel):
    """Combined typed enrichment state for one content item."""

    review_state: ContentReviewState = "none"
    classification_lifecycle: ContentEnrichmentLifecycleInfo | None = None
    extraction_lifecycle: ContentEnrichmentLifecycleInfo | None = None
    classification_review_status: ContentReviewStatus | None = None
    extraction_review_status: ContentReviewStatus | None = None


class ContentItemProcessingModeSummary(BaseModel):
    """Structured summary of how the latest processing run was executed."""

    mode: Literal[
        "full",
        "enrichment_only",
    ]
    enrichment_only: bool = False
    document_enrichment: bool = False


class ContentProcessingTaskInfo(BaseModel):
    """Queue task details for the current or latest processing run."""

    id: str
    task_type: str
    content_kind: str | None = None
    status: str
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ContentItemFileDetails(BaseModel):
    """Optional file-specific metadata for one content item."""

    checksum: str | None = None
    symlink_target_path: str | None = None
    page_count: int | None = None
    media_duration_ms: int | None = None
    image_width: int | None = None
    image_height: int | None = None


class ContentItemFolderDetails(BaseModel):
    """Optional folder-specific metadata for one content item."""

    child_count: int | None = None
    supports_children: bool = True


class ContentItemEmailMessageDetails(BaseModel):
    """Optional email-message metadata for one content item."""

    message_id_header: str | None = None
    thread_id: str | None = None
    subject: str = ""
    from_name: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    cc_addresses: list[str] = Field(default_factory=list)
    bcc_addresses: list[str] = Field(default_factory=list)
    reply_to_addresses: list[str] = Field(default_factory=list)
    sent_at: datetime | None = None
    received_at: datetime | None = None
    body_text: str | None = None
    body_html: str | None = None
    snippet: str | None = None
    has_attachments: bool = False


class ContentItemAttachmentDetails(BaseModel):
    """Optional attachment metadata for one content item."""

    email_message_content_item_id: str | None = None
    content_id_header: str | None = None
    disposition: str | None = None
    is_inline: bool = False
    attachment_index: int | None = None


class ContentItemRelationSummary(BaseModel):
    """Compact related-item projection for parent/child navigation."""

    id: str
    display_name: str
    path: str
    kind: ContentItemKind
    mime_type: str | None = None


class ContentItemCapabilities(BaseModel):
    """Kind-aware capabilities for one content item."""

    supports_chunking: bool = False
    supports_search: bool = False
    supports_enrichment: bool = False
    supports_review: bool = False


class ContentItemInfo(BaseModel):
    """Information about a single file."""

    id: str
    name: str
    display_name: str
    path: str
    kind: ContentItemKind = ContentItemKind.FILE
    type: ContentItemType = ContentItemType.FILE
    parent_content_item_id: str | None = None
    container_content_item_id: str | None = None
    external_id: str | None = None
    extension: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: int = 0
    size_human: str = "0 B"
    modified_at: datetime
    created_at: Optional[datetime] = None
    accessed_at: Optional[datetime] = None
    is_container: bool = False
    is_hidden: bool = False
    is_symlink: bool = False
    inode: Optional[int] = None
    file_details: ContentItemFileDetails | None = None
    folder_details: ContentItemFolderDetails | None = None
    email_message_details: ContentItemEmailMessageDetails | None = None
    attachment_details: ContentItemAttachmentDetails | None = None
    capabilities: ContentItemCapabilities = Field(
        default_factory=ContentItemCapabilities
    )
    parent_item: ContentItemRelationSummary | None = None
    child_items: list[ContentItemRelationSummary] = Field(default_factory=list)

    # Processing status
    status: Optional[str] = (
        None  # QUEUED, PROCESSING, RETRYING, COMPLETED, FAILED, REVOKED
    )
    processing_stage: Optional[str] = None  # Live worker stage while PROCESSING
    processing_error: Optional[str] = None

    # Processing metadata
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None  # worker ID
    processing_duration_ms: Optional[int] = None
    processing_mode: ContentItemProcessingModeSummary | None = None
    processing_task: ContentProcessingTaskInfo | None = None
    last_processing_config: dict[str, Any] | None = None
    review_state: ContentReviewState = "none"
    immutable: bool = False
    document_classification: ContentClassificationView | None = None
    document_extraction: ContentExtractionView | None = None
    document_enrichment: ContentEnrichmentView | None = None


class FolderInfo(BaseModel):
    """Information about a folder."""

    id: str
    name: str
    display_name: str
    path: str
    kind: ContentItemKind = ContentItemKind.FOLDER
    type: ContentItemType = ContentItemType.FOLDER
    parent_content_item_id: str | None = None
    container_content_item_id: str | None = None
    external_id: str | None = None
    mime_type: str | None = None
    modified_at: datetime
    item_count: int = 0
    total_size_bytes: int = 0
    is_container: bool = True
    folder_details: ContentItemFolderDetails | None = None


class ContentItemTreeNode(BaseModel):
    """Node in a file tree structure."""

    id: str
    name: str
    display_name: str | None = None
    path: str
    kind: ContentItemKind
    type: ContentItemType
    children: Optional[list["ContentItemTreeNode"]] = None
    is_expanded: bool = False
    has_children: bool = False

    # Optional details (loaded on demand)
    details: Optional[ContentItemInfo | FolderInfo] = None


class ContentItemListResponse(BaseModel):
    """Response for file listing endpoints."""

    path: str
    parent_path: Optional[str] = None
    folders: list[FolderInfo] = Field(default_factory=list)
    files: list[ContentItemInfo] = Field(default_factory=list)
    total_items: int = 0
    total_size_bytes: int = 0
    immutable: bool = False


class FlatContentItemListResponse(BaseModel):
    """Response for flat file listing (all files across all folders)."""

    files: list[ContentItemInfo]
    total: int
    limit: int
    offset: int
    has_more: bool
    document_class_facets: list["DocumentClassFacet"] = Field(default_factory=list)
    extraction_schema_facets: list["ExtractionSchemaFacet"] = Field(
        default_factory=list
    )
    extraction_schema_field_facets: list["ExtractionSchemaFieldFacet"] = Field(
        default_factory=list
    )
    extraction_field_facets: list["ExtractionFieldFacet"] = Field(default_factory=list)
    extraction_value_facets: list["ExtractionValueFacet"] = Field(default_factory=list)
    review_reason_facets: list["ReviewReasonFacet"] = Field(default_factory=list)
    review_summary: "ReviewQueueSummary" = Field(
        default_factory=lambda: ReviewQueueSummary()
    )


class DocumentClassFacet(BaseModel):
    """Facet count for an effective document classification label."""

    label: str
    count: int


class ExtractionSchemaFacet(BaseModel):
    """Facet count for an effective extraction schema."""

    schema_name: str
    count: int


class ExtractionFieldFacet(BaseModel):
    """Facet count for an effective extracted field name."""

    field: str
    count: int


class ExtractionSchemaFieldFacet(BaseModel):
    """Coverage metadata for one filterable leaf in the selected extraction schema.

    ``label`` is the human path (e.g. ``line_items[].amount``) and ``segments``
    is the structured JSON path used to build field predicates.
    """

    field: str
    label: str = ""
    segments: list[dict[str, Any]] = Field(default_factory=list)
    dtype: Literal[
        "str", "int", "float", "bool", "list", "date", "currency", "object_list"
    ]
    description: str = ""
    required: bool = False
    count: int
    total: int


class ExtractionValueFacet(BaseModel):
    """Facet count for an effective extracted field value."""

    value: str
    count: int


class ReviewReasonFacet(BaseModel):
    """Facet count for one effective enrichment review reason."""

    reason: Literal["missing_required_fields", "conflicted_fields", "missing_evidence"]
    count: int


class ReviewQueueSummary(BaseModel):
    """Summary counts for the currently matched review queue."""

    total: int = 0
    unreviewed: int = 0
    accepted: int = 0
    corrected: int = 0
    dismissed: int = 0
    needs_review: int = 0
    missing_required_fields: int = 0
    conflicted_fields: int = 0
    missing_evidence: int = 0


class ContentTreeResponse(BaseModel):
    """Response for file tree endpoints."""

    root: ContentItemTreeNode
    depth: int = 1
    immutable: bool = False


class ChunkInfo(BaseModel):
    """Information about a single vector database chunk."""

    chunk_index: int
    text: Optional[str] = None
    page_numbers: list[int] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    word_count: int = 0
    char_count: int = 0


class ContentItemChunksResponse(BaseModel):
    """Response for file chunks endpoint."""

    file_path: str
    chunks: list[ChunkInfo] = Field(default_factory=list)
    total_chunks: int = 0
    is_indexed: bool = False


class ExtractedAsset(BaseModel):
    """Single extracted asset image."""

    name: str
    path: str
    type: str  # "figure" or "table"
    size_bytes: int = 0
    classification: Optional[str] = None
    description: Optional[str] = None


class ExtractedAssetsResponse(BaseModel):
    """Response for extracted assets endpoint."""

    file_path: str
    extracted_dir: Optional[str] = None
    figures: list[ExtractedAsset] = Field(default_factory=list)
    tables: list[ExtractedAsset] = Field(default_factory=list)
    has_extracted_content: bool = False
    has_docling_document: bool = False


class BatchProcessRequest(BaseModel):
    """Request model for batch file processing."""

    directory_path: str | None = None
    paths: list[str] | None = None
    processing_config: dict[str, Any] | None = None


class FilteredBatchProcessRequest(BaseModel):
    """Request model for batch processing files selected by flat-list filters."""

    name: str | None = None
    name_regex: bool = False
    search_path: bool = False
    path: str | None = None
    content_kind: ContentItemKind | None = None
    extension: str | None = None
    status: str | None = None
    document_class: str | None = None
    extraction_schema: str | None = None
    extraction_field: str | None = None
    extraction_value: str | None = None
    extraction_value_number_min: float | None = None
    extraction_value_number_max: float | None = None
    extraction_value_date_from: date | None = None
    extraction_value_date_to: date | None = None
    field_filters: str | None = None
    review_status: ContentReviewStatus | None = None
    review_reason: (
        Literal["missing_required_fields", "conflicted_fields", "missing_evidence"]
        | None
    ) = None
    needs_review: bool = False
    stale_enrichment: bool = False
    processing_config: dict[str, Any] | None = None


class ContentReviewSubmitRequest(BaseModel):
    """Unified per-file review payload for classification and extraction."""

    classification_label: str | None = Field(default=None, min_length=1, max_length=120)
    classification_dismissed: bool | None = None
    classification_dismiss_reason: ContentClassificationDismissReason | None = None
    classification_reset: bool | None = None
    extraction_data: dict[str, Any] | None = None
    extraction_dismissed: bool | None = None
    extraction_dismiss_reason: ContentExtractionDismissReasonInput | None = None
    extraction_reset: bool | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContentVerifyClassRequest(BaseModel):
    """Payload for changing the effective document class before verification."""

    classification_label: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContentVerifyClassResponse(BaseModel):
    """Response after storing an unconfirmed class change and optional extraction task."""

    content_item: ContentItemInfo
    task_id: str | None = None
