import { apiUrl, httpClient } from "./client.ts";

export const userApi = {
  getMe: async (): Promise<{
    sub?: string | null;
    username: string;
    email?: string;
    groups: string[];
    preferred_username?: string;
  }> => {
    const { json } = await httpClient(`${apiUrl}/me`);
    return json;
  },
};

export interface PermissionEntry {
  connector_uuid: string;
  trustee: string;
  access: string;
  granted_by?: string;
  created_at?: string;
}

export interface AppUserEntry {
  sub: string;
  username: string;
  email?: string;
  display_name?: string;
  auth_display_source?: string;
  is_admin: boolean;
  is_disabled: boolean;
  groups: string[];
  providers: string[];
  has_local_credential: boolean;
  first_seen_at?: string;
  last_seen_at?: string;
}

export interface GroupEntry {
  slug: string;
  display_name: string;
  description?: string;
  proxy_aliases: string[];
  member_count: number;
}

export interface DataConnectorTypeFieldEntry {
  key: string;
  label: string;
  description: string;
  required: boolean;
  input_type: string;
  placeholder?: string;
}

export interface DataConnectorTypeEntry {
  connector_type: string;
  label: string;
  description: string;
  fields: DataConnectorTypeFieldEntry[];
}

export const permissionsApi = {
  list: async (connectorUuid: string): Promise<PermissionEntry[]> => {
    const { json } = await httpClient(
      `${apiUrl}/connectors/${encodeURIComponent(connectorUuid)}/permissions`,
    );
    return json;
  },
  set: async (
    connectorUuid: string,
    trustee: string,
    access: string = "allow",
  ): Promise<PermissionEntry> => {
    const { json } = await httpClient(
      `${apiUrl}/connectors/${encodeURIComponent(connectorUuid)}/permissions`,
      { method: "PUT", body: JSON.stringify({ trustee, access }) },
    );
    return json;
  },
  remove: async (connectorUuid: string, trustee: string): Promise<void> => {
    await httpClient(
      `${apiUrl}/connectors/${encodeURIComponent(connectorUuid)}/permissions/${encodeURIComponent(trustee)}`,
      { method: "DELETE" },
    );
  },
  listUsers: async (): Promise<AppUserEntry[]> => {
    const { json } = await httpClient(`${apiUrl}/users`);
    return json;
  },
};

