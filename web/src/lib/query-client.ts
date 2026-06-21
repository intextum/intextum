import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
});

export const queryKeys = {
  auth: {
    currentUser: ["auth", "current-user"] as const,
    admin: ["auth", "admin"] as const,
  },
  content: {
    all: ["content"] as const,
    listAll: (params: unknown) => ["content", "list-all", params] as const,
    tree: (path: string, depth: number) => ["content", "tree", path, depth] as const,
    details: (path: string) => ["content", "details", path] as const,
    detailsById: (id: string) => ["content", "details-by-id", id] as const,
    audit: (path: string, params: unknown) => ["content", "audit", path, params] as const,
    extractedAssets: (path: string) => ["content", "extracted-assets", path] as const,
    chunks: (path: string) => ["content", "chunks", path] as const,
    recent: (limit: number) => ["content", "recent", limit] as const,
    stats: (scope: "global" | "folder", path: string) => ["content", "stats", scope, path] as const,
  },
  conversations: {
    all: ["conversations"] as const,
    list: (limit: number, offset: number) => ["conversations", "list", limit, offset] as const,
    detail: (id: string) => ["conversations", "detail", id] as const,
    run: (id: string) => ["conversations", "run", id] as const,
    promptPresets: ["conversations", "prompt-presets"] as const,
  },
  workers: {
    all: ["workers"] as const,
    list: ["workers", "list"] as const,
    tasks: (params: unknown) => ["workers", "tasks", params] as const,
  },
  settings: {
    ai: ["settings", "ai"] as const,
    contentEnrichmentCatalog: ["settings", "content-enrichment-catalog"] as const,
    notificationPreferences: ["settings", "notification-preferences"] as const,
  },
  admin: {
    all: ["admin"] as const,
    promptPresets: ["admin", "prompt-presets"] as const,
  },
};

export const invalidateContentQueries = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.content.all });

export const invalidateConversationQueries = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.conversations.all });

export const invalidateNotificationPreferenceQueries = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.settings.notificationPreferences });
