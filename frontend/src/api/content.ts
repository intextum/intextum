import { apiUrl, httpClient, httpFetch } from "./client.ts";

export interface ContentItemInfo {
  id: string;
  name: string;
  display_name: string;
  path: string;
  kind: ContentItemKind;
  type: "file" | "folder" | "symlink";
  parent_content_item_id?: string | null;
  container_content_item_id?: string | null;
  external_id?: string | null;
  extension?: string;
  mime_type?: string | null;
  size_bytes: number;
  size_human: string;
  modified_at: string;
  created_at?: string;
  is_container?: boolean;
  is_hidden: boolean;
  status?: string; // QUEUED, PROCESSING, RETRYING, COMPLETED, FAILED, REVOKED
  processing_stage?: string | null; // Live worker stage while PROCESSING
  processing_error?: string;
  processed_at?: string;
  processed_by?: string;
  processing_duration_ms?: number;
  processing_mode?: ContentItemProcessingModeSummary | null;
  processing_task?: ContentProcessingTaskInfo | null;
  last_processing_config?: Record<string, unknown> | null;
  review_state?: "stale" | "needs_review" | "reviewed" | "none";
  immutable?: boolean;
  document_classification?: ContentClassificationView | null;
  document_extraction?: ContentExtractionView | null;
  document_enrichment?: ContentEnrichmentView | null;
  file_details?: ContentItemFileDetails | null;
  folder_details?: ContentItemFolderDetails | null;
  email_message_details?: ContentItemEmailMessageDetails | null;
  attachment_details?: ContentItemAttachmentDetails | null;
  capabilities?: ContentItemCapabilities | null;
  parent_item?: ContentItemRelationSummary | null;
  child_items?: ContentItemRelationSummary[];
}

export type ContentItemKind = "file" | "folder" | "email_message" | "attachment";

export type ContentReviewStatus = "accepted" | "corrected" | "dismissed" | "unreviewed";

export type ContentClassificationDismissReason = "not_a_document" | "no_fitting_class";

export type ContentExtractionDismissReason = "not_extractable" | "schema_mismatch" | "no_class";

export interface ContentEnrichmentReviewInfo {
  status: ContentReviewStatus;
  reviewed: boolean;
  dismissed_reason?: string | null;
  reviewed_by?: string | null;
  reviewed_by_sub?: string | null;
  reviewed_at?: string | null;
  history: Record<string, unknown>[];
}

