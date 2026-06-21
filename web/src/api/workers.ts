import { apiUrl, httpClient } from "./client.ts";

export interface Worker {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  last_seen: string | null;
  config: Record<string, unknown>;
  status: string;
}

export interface WorkerCreateResponse {
  worker: Worker;
  token: string;
}

export interface WorkerListResponse {
  workers: Worker[];
  total: number;
}

export interface WorkerTaskQueueItem {
  id: string;
  task_type: string;
  content_kind?: string | null;
  content_item_id?: string | null;
  folder_uuid: string;
  relative_path: string;
  status: string;
  stage?: string | null;
  requested_by_sub?: string | null;
  claimed_by?: string | null;
  claimed_at?: string | null;
  claim_age_seconds?: number | null;
  stale_after_seconds: number;
  is_stale: boolean;
  retry_count: number;
  max_retries: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkerTaskQueueListResponse {
  tasks: WorkerTaskQueueItem[];
  total: number;
}

export interface WorkerTaskQueueCleanupResponse {
  total: number;
  requeued: number;
  failed: number;
}

export interface WorkerInstallPlatform {
  id: string;
  label: string;
  kind: "pip" | "docker";
  extra: string | null;
  extra_index_url: string | null;
  image: string | null;
  gpu: boolean;
  notes: string | null;
}

export interface WorkerInstallInfo {
  package: string;
  version: string;
  default_capabilities: string;
  public_url: string | null;
  platforms: WorkerInstallPlatform[];
}

export const workersApi = {
  list: async (): Promise<WorkerListResponse> => {
    const { json } = await httpClient(`${apiUrl}/workers/`);
    return json;
  },

  listTasks: async (
    options: { activeOnly?: boolean; limit?: number } = {},
  ): Promise<WorkerTaskQueueListResponse> => {
    const params = new URLSearchParams();
    params.set("active_only", String(options.activeOnly ?? true));
    if (options.limit) params.set("limit", String(options.limit));
    const { json } = await httpClient(`${apiUrl}/workers/tasks?${params}`);
    return json;
  },

  cleanupStaleTasks: async (): Promise<WorkerTaskQueueCleanupResponse> => {
    const { json } = await httpClient(`${apiUrl}/workers/tasks/cleanup-stale`, {
      method: "POST",
    });
    return json;
  },

  get: async (id: string): Promise<Worker> => {
    const { json } = await httpClient(`${apiUrl}/workers/${id}`);
    return json;
  },

  create: async (data: { name: string; description?: string }): Promise<WorkerCreateResponse> => {
    const { json } = await httpClient(`${apiUrl}/workers/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
    return json;
  },

  update: async (id: string, data: { name?: string; description?: string }): Promise<Worker> => {
    const { json } = await httpClient(`${apiUrl}/workers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    return json;
  },

  delete: async (id: string): Promise<void> => {
    await httpClient(`${apiUrl}/workers/${id}`, {
      method: "DELETE",
    });
  },

  rotateToken: async (id: string): Promise<WorkerCreateResponse> => {
    const { json } = await httpClient(`${apiUrl}/workers/${id}/rotate-token`, {
      method: "POST",
    });
    return json;
  },

  installInfo: async (): Promise<WorkerInstallInfo> => {
    const { json } = await httpClient(`${apiUrl}/workers/install-info`);
    return json;
  },
};
