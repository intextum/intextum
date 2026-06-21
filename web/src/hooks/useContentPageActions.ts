import { useCallback, type ReactNode } from "react";
import type { NotificationOptions, NotificationType } from "@/lib/app-context";

import { contentApi } from "../dataProvider.ts";
import { useConfirm } from "../lib/confirm-context.ts";
import {
  buildContentPageDeleteNotification,
  buildContentPageProcessStartedNotification,
  buildContentPageProcessingFailedNotification,
  buildContentPageQueuedBatchNotification,
  resolveContentPageNotification,
  runContentPageBatchMutation,
  runContentPageDelete,
} from "../lib/content-page-actions.ts";

type NotifyFn = (
  message: ReactNode,
  options?: NotificationOptions & { type?: NotificationType },
) => void;
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

interface UseContentPageActionsOptions {
  notify: NotifyFn;
  translate: TranslateFn;
  selectedFilePath: string | null;
  onRefresh: () => void;
  onClearSelectedFile: () => void;
}

export function useContentPageActions({
  notify,
  translate,
  selectedFilePath,
  onRefresh,
  onClearSelectedFile,
}: UseContentPageActionsOptions) {
  const confirm = useConfirm();
  const showNotification = useCallback(
    (
      descriptor:
        | ReturnType<typeof buildContentPageProcessStartedNotification>
        | ReturnType<typeof buildContentPageProcessingFailedNotification>
        | ReturnType<typeof buildContentPageQueuedBatchNotification>
        | ReturnType<typeof buildContentPageDeleteNotification>,
    ) => {
      if (!descriptor) {
        return;
      }
      const { message, options } = resolveContentPageNotification(translate, descriptor);
      notify(message, options);
    },
    [notify, translate],
  );

  const handleProcess = useCallback(
    async (path: string, processingConfig?: Record<string, unknown>) => {
      try {
        const result = await contentApi.triggerProcess(path, processingConfig);
        showNotification(buildContentPageProcessStartedNotification(result.task_id));
        onRefresh();
        return true;
      } catch {
        showNotification(buildContentPageProcessingFailedNotification());
        return false;
      }
    },
    [onRefresh, showNotification],
  );

  const handleProcessFolder = useCallback(
    async (path: string) => {
      const outcome = await runContentPageBatchMutation({
        confirm: () =>
          confirm({
            description: translate("custom.content.actions.confirm_process_folder"),
          }),
        execute: () => contentApi.triggerBatchProcess({ directoryPath: path }),
        onRefresh,
      });
      showNotification(buildContentPageQueuedBatchNotification(outcome));
    },
    [confirm, onRefresh, showNotification, translate],
  );

  const handleProcessSelected = useCallback(
    async (paths: string[], processingConfig?: Record<string, unknown>) => {
      const outcome = await runContentPageBatchMutation({
        execute: () => contentApi.triggerBatchProcess({ paths, processingConfig }),
        onRefresh,
      });
      showNotification(buildContentPageQueuedBatchNotification(outcome));
    },
    [onRefresh, showNotification],
  );

  const handleDelete = useCallback(
    async (path: string) => {
      const name = path.split("/").pop() || path;
      if (
        !(await confirm({
          title: translate("custom.content.delete.title"),
          description: translate("custom.content.delete.confirm_message", { name }),
          confirmLabel: translate("custom.confirm.delete"),
          destructive: true,
        }))
      ) {
        return;
      }
      try {
        await runContentPageDelete({
          path,
          selectedFilePath,
          deleteFile: contentApi.deleteFile,
          onRefresh,
          onClearSelectedFile,
        });
        showNotification(buildContentPageDeleteNotification("success"));
      } catch {
        showNotification(buildContentPageDeleteNotification("error"));
      }
    },
    [confirm, onClearSelectedFile, onRefresh, selectedFilePath, showNotification, translate],
  );

  const handleMutationSuccess = useCallback(() => {
    onRefresh();
  }, [onRefresh]);

  return {
    handleProcess,
    handleProcessFolder,
    handleProcessSelected,
    handleDelete,
    handleMutationSuccess,
  };
}