export interface ContentProcessingTaskInfo {
  id: string;
  task_type: string;
  content_kind?: string | null;
  status: string;
  claimed_by?: string | null;
  claimed_at?: string | null;
  retry_count: number;
  max_retries: number;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ContentClassificationResult {
  label?: string | null;
  class_id?: string | null;
  confidence?: number | null;
  score?: number | null;
  probability?: number | null;
  model?: string | null;
  config_fingerprint?: string | null;
  evidence?: Record<string, unknown>[];
  raw?: Record<string, unknown> | null;
}

export interface ContentClassificationView extends ContentClassificationResult {
  source?: "system" | "user_override";
  system?: ContentClassificationResult | null;
  review?: ContentEnrichmentReviewInfo;
  review_status?: ContentReviewStatus;
  reviewed?: boolean;
  dismissed_reason?: ContentClassificationDismissReason | null;
  needs_review?: boolean;
  review_reasons?: Record<string, unknown>[];
}

export interface ContentExtractionResult {
  schema_id?: string | null;
  schema_name?: string | null;
  schema_version?: number | null;
  document_class_id?: string | null;
  document_class?: string | null;
  model?: string | null;
  config_fingerprint?: string | null;
  data?: Record<string, unknown>;
  fields?: Record<string, Record<string, unknown>>;
  summary?: Record<string, unknown>;
  raw?: Record<string, unknown> | null;
}

export interface ContentExtractionView extends ContentExtractionResult {
  source?: "system" | "user_override";
  system?: ContentExtractionResult | null;
  review?: ContentEnrichmentReviewInfo;
  review_status?: ContentReviewStatus;
  reviewed?: boolean;
  dismissed_reason?: ContentExtractionDismissReason | null;
  needs_review?: boolean;
}

export interface ContentEnrichmentView {
  review_state: "stale" | "needs_review" | "reviewed" | "none";
  classification_lifecycle?: ContentEnrichmentLifecycleInfo | null;
  extraction_lifecycle?: ContentEnrichmentLifecycleInfo | null;
  classification_review_status?: ContentReviewStatus | null;
  extraction_review_status?: ContentReviewStatus | null;
}

export interface ContentItemFileDetails {
  checksum?: string | null;
  symlink_target_path?: string | null;
  page_count?: number | null;
  media_duration_ms?: number | null;
  image_width?: number | null;
  image_height?: number | null;
}

export interface ContentItemFolderDetails {
  child_count?: number | null;
  supports_children: boolean;
}

export interface ContentItemEmailMessageDetails {
  message_id_header?: string | null;
  thread_id?: string | null;
  subject: string;
  from_name?: string | null;
  from_address?: string | null;
  to_addresses: string[];
  cc_addresses: string[];
  bcc_addresses: string[];
  reply_to_addresses: string[];
  sent_at?: string | null;
  received_at?: string | null;
  body_text?: string | null;
  body_html?: string | null;
  snippet?: string | null;
  has_attachments: boolean;
}

export interface ContentItemAttachmentDetails {
  email_message_content_item_id?: string | null;
  content_id_header?: string | null;
  disposition?: string | null;
  is_inline: boolean;
  attachment_index?: number | null;
}

export interface ContentItemRelationSummary {
  id: string;
  display_name: string;
  path: string;
  kind: ContentItemKind;
  mime_type?: string | null;
}

export interface ContentItemCapabilities {
  supports_chunking: boolean;
  supports_search: boolean;
  supports_enrichment: boolean;
  supports_review: boolean;
}

export interface ContentEnrichmentLifecycleInfo {
  stale: boolean;
  reason?: "missing_result" | "missing_fingerprint" | "config_changed" | null;
  current_enabled?: boolean;
  current_config_fingerprint?: string | null;
  stored_config_fingerprint?: string | null;
}

export interface ContentItemProcessingModeSummary {
  mode: "full" | "enrichment_only";
  enrichment_only: boolean;
  document_enrichment: boolean;
}

export interface ContentReviewSubmitPayload {
  classification_label?: string | null;
  classification_dismissed?: boolean | null;
  classification_dismiss_reason?: ContentClassificationDismissReason | null;
  extraction_data?: Record<string, unknown> | null;
  extraction_dismissed?: boolean | null;
  extraction_dismiss_reason?: Exclude<ContentExtractionDismissReason, "no_class"> | null;
}

export interface ContentVerifyClassPayload {
  classification_label: string;
}

export interface ContentVerifyClassResponse {
  content_item: ContentItemInfo;
  task_id?: string | null;
}

export interface ContentAuditEventInfo {
  id: string;
  content_item_id: string;
  connector_uuid?: string | null;
  relative_path?: string | null;
  display_name?: string | null;
  event_type: string;
  event_group: string;
  status: string;
  summary: string;
  metadata: Record<string, unknown>;
  actor_sub?: string | null;
  actor_name?: string | null;
  source: string;
  created_at: string;
}

export interface ContentAuditEventListResponse {
  events: ContentAuditEventInfo[];
  total: number;
  limit: number;
  offset: number;
}

export interface FolderInfo {
  id: string;
  name: string;
  display_name: string;
  path: string;
  kind: "folder";
  type: "folder";
  parent_content_item_id?: string | null;
  container_content_item_id?: string | null;
  external_id?: string | null;
  mime_type?: string | null;
  modified_at: string;
  item_count: number;
  total_size_bytes: number;
  is_container?: boolean;
  folder_details?: ContentItemFolderDetails | null;
}

export interface ContentItemListResponse {
  path: string;
  parent_path?: string;
  folders: FolderInfo[];
  files: ContentItemInfo[];
  total_items: number;
  total_size_bytes: number;
  immutable?: boolean;
}

export interface ContentItemTreeNode {
  id: string;
  name: string;
  display_name?: string | null;
  path: string;
  kind: ContentItemKind;
  type: "file" | "folder" | "symlink";
  children?: ContentItemTreeNode[];
  is_expanded: boolean;
  has_children: boolean;
  details?: ContentItemInfo | FolderInfo;
}

export interface FlatContentItemListResponse {
  files: ContentItemInfo[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  document_class_facets?: DocumentClassFacet[];
  extraction_schema_facets?: ExtractionSchemaFacet[];
  extraction_schema_field_facets?: ExtractionSchemaFieldFacet[];
  extraction_field_facets?: ExtractionFieldFacet[];
  extraction_value_facets?: ExtractionValueFacet[];
  review_reason_facets?: ReviewReasonFacet[];
  review_summary?: ReviewQueueSummary;
}

export interface DocumentClassFacet {
  label: string;
  count: number;
}

export interface ExtractionSchemaFacet {
  schema_name: string;
  count: number;
}

export interface ExtractionFieldFacet {
  field: string;
  count: number;
}

export interface ExtractionSchemaFieldFacet {
  field: string;
  label: string;
  segments: ({ k: string } | { elem: true })[];
  dtype: "str" | "int" | "float" | "bool" | "list" | "date" | "currency" | "object_list";
  description: string;
  required: boolean;
  count: number;
  total: number;
}

export interface ExtractionValueFacet {
  value: string;
  count: number;
}

export type ContentEnrichmentReviewStatus = ContentReviewStatus;
export type ContentEnrichmentReviewReason =
  | "missing_required_fields"
  | "conflicted_fields"
  | "missing_evidence";

export interface AllFilesBatchFilters {
  name?: string;
  name_regex?: boolean;
  search_path?: boolean;
  /** Folder-prefixed path scoping results to one folder subtree. */
  path?: string;
  content_kind?: ContentItemKind;
  extension?: string;
  status?: string;
  document_class?: string;
  extraction_schema?: string;
  /** Focus field driving value-facet suggestions and schema-field coverage. */
  extraction_field?: string;
  /** JSON array of field predicates: [{field, op, value, value2, dtype}]. */
  field_filters?: string;
  review_status?: ContentEnrichmentReviewStatus;
  review_reason?: ContentEnrichmentReviewReason;
  needs_review?: boolean;
  stale_enrichment?: boolean;
}

function appendAllFilesBatchFilters(qp: URLSearchParams, params: AllFilesBatchFilters): void {
  if (params.name) qp.set("name", params.name);
  if (params.name && params.name_regex) qp.set("name_regex", "true");
  if (params.name && params.search_path) qp.set("search_path", "true");
  if (params.path) qp.set("path", params.path);
  if (params.content_kind) qp.set("content_kind", params.content_kind);
  if (params.extension) qp.set("extension", params.extension);
  if (params.status) qp.set("status", params.status);
  if (params.document_class) qp.set("document_class", params.document_class);
  if (params.extraction_schema) qp.set("extraction_schema", params.extraction_schema);
  if (params.extraction_field) qp.set("extraction_field", params.extraction_field);
  if (params.field_filters) qp.set("field_filters", params.field_filters);
  if (params.review_status) qp.set("review_status", params.review_status);
  if (params.review_reason) qp.set("review_reason", params.review_reason);
  if (params.needs_review) qp.set("needs_review", "true");
  if (params.stale_enrichment) qp.set("stale_enrichment", "true");
}

export interface ReviewReasonFacet {
  reason: ContentEnrichmentReviewReason;
  count: number;
}

export interface ReviewQueueSummary {
  total: number;
  unreviewed: number;
  accepted: number;
  corrected: number;
  needs_review: number;
  missing_required_fields: number;
  conflicted_fields: number;
  missing_evidence: number;
}

export interface SearchResult {
  score: number;
  file_path: string;
  content_item_id?: string | null;
  display_name?: string | null;
  content_kind?: ContentItemKind | null;
  email_from_address?: string | null;
  email_sent_at?: string | null;
  parent_display_name?: string | null;
  text?: string;
  chunk_index: number;
  page_numbers: number[];
  headings: string[];
  images: string[];
  doc_refs: string[];
  payload: Record<string, unknown>;
}

export interface ChunkInfo {
  chunk_index: number;
  text?: string;
  page_numbers: number[];
  headings: string[];
  images: string[];
  doc_refs: string[];
  word_count: number;
  char_count: number;
}

export interface ContentItemChunksResponse {
  file_path: string;
  chunks: ChunkInfo[];
  total_chunks: number;
  is_indexed: boolean;
}

export interface ExtractedAsset {
  name: string;
  path: string;
  type: "figure" | "table";
  size_bytes: number;
  classification?: string | null;
  description?: string | null;
}

export interface ExtractedAssetsResponse {
  file_path: string;
  extracted_dir?: string;
  figures: ExtractedAsset[];
  tables: ExtractedAsset[];
  has_extracted_content: boolean;
  has_docling_document: boolean;
}

export interface DataFolderInfo {
  uuid: string;
  name: string;
  watch: boolean;
  auto_process_new: boolean;
  immutable?: boolean;
}

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isFileType = (value: unknown): value is ContentItemInfo["type"] =>
  value === "file" || value === "folder" || value === "symlink";

const isContentKind = (value: unknown): value is ContentItemKind =>
  value === "file" || value === "folder" || value === "email_message" || value === "attachment";

const isFileInfo = (value: unknown): value is ContentItemInfo => {
  if (!isObjectRecord(value)) return false;

  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.display_name === "string" &&
    typeof value.path === "string" &&
    isContentKind(value.kind) &&
    isFileType(value.type) &&
    typeof value.size_bytes === "number" &&
    typeof value.size_human === "string" &&
    typeof value.modified_at === "string" &&
    typeof value.is_hidden === "boolean"
  );
};

const isFolderInfo = (value: unknown): value is FolderInfo => {
  if (!isObjectRecord(value)) return false;

  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.display_name === "string" &&
    typeof value.path === "string" &&
    value.kind === "folder" &&
    value.type === "folder" &&
    typeof value.modified_at === "string" &&
    typeof value.item_count === "number" &&
    typeof value.total_size_bytes === "number"
  );
};

