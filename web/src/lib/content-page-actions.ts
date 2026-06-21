import type { ContentItemInfo } from "@/dataProvider";

export type ContentPageNotificationType = "success" | "error" | "warning";
export type ContentPageTranslateFn = (key: string, options?: Record<string, unknown>) => string;

export type ContentPageBatchMutationOutcome<T> =
  | { status: "cancelled" }
  | { status: "error" }
  | { status: "success"; result: T };

export interface ContentPageNotificationDescriptor {
  key: string;
  type: ContentPageNotificationType;
  options?: Record<string, unknown>;
}

type ContentPageQueuedBatchResult = {
  queued: number;
};

interface RunContentPageBatchMutationOptions<T> {
  confirm?: () => boolean | Promise<boolean>;
  execute: () => Promise<T>;
  onRefresh: () => void;
}

interface RunContentPageSelectedFileMutationOptions<T extends ContentItemInfo> {
  activeSelectedFile: ContentItemInfo | null;
  mutate: (path: string) => Promise<T>;
  onUpdateSelectedFile: (file: T) => void;
  onRefresh: () => void;
}

interface RunContentPageDeleteOptions {
  path: string;
  selectedFilePath: string | null;
  deleteFile: (path: string) => Promise<void>;
  onRefresh: () => void;
  onClearSelectedFile: () => void;
}

export async function runContentPageBatchMutation<T>({
  confirm,
  execute,
  onRefresh,
}: RunContentPageBatchMutationOptions<T>): Promise<ContentPageBatchMutationOutcome<T>> {
  if (confirm && !(await confirm())) {
    return { status: "cancelled" };
  }

  try {
    const result = await execute();
    onRefresh();
    return { status: "success", result };
  } catch {
    return { status: "error" };
  }
}

export function resolveContentPageNotification(
  translate: ContentPageTranslateFn,
  descriptor: ContentPageNotificationDescriptor,
): { message: string; options: { type: ContentPageNotificationType } } {
  return {
    message: translate(descriptor.key, descriptor.options),
    options: { type: descriptor.type },
  };
}

export function buildContentPageProcessStartedNotification(
  taskId: string,
): ContentPageNotificationDescriptor {
  return {
    key: "custom.processing_started",
    type: "success",
    options: { id: taskId },
  };
}

export function buildContentPageProcessingFailedNotification(): ContentPageNotificationDescriptor {
  return {
    key: "custom.failed_to_start_processing",
    type: "error",
  };
}

export function buildContentPageQueuedBatchNotification(
  outcome: ContentPageBatchMutationOutcome<ContentPageQueuedBatchResult>,
): ContentPageNotificationDescriptor | null {
  if (outcome.status === "cancelled") {
    return null;
  }
  if (outcome.status === "error") {
    return buildContentPageProcessingFailedNotification();
  }
  return {
    key: "custom.batch_processing_started",
    type: "success",
    options: { count: outcome.result.queued },
  };
}

export function buildContentPageDeleteNotification(
  status: "success" | "error",
): ContentPageNotificationDescriptor {
  return {
    key: status === "success" ? "custom.content.delete.success" : "custom.content.delete.failed",
    type: status,
  };
}

export async function runContentPageSelectedFileMutation<T extends ContentItemInfo>({
  activeSelectedFile,
  mutate,
  onUpdateSelectedFile,
  onRefresh,
}: RunContentPageSelectedFileMutationOptions<T>): Promise<T | null> {
  if (!activeSelectedFile) {
    return null;
  }

  try {
    const updatedFile = await mutate(activeSelectedFile.path);
    onUpdateSelectedFile(updatedFile);
    onRefresh();
    return updatedFile;
  } catch {
    return null;
  }
}

export async function runContentPageDelete({
  path,
  selectedFilePath,
  deleteFile,
  onRefresh,
  onClearSelectedFile,
}: RunContentPageDeleteOptions): Promise<void> {
  await deleteFile(path);
  onRefresh();
  if (selectedFilePath === path) {
    onClearSelectedFile();
  }
}
