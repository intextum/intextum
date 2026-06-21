import { useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  contentApi,
  type ContentItemInfo,
  type ContentItemTreeNode,
  type FolderInfo,
} from "@/dataProvider";
import { queryKeys } from "@/lib/query-client";

const ACTIVE_STATUSES = new Set(["QUEUED", "PROCESSING", "RETRYING"]);
const POLL_INTERVAL = 3000;
const EMPTY_FOLDERS: FolderInfo[] = [];
const EMPTY_FILES: ContentItemInfo[] = [];

interface UseContentListFoldersOptions {
  enabled: boolean;
  path: string;
  refreshKey?: number;
  onImmutableChange?: (immutable: boolean) => void;
}

interface ContentListFoldersState {
  folders: FolderInfo[];
  files: ContentItemInfo[];
  isLoading: boolean;
  error: string | null;
  immutable: boolean;
}

function nodeToFolder(node: ContentItemTreeNode): FolderInfo | null {
  const details = node.details as FolderInfo | undefined;
  if (details) {
    return details;
  }
  return {
    id: node.id,
    name: node.name,
    display_name: node.display_name ?? node.name,
    path: node.path,
    kind: "folder",
    type: "folder",
    modified_at: "",
    item_count: 0,
    total_size_bytes: 0,
  };
}

export function useContentListFolders({
  enabled,
  path,
  refreshKey,
  onImmutableChange,
}: UseContentListFoldersOptions): ContentListFoldersState & { refresh: () => void } {
  const query = useQuery({
    queryKey: [...queryKeys.content.tree(path, 1), refreshKey ?? 0],
    enabled,
    queryFn: async () => {
      const response = await contentApi.getTree(path, 1);
      const children = response.root.children ?? [];
      const nextFolders: FolderInfo[] = [];
      const nextFiles: ContentItemInfo[] = [];
      for (const node of children) {
        if (node.type === "folder") {
          const folder = nodeToFolder(node);
          if (folder) {
            nextFolders.push(folder);
          }
        } else {
          const details = node.details as ContentItemInfo | undefined;
          if (details) {
            nextFiles.push(details);
          }
        }
      }
      return {
        folders: nextFolders,
        files: nextFiles,
        immutable: response.immutable ?? false,
      };
    },
    refetchInterval: (queryState) =>
      queryState.state.data?.files.some(
        (file) => file.status != null && ACTIVE_STATUSES.has(file.status),
      )
        ? POLL_INTERVAL
        : false,
  });
  const { data, error, isLoading, refetch } = query;

  useEffect(() => {
    if (data) {
      onImmutableChange?.(data.immutable);
    } else if (!enabled) {
      onImmutableChange?.(false);
    }
  }, [data, enabled, onImmutableChange]);

  const refresh = useCallback(() => {
    void refetch();
  }, [refetch]);

  return {
    folders: data?.folders ?? EMPTY_FOLDERS,
    files: data?.files ?? EMPTY_FILES,
    isLoading,
    error: error ? String(error) : null,
    immutable: data?.immutable ?? false,
    refresh,
  };
}
