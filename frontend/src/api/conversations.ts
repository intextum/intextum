import { apiUrl, httpClient, httpFetch } from "./client.ts";
import type { ContentItemKind } from "./content.ts";

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  active_run_status?: "PENDING" | "RUNNING" | null;
}

export interface ConversationSource {
  file_path: string;
  content_item_id?: string | null;
  display_name?: string | null;
  content_kind?: ContentItemKind | null;
  email_from_address?: string | null;
  email_sent_at?: string | null;
  parent_display_name?: string | null;
  title?: string;
  source_kind?: "reviewed_enrichment" | null;
  page_numbers: number[];
  doc_refs: string[];
  citation_index?: number;
  images: string[];
  quote?: string;
}

export interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  sources: ConversationSource[];
  metadata?: Record<string, unknown> | null;
  created_at?: string;
  status?: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
  context_file_paths: string[];
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
  total: number;
}

export interface ConversationBulkDeleteResponse {
  deleted_count: number;
}

export interface ConversationRun {
  id: string;
  conversation_id: string;
  user_sub: string;
  mode: "chat" | "research";
  research_report_id?: string | null;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  claimed_by?: string | null;
  claimed_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  last_event_id?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateConversationRunResponse {
  run_id: string;
  conversation_id: string;
  mode: ConversationRun["mode"];
  research_report_id?: string | null;
  status: ConversationRun["status"];
}

export interface ImportConversationResponse {
  conversation_id: string;
}

export interface AssistantResponseExportPayload {
  title: string;
  filename_base: string;
  markdown: string;
  embedded_images?: ExportEmbeddedImagePayload[];
}

export interface ExportEmbeddedImagePayload {
  url: string;
  filename: string;
  media_type: string;
  data_base64: string;
  width_px: number;
  height_px: number;
  alt_text?: string | null;
}

export type ChatPromptPresetMode = "chat" | "research";
export type ChatPromptPresetAction = "fill" | "submit";
export type ChatPromptPresetIcon =
  | "bar-chart"
  | "book-open"
  | "file-search"
  | "file-text"
  | "list-checks"
  | "search"
  | "sparkles";

export interface ChatPromptPresetContextRequirement {
  min_files: number;
  max_files?: number | null;
}

export interface ChatPromptPreset {
  id: string;
  enabled: boolean;
  sort_order: number;
  mode: ChatPromptPresetMode;
  label: Record<string, string>;
  description: Record<string, string>;
  prompt: Record<string, string>;
  icon: ChatPromptPresetIcon;
  context: ChatPromptPresetContextRequirement;
  action: ChatPromptPresetAction;
}

export interface ChatPromptPresetListResponse {
  presets: ChatPromptPreset[];
}

export const conversationsApi = {
  list: async (limit: number = 50, offset: number = 0): Promise<ConversationListResponse> => {
    const { json } = await httpClient(`${apiUrl}/conversations/?limit=${limit}&offset=${offset}`);
    return json;
  },

  get: async (id: string): Promise<ConversationDetail> => {
    const { json } = await httpClient(`${apiUrl}/conversations/${id}`);
    return json;
  },

  update: async (id: string, data: { title?: string }): Promise<ConversationSummary> => {
    const { json } = await httpClient(`${apiUrl}/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    return json;
  },

  delete: async (id: string): Promise<void> => {
    await httpClient(`${apiUrl}/conversations/${id}`, {
      method: "DELETE",
    });
  },

  deleteAll: async (): Promise<ConversationBulkDeleteResponse> => {
    const { json } = await httpClient(`${apiUrl}/conversations/`, {
      method: "DELETE",
    });
    return json;
  },

  deleteOlder: async (beforeIso: string): Promise<ConversationBulkDeleteResponse> => {
    const { json } = await httpClient(
      `${apiUrl}/conversations/?before=${encodeURIComponent(beforeIso)}`,
      {
        method: "DELETE",
      },
    );
    return json;
  },

  createRun: async (payload: unknown): Promise<CreateConversationRunResponse> => {
    const { json } = await httpClient(`${apiUrl}/conversations/runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },

  regenerateMessage: async (
    conversationId: string,
    messageId: string,
  ): Promise<CreateConversationRunResponse> => {
    const { json } = await httpClient(
      `${apiUrl}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(
        messageId,
      )}/regenerate`,
      {
        method: "POST",
      },
    );
    return json;
  },

  import: async (payload: {
    title?: string | null;
    context_file_paths: string[];
    messages: unknown[];
  }): Promise<ImportConversationResponse> => {
    const { json } = await httpClient(`${apiUrl}/conversations/import`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return json;
  },

  getRun: async (runId: string): Promise<ConversationRun> => {
    const { json } = await httpClient(`${apiUrl}/conversations/runs/${encodeURIComponent(runId)}`);
    return json;
  },

  cancelRun: async (runId: string): Promise<ConversationRun> => {
    const { json } = await httpClient(
      `${apiUrl}/conversations/runs/${encodeURIComponent(runId)}/cancel`,
      {
        method: "POST",
      },
    );
    return json;
  },
};

export const chatPromptPresetsApi = {
  list: async (): Promise<ChatPromptPresetListResponse> => {
    const { json } = await httpClient(`${apiUrl}/chat/prompt-presets`);
    return json;
  },

  getAdmin: async (): Promise<ChatPromptPresetListResponse> => {
    const { json } = await httpClient(`${apiUrl}/admin/chat-prompt-presets`);
    return json;
  },

  replaceAdmin: async (presets: ChatPromptPreset[]): Promise<ChatPromptPresetListResponse> => {
    const { json } = await httpClient(`${apiUrl}/admin/chat-prompt-presets`, {
      method: "PUT",
      body: JSON.stringify({ presets }),
    });
    return json;
  },

  resetAdmin: async (): Promise<ChatPromptPresetListResponse> => {
    const { json } = await httpClient(`${apiUrl}/admin/chat-prompt-presets/reset`, {
      method: "POST",
    });
    return json;
  },
};

export const exportsApi = {
  exportDocx: async (payload: AssistantResponseExportPayload): Promise<Blob> => {
    const response = await httpFetch(`${apiUrl}/exports/docx`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`Failed to export DOCX (${response.status})`);
    }
    return response.blob();
  },
};