const parseFileListResponse = (value: unknown): ContentItemListResponse => {
  if (!isObjectRecord(value)) {
    throw new Error("Invalid file list response: expected object");
  }

  const { path, parent_path, folders, files, total_items, total_size_bytes, immutable } = value;
  if (typeof path !== "string") {
    throw new Error("Invalid file list response: missing path");
  }
  if (parent_path !== undefined && parent_path !== null && typeof parent_path !== "string") {
    throw new Error("Invalid file list response: invalid parent_path");
  }
  if (!Array.isArray(folders) || !folders.every(isFolderInfo)) {
    throw new Error("Invalid file list response: invalid folders");
  }
  if (!Array.isArray(files) || !files.every(isFileInfo)) {
    throw new Error("Invalid file list response: invalid files");
  }
  if (typeof total_items !== "number" || typeof total_size_bytes !== "number") {
    throw new Error("Invalid file list response: invalid totals");
  }

  return {
    path,
    parent_path: parent_path ?? undefined,
    folders,
    files,
    total_items,
    total_size_bytes,
    immutable: typeof immutable === "boolean" ? immutable : false,
  };
};

// Custom API functions
export const contentApi = {
  listAll: async (
    params: AllFilesBatchFilters & {
      limit?: number;
      offset?: number;
      sort_by?: string;
      sort_order?: string;
    } = {},
  ): Promise<FlatContentItemListResponse> => {
    const qp = new URLSearchParams();
    if (params.limit !== undefined) qp.set("limit", String(params.limit));
    if (params.offset !== undefined) qp.set("offset", String(params.offset));
    if (params.sort_by) qp.set("sort_by", params.sort_by);
    if (params.sort_order) qp.set("sort_order", params.sort_order);
    appendAllFilesBatchFilters(qp, params);
    const qs = qp.toString();
    const { json } = await httpClient(`${apiUrl}/content/all${qs ? `?${qs}` : ""}`);
    return json;
  },

  listDirectory: async (
    path: string = "",
    includeHidden: boolean = false,
  ): Promise<ContentItemListResponse> => {
    const { json } = await httpClient(
      `${apiUrl}/content/?path=${encodeURIComponent(path)}&include_hidden=${includeHidden}`,
    );
    return parseFileListResponse(json);
  },

  getTree: async (
    path: string = "",
    depth: number = 1,
  ): Promise<{ root: ContentItemTreeNode; depth: number; immutable?: boolean }> => {
    const { json } = await httpClient(
      `${apiUrl}/content/tree?path=${encodeURIComponent(path)}&depth=${depth}`,
    );
    return json;
  },

  getDetails: async (path: string): Promise<ContentItemInfo> => {
    const { json } = await httpClient(`${apiUrl}/content/details/${encodeURIComponent(path)}`);
    return json;
  },

  getDetailsById: async (id: string): Promise<ContentItemInfo> => {
    const { json } = await httpClient(`${apiUrl}/content/item/${encodeURIComponent(id)}`);
    return json;
  },

  listAudit: async (
    path: string,
    params: { limit?: number; offset?: number } = {},
  ): Promise<ContentAuditEventListResponse> => {
    const qp = new URLSearchParams();
    if (params.limit !== undefined) qp.set("limit", String(params.limit));
    if (params.offset !== undefined) qp.set("offset", String(params.offset));
    const qs = qp.toString();
    const { json } = await httpClient(
      `${apiUrl}/content/audit/${encodeURIComponent(path)}${qs ? `?${qs}` : ""}`,
    );
    return json;
  },

  submitReview: async (
    path: string,
    payload: ContentReviewSubmitPayload,
  ): Promise<ContentItemInfo> => {
    const { json } = await httpClient(`${apiUrl}/content/review/${encodeURIComponent(path)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },

  verifyClass: async (
    path: string,
    payload: ContentVerifyClassPayload,
  ): Promise<ContentVerifyClassResponse> => {
    const { json } = await httpClient(
      `${apiUrl}/content/verify-class/${encodeURIComponent(path)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
    return json;
  },

  triggerProcess: async (
    path: string,
    processingConfig?: Record<string, unknown>,
  ): Promise<{ message: string; task_id: string }> => {
    const sanitizedProcessingConfig = processingConfig
      ? Object.fromEntries(
          Object.entries(processingConfig).filter(([key]) => key !== "embedding_model"),
        )
      : undefined;
    const body = sanitizedProcessingConfig
      ? JSON.stringify({ processing_config: sanitizedProcessingConfig })
      : undefined;
    const { json } = await httpClient(
      `${apiUrl}/content/process?path=${encodeURIComponent(path)}`,
      {
        method: "POST",
        body,
      },
    );
    return json;
  },

  abortProcessing: async (fileId: string): Promise<{ status: string }> => {
    const { json } = await httpClient(`${apiUrl}/content/abort/${encodeURIComponent(fileId)}`, {
      method: "POST",
    });
    return json;
  },

  triggerBatchProcess: async (params: {
    directoryPath?: string;
    paths?: string[];
    processingConfig?: Record<string, unknown>;
  }): Promise<{ message: string; queued: number; errors: number }> => {
    const sanitizedProcessingConfig = params.processingConfig
      ? Object.fromEntries(
          Object.entries(params.processingConfig).filter(([key]) => key !== "embedding_model"),
        )
      : undefined;
    const { json } = await httpClient(`${apiUrl}/content/process-batch`, {
      method: "POST",
      body: JSON.stringify({
        directory_path: params.directoryPath,
        paths: params.paths,
        processing_config: sanitizedProcessingConfig,
      }),
    });
    return json;
  },

  triggerFilteredBatchProcess: async (
    params: AllFilesBatchFilters,
    processingConfig?: Record<string, unknown>,
  ): Promise<{ message: string; queued: number; errors: number; matched: number }> => {
    const sanitizedProcessingConfig = processingConfig
      ? Object.fromEntries(
          Object.entries(processingConfig).filter(([key]) => key !== "embedding_model"),
        )
      : undefined;
    const { json } = await httpClient(`${apiUrl}/content/process-batch-filtered`, {
      method: "POST",
      body: JSON.stringify({
        name: params.name,
        name_regex: params.name ? (params.name_regex ?? false) : false,
        search_path: params.name ? (params.search_path ?? false) : false,
        path: params.path,
        content_kind: params.content_kind,
        extension: params.extension,
        status: params.status,
        document_class: params.document_class,
        extraction_schema: params.extraction_schema,
        extraction_field: params.extraction_field,
        field_filters: params.field_filters,
        review_status: params.review_status,
        review_reason: params.review_reason,
        needs_review: params.needs_review ?? false,
        stale_enrichment: params.stale_enrichment ?? false,
        processing_config: sanitizedProcessingConfig,
      }),
    });
    return json;
  },

  getChunks: async (
    path: string,
    limit?: number,
    offset?: number,
  ): Promise<ContentItemChunksResponse> => {
    const params = new URLSearchParams();
    if (limit !== undefined) params.set("limit", String(limit));
    if (offset !== undefined) params.set("offset", String(offset));
    const queryString = params.toString();
    const url = `${apiUrl}/content/chunks/${encodeURIComponent(path)}${queryString ? `?${queryString}` : ""}`;
    const { json } = await httpClient(url);
    return json;
  },

  getDownloadUrl: (path: string): string => {
    return `${apiUrl}/content/download/${encodeURIComponent(path)}`;
  },

  getExtractedDataCsvUrl: (params: AllFilesBatchFilters = {}): string => {
    const qp = new URLSearchParams();
    appendAllFilesBatchFilters(qp, params);
    const qs = qp.toString();
    return `${apiUrl}/content/extracted-data.csv${qs ? `?${qs}` : ""}`;
  },

  getPreviewUrl: (path: string): string => {
    return `${apiUrl}/content/preview/${encodeURIComponent(path)}`;
  },

  getExtractedDocument: async (path: string): Promise<unknown> => {
    const { json } = await httpClient(
      `${apiUrl}/content/extracted-document/${encodeURIComponent(path)}`,
    );
    return json;
  },

  getExtractedDocumentById: async (contentItemId: string): Promise<unknown> => {
    const { json } = await httpClient(
      `${apiUrl}/content/extracted-document-by-id/${encodeURIComponent(contentItemId)}`,
    );
    return json;
  },

  getExtractedAssets: async (path: string): Promise<ExtractedAssetsResponse> => {
    const { json } = await httpClient(`${apiUrl}/content/extracted/${encodeURIComponent(path)}`);
    return json;
  },

  getExtractedAssetUrl: (assetPath: string): string => {
    return `${apiUrl}/content/extracted-asset/${assetPath.split("/").map(encodeURIComponent).join("/")}`;
  },

  streamChat: async (
    payload: {
      thread_id: string;
      content_path: string;
      messages: unknown[];
    },
    signal?: AbortSignal,
  ): Promise<Response> => {
    return httpFetch(`${apiUrl}/content/chat/stream`, {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  },

  getRecent: async (limit: number = 10): Promise<ContentItemInfo[]> => {
    const { json } = await httpClient(`${apiUrl}/content/recent?limit=${limit}`);
    return json;
  },

  getGlobalStats: async (): Promise<{
    total_items: number;
    total_size_bytes: number;
    processing_count: number;
    stale_enrichment_count: number;
  }> => {
    const { json } = await httpClient(`${apiUrl}/content/stats`);
    return json;
  },

  getFolders: async (): Promise<DataFolderInfo[]> => {
    const { json } = await httpClient(`${apiUrl}/content/folders`);
    return json;
  },

  upload: async (directory: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const { json } = await httpClient(
      `${apiUrl}/content/upload?directory=${encodeURIComponent(directory)}`,
      {
        method: "POST",
        body: formData,
      },
    );
    return json;
  },

  mkdir: async (path: string) => {
    const { json } = await httpClient(`${apiUrl}/content/mkdir?path=${encodeURIComponent(path)}`, {
      method: "POST",
    });
    return json;
  },

  deleteFile: async (filePath: string) => {
    const { json } = await httpClient(`${apiUrl}/content/delete/${encodeURIComponent(filePath)}`, {
      method: "DELETE",
    });
    return json;
  },
};