export const usersApi = {
  list: async (): Promise<AppUserEntry[]> => {
    const { json } = await httpClient(`${apiUrl}/users`);
    return json;
  },
  create: async (payload: {
    username: string;
    password: string;
    email?: string;
    display_name?: string;
    is_admin: boolean;
    is_disabled: boolean;
    groups: string[];
  }): Promise<AppUserEntry> => {
    const { json } = await httpClient(`${apiUrl}/users`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },
  update: async (
    userSub: string,
    payload: Partial<{
      username: string;
      email?: string;
      display_name?: string;
      is_admin: boolean;
      is_disabled: boolean;
      groups: string[];
    }>,
  ): Promise<AppUserEntry> => {
    const { json } = await httpClient(`${apiUrl}/users/${encodeURIComponent(userSub)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    return json;
  },
  setPassword: async (
    userSub: string,
    payload: { password: string; must_change_password?: boolean },
  ): Promise<void> => {
    await httpClient(`${apiUrl}/users/${encodeURIComponent(userSub)}/password`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};

export const groupsApi = {
  list: async (): Promise<GroupEntry[]> => {
    const { json } = await httpClient(`${apiUrl}/groups`);
    return json;
  },
  create: async (payload: {
    slug: string;
    display_name: string;
    description?: string;
    proxy_aliases: string[];
  }): Promise<GroupEntry> => {
    const { json } = await httpClient(`${apiUrl}/groups`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },
  update: async (
    slug: string,
    payload: Partial<{
      display_name: string;
      description?: string;
      proxy_aliases: string[];
    }>,
  ): Promise<GroupEntry> => {
    const { json } = await httpClient(`${apiUrl}/groups/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    return json;
  },
  remove: async (slug: string): Promise<void> => {
    await httpClient(`${apiUrl}/groups/${encodeURIComponent(slug)}`, {
      method: "DELETE",
    });
  },
};

export const authApi = {
  loginLocal: async (payload: { username_or_email: string; password: string }): Promise<void> => {
    await httpClient(`${apiUrl}/auth/login`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  logout: async (): Promise<{
    logged_out: boolean;
    auth_provider: string;
    proxy_logout_url: string;
  }> => {
    const { json } = await httpClient(`${apiUrl}/auth/logout`, {
      method: "POST",
    });
    return json;
  },
  changePassword: async (payload: {
    current_password: string;
    new_password: string;
  }): Promise<void> => {
    await httpClient(`${apiUrl}/auth/change-password`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};

export const dataConnectorsApi = {
  list: async (): Promise<DataConnectorEntry[]> => {
    const { json } = await httpClient(`${apiUrl}/data-connectors`);
    return json;
  },
  listTypes: async (): Promise<DataConnectorTypeEntry[]> => {
    const { json } = await httpClient(`${apiUrl}/data-connector-types`);
    return json;
  },
  create: async (payload: {
    name: string;
    connector_type: string;
    path?: string;
    watch: boolean;
    auto_process_new: boolean;
    initial_scan: boolean;
    immutable?: boolean;
    force_polling: boolean;
    poll_interval_seconds: number;
    uuid?: string;
    watcher_type?: string;
    smb_server?: string;
    smb_share?: string;
    smb_port?: number;
    smb_username?: string;
    smb_password?: string;
    smb_domain?: string;
    // S3 fields
    endpoint_url?: string;
    bucket?: string;
    s3_prefix?: string;
    access_key?: string;
    secret_key?: string;
    region?: string;
  }): Promise<DataConnectorEntry> => {
    const { json } = await httpClient(`${apiUrl}/data-connectors`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },
  update: async (
    connectorUuid: string,
    payload: Partial<{
      name: string;
      connector_type: string;
      path?: string;
      watch: boolean;
      auto_process_new: boolean;
      initial_scan: boolean;
      immutable: boolean;
      force_polling: boolean;
      poll_interval_seconds: number;
      watcher_type: string;
      smb_server: string;
      smb_share: string;
      smb_port: number;
      smb_username: string;
      smb_password: string;
      smb_domain: string;
      // S3 fields
      endpoint_url: string;
      bucket: string;
      s3_prefix: string;
      access_key: string;
      secret_key: string;
      region: string;
    }>,
  ): Promise<DataConnectorEntry> => {
    const { json } = await httpClient(
      `${apiUrl}/data-connectors/${encodeURIComponent(connectorUuid)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
    return json;
  },
  remove: async (connectorUuid: string, force: boolean = false): Promise<void> => {
    const query = force ? "?force=true" : "";
    await httpClient(`${apiUrl}/data-connectors/${encodeURIComponent(connectorUuid)}${query}`, {
      method: "DELETE",
    });
  },
};

export interface DataConnectorEntry {
  uuid: string;
  name: string;
  connector_type: string;
  path: string;
  watch: boolean;
  auto_process_new: boolean;
  initial_scan: boolean;
  immutable: boolean;
  force_polling: boolean;
  poll_interval_seconds: number;
  watcher_type: string;
  smb_server: string | null;
  smb_share: string | null;
  smb_port: number;
  smb_username: string | null;
  smb_domain: string | null;
  // S3 fields
  endpoint_url: string | null;
  bucket: string | null;
  s3_prefix: string | null;
  access_key: string | null;
  region: string | null;
  // Initial-scan progress (read-only)
  scan_state: "idle" | "scanning" | "done" | "failed";
  scan_dirs: number;
  scan_files_queued: number;
  scan_files_unchanged: number;
  scan_started_at: string | null;
  scan_finished_at: string | null;
}

export interface AiSettingEntry {
  key: string;
  section: "chat" | "image_description" | "content_enrichment";
  label: string;
  description: string;
  input_type: "text" | "textarea" | "number" | "boolean" | "json";
  value: string | number | boolean | Array<Record<string, unknown>> | Record<string, string>;
  default_value:
    | string
    | number
    | boolean
    | Array<Record<string, unknown>>
    | Record<string, string>;
  overridden: boolean;
}

export interface AiSettingsResponse {
  items: AiSettingEntry[];
}

export interface AiSettingsUpdatePayload {
  chat_model?: string;
  chat_system_prompt?: string;
  chat_tool_prompt?: string;
  chat_search_limit?: number;
  chat_document_max_chars?: number;
  picture_description_model?: string;
  picture_description_prompt?: string;
  picture_description_max_tokens?: number;
  picture_description_enable_thinking?: boolean;
  document_classification_enabled?: boolean;
  document_classification_provider?: string;
  document_classification_model?: string;
  document_extraction_enabled?: boolean;
  document_extraction_model?: string;
  document_extraction_llm_model?: string;
  document_extraction_llm_max_output_tokens?: number;
  document_extraction_llm_enable_thinking?: boolean;
  document_extraction_chat_max_retries?: number;
  document_extraction_chat_evidence_required?: boolean;
  document_extraction_chat_full_text_threshold_chars?: number;
  document_extraction_schema_models?: Record<string, string>;
  document_extraction_max_chars?: number;
}

export interface ContentEnrichmentCatalogClass {
  id: string;
  name: string;
  version: number;
  description: string;
  aliases: string[];
}

export interface ContentEnrichmentCatalogField {
  name: string;
  dtype: "str" | "int" | "float" | "bool" | "list" | "date" | "currency" | "object_list";
  description: string;
  required: boolean;
  fields?: Array<{
    name: string;
    dtype: "str" | "int" | "float" | "bool" | "list" | "date" | "currency";
    description: string;
    required: boolean;
  }>;
}

export interface ContentEnrichmentCatalogSceneExtraction {
  field: string;
  extraction_text: string;
  value: unknown;
}

export interface ContentEnrichmentCatalogScene {
  text: string;
  extractions: ContentEnrichmentCatalogSceneExtraction[];
}

export interface ContentEnrichmentCatalogSchema {
  id: string;
  name: string;
  version: number;
  description: string;
  fields: ContentEnrichmentCatalogField[];
  scenes?: ContentEnrichmentCatalogScene[];
}

export interface ContentEnrichmentCatalogDocumentClass extends ContentEnrichmentCatalogClass {
  extraction_schema?: ContentEnrichmentCatalogSchema | null;
}

export interface ContentEnrichmentCatalogResponse {
  document_classes: ContentEnrichmentCatalogDocumentClass[];
}

export interface ContentEnrichmentCatalogUpdatePayload {
  document_classes: Array<Record<string, unknown>>;
}

export type ContentEnrichmentFineTuneTargetKind = "classification" | "extraction";
export type ContentEnrichmentFineTuneTrainingMethod = "lora";
export type ContentEnrichmentFineTuneJobStatus = "queued" | "running" | "completed" | "failed";
export type ContentEnrichmentModelRegistryStatus = "training" | "ready" | "failed" | "archived";

export interface ContentEnrichmentTrainingDatasetSummary {
  reviewed_example_count: number;
}

export interface ContentEnrichmentModelRegistryEntry {
  id: string;
  target_kind: ContentEnrichmentFineTuneTargetKind;
  training_method: ContentEnrichmentFineTuneTrainingMethod;
  status: ContentEnrichmentModelRegistryStatus;
  base_model: string;
  target_name?: string | null;
  config_fingerprint: string;
  reviewed_example_count: number;
  artifact_path?: string | null;
  metrics?: Record<string, unknown> | null;
  created_by?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContentEnrichmentFineTuneJobEntry {
  id: string;
  registry_model_id: string;
  queue_task_id?: string | null;
  status: ContentEnrichmentFineTuneJobStatus;
  target_kind: ContentEnrichmentFineTuneTargetKind;
  training_method: ContentEnrichmentFineTuneTrainingMethod;
  base_model: string;
  target_name?: string | null;
  config_fingerprint: string;
  dataset_summary: ContentEnrichmentTrainingDatasetSummary;
  error_message?: string | null;
  requested_by?: string | null;
  requested_by_sub?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ContentEnrichmentTrainingCurrentExamples {
  classification: number;
}

export interface ContentEnrichmentTrainingOverviewResponse {
  jobs: ContentEnrichmentFineTuneJobEntry[];
  models: ContentEnrichmentModelRegistryEntry[];
  current_examples?: ContentEnrichmentTrainingCurrentExamples;
}

export interface CreateContentEnrichmentFineTuneJobPayload {
  target_kind: "classification";
  training_method: ContentEnrichmentFineTuneTrainingMethod;
  base_model?: string;
}

export interface ContentEnrichmentModelPromotionResponse {
  model_id: string;
  target_kind: ContentEnrichmentFineTuneTargetKind;
  target_name?: string | null;
  setting_key: "document_classification_model";
  setting_value: string;
  stale_file_count: number;
  newly_stale_file_count: number;
}

export interface NotificationPreferences {
  chat: {
    completed: boolean;
    failed: boolean;
    cancelled: boolean;
  };
  content_processing: {
    completed: boolean;
    failed: boolean;
  };
  research: {
    completed: boolean;
    failed: boolean;
    cancelled: boolean;
  };
}

export interface UserEvent {
  kind: string;
  resource_type: string;
  resource_id: string;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  event_id?: string;
}

export interface ContentEnrichmentFieldExampleCandidate {
  content_item_id: string;
  relative_path: string;
  review_status: string | null;
  text: string;
  anchor_text: string;
  value: unknown;
  page_numbers: number[];
  chunk_index: number | null;
}

export interface ContentEnrichmentFieldExampleCandidatesResponse {
  candidates: ContentEnrichmentFieldExampleCandidate[];
}

export const contentEnrichmentCatalogApi = {
  get: async (): Promise<ContentEnrichmentCatalogResponse> => {
    const { json } = await httpClient(`${apiUrl}/content-enrichment-catalog`);
    return json;
  },

  replace: async (
    payload: ContentEnrichmentCatalogUpdatePayload,
  ): Promise<ContentEnrichmentCatalogResponse> => {
    const { json } = await httpClient(`${apiUrl}/content-enrichment-catalog`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    return json;
  },

  reset: async (): Promise<ContentEnrichmentCatalogResponse> => {
    const { json } = await httpClient(`${apiUrl}/content-enrichment-catalog/reset`, {
      method: "POST",
    });
    return json;
  },

  suggestFieldExampleCandidates: async (
    schemaName: string,
    fieldName: string,
    contentItemIds: string[],
  ): Promise<ContentEnrichmentFieldExampleCandidatesResponse> => {
    const { json } = await httpClient(
      `${apiUrl}/content-enrichment-catalog/schemas/${encodeURIComponent(schemaName)}/fields/${encodeURIComponent(fieldName)}/example-candidates`,
      {
        method: "POST",
        body: JSON.stringify({ content_item_ids: contentItemIds }),
      },
    );
    return json;
  },
};

export const contentEnrichmentTrainingApi = {
  getOverview: async (): Promise<ContentEnrichmentTrainingOverviewResponse> => {
    const { json } = await httpClient(`${apiUrl}/content-enrichment-training`);
    return json;
  },

  createJob: async (
    payload: CreateContentEnrichmentFineTuneJobPayload,
  ): Promise<ContentEnrichmentFineTuneJobEntry> => {
    const { json } = await httpClient(`${apiUrl}/content-enrichment-training/jobs`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },

  retryJob: async (jobId: string): Promise<ContentEnrichmentFineTuneJobEntry> => {
    const { json } = await httpClient(
      `${apiUrl}/content-enrichment-training/jobs/${encodeURIComponent(jobId)}/retry`,
      {
        method: "POST",
      },
    );
    return json;
  },

  cancelJob: async (jobId: string): Promise<ContentEnrichmentFineTuneJobEntry> => {
    const { json } = await httpClient(
      `${apiUrl}/content-enrichment-training/jobs/${encodeURIComponent(jobId)}/cancel`,
      {
        method: "POST",
      },
    );
    return json;
  },

  deleteJob: async (jobId: string): Promise<void> => {
    await httpClient(`${apiUrl}/content-enrichment-training/jobs/${encodeURIComponent(jobId)}`, {
      method: "DELETE",
    });
  },

  promoteModel: async (modelId: string): Promise<ContentEnrichmentModelPromotionResponse> => {
    const { json } = await httpClient(
      `${apiUrl}/content-enrichment-training/models/${encodeURIComponent(modelId)}/promote`,
      {
        method: "POST",
      },
    );
    return json;
  },

  archiveModel: async (modelId: string): Promise<ContentEnrichmentModelRegistryEntry> => {
    const { json } = await httpClient(
      `${apiUrl}/content-enrichment-training/models/${encodeURIComponent(modelId)}/archive`,
      {
        method: "POST",
      },
    );
    return json;
  },
};

export const aiSettingsApi = {
  get: async (): Promise<AiSettingsResponse> => {
    const { json } = await httpClient(`${apiUrl}/ai-settings`);
    return json;
  },

  update: async (payload: AiSettingsUpdatePayload): Promise<AiSettingsResponse> => {
    const { json } = await httpClient(`${apiUrl}/ai-settings`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    return json;
  },

  reset: async (key: string): Promise<AiSettingsResponse> => {
    const { json } = await httpClient(`${apiUrl}/ai-settings/${encodeURIComponent(key)}`, {
      method: "DELETE",
    });
    return json;
  },

  resetMany: async (keys?: string[]): Promise<AiSettingsResponse> => {
    const { json } = await httpClient(`${apiUrl}/ai-settings/reset`, {
      method: "POST",
      body: JSON.stringify(keys && keys.length > 0 ? { keys } : {}),
    });
    return json;
  },
};

export const notificationPreferencesApi = {
  get: async (): Promise<NotificationPreferences> => {
    const { json } = await httpClient(`${apiUrl}/me/notification-preferences`);
    return json;
  },

  update: async (preferences: NotificationPreferences): Promise<NotificationPreferences> => {
    const { json } = await httpClient(`${apiUrl}/me/notification-preferences`, {
      method: "PUT",
      body: JSON.stringify(preferences),
    });
    return json;
  },
};
