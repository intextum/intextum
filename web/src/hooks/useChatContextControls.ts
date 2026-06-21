import { useCallback, useRef, useState, type Dispatch, type MutableRefObject } from "react";
import type { ChatPromptPreset } from "@/dataProvider";
import { addPaths, normalizePath, removePath } from "@/hooks/chat-context";
import type { ChatExperienceMode } from "@/lib/chat-experience-state";
import { localizedPresetText, promptPresetRequirementMessageKey } from "@/lib/chat-prompt-presets";

type TranslateFn = (key: string, options?: unknown) => string;
type NotifyFn = (
  message: string,
  options?: { type?: "info" | "success" | "warning" | "error" },
) => void;

export function useChatContextControls({
  applyPromptPreset,
  contextFilePaths,
  contextFilePathsRef,
  locale,
  notify,
  setChatExperienceMode,
  setComposerText,
  setCurrentContextFilePaths,
  translate,
  updateCurrentContextFilePaths,
}: {
  applyPromptPreset: (preset: ChatPromptPreset, contextPaths: string[]) => Promise<boolean>;
  contextFilePaths: string[];
  contextFilePathsRef: MutableRefObject<string[]>;
  locale: string;
  notify: NotifyFn;
  setChatExperienceMode: (mode: ChatExperienceMode) => void;
  setComposerText: Dispatch<string>;
  setCurrentContextFilePaths: (paths: string[]) => void;
  translate: TranslateFn;
  updateCurrentContextFilePaths: (updater: (paths: string[]) => string[]) => void;
}) {
  const [contextPickerOpen, setContextPickerOpen] = useState(false);
  const pendingPresetRef = useRef<ChatPromptPreset | null>(null);

  const handlePresetClick = useCallback(
    async (preset: ChatPromptPreset) => {
      const prompt = localizedPresetText(preset.prompt, locale);
      const requirement = promptPresetRequirementMessageKey(preset, contextFilePaths.length);
      setChatExperienceMode(preset.mode);
      setComposerText(prompt);

      if (requirement === "min") {
        pendingPresetRef.current = preset;
        notify(
          translate("custom.pages.chat.context.require_files_for_suggestion", {
            required: preset.context.min_files,
          }),
          { type: "warning" },
        );
        setContextPickerOpen(true);
        return;
      }

      if (requirement === "max") {
        pendingPresetRef.current = null;
        notify(
          translate("custom.pages.chat.context.limit_files_for_suggestion", {
            max: preset.context.max_files,
          }),
          { type: "warning" },
        );
        return;
      }

      pendingPresetRef.current = null;
      await applyPromptPreset(preset, contextFilePaths);
    },
    [
      applyPromptPreset,
      contextFilePaths,
      locale,
      notify,
      setChatExperienceMode,
      setComposerText,
      translate,
    ],
  );

  const handleRemoveContextFile = useCallback(
    (path: string) => {
      updateCurrentContextFilePaths((paths) => removePath(paths, path));
    },
    [updateCurrentContextFilePaths],
  );

  const handleClearContextFiles = useCallback(() => {
    setCurrentContextFilePaths([]);
  }, [setCurrentContextFilePaths]);

  const handleOpenContextPicker = useCallback(() => {
    pendingPresetRef.current = null;
    setContextPickerOpen(true);
  }, []);

  const handleContextPickerOpenChange = useCallback((open: boolean) => {
    setContextPickerOpen(open);
    if (!open) {
      pendingPresetRef.current = null;
    }
  }, []);

  const handleAddContextPaths = useCallback(
    (paths: string[]) => {
      let skippedCount = 0;
      const activePendingPreset = pendingPresetRef.current;
      const currentPaths = contextFilePathsRef.current;
      const maxFiles = activePendingPreset?.context.max_files ?? null;
      const incomingPaths =
        maxFiles === null || maxFiles === undefined
          ? paths
          : paths.reduce<string[]>((acc, path) => {
              const normalized = normalizePath(path);
              if (!normalized) {
                skippedCount += 1;
                return acc;
              }

              const projected = addPaths(currentPaths, acc);
              if (projected.paths.includes(normalized) || projected.paths.length >= maxFiles) {
                skippedCount += 1;
                return acc;
              }

              return [...acc, normalized];
            }, []);
      const result = addPaths(currentPaths, incomingPaths);
      const addedCount = result.addedCount;
      skippedCount += result.skippedCount;
      const resolvedPaths = result.paths;

      setCurrentContextFilePaths(resolvedPaths);

      if (addedCount > 0 && skippedCount > 0) {
        notify(
          translate("custom.pages.chat.context.added_and_skipped", {
            added: addedCount,
            skipped: skippedCount,
          }),
          { type: "info" },
        );
      } else if (addedCount > 0) {
        notify(
          translate("custom.pages.chat.context.added_count", {
            count: addedCount,
          }),
          { type: "info" },
        );
      } else if (skippedCount > 0) {
        notify(
          translate("custom.pages.chat.context.already_selected_multiple", {
            count: skippedCount,
          }),
          { type: "warning" },
        );
      }

      if (!activePendingPreset) {
        return;
      }

      const requirement = promptPresetRequirementMessageKey(
        activePendingPreset,
        resolvedPaths.length,
      );
      if (requirement === "min") {
        return;
      }
      if (requirement === "max") {
        notify(
          translate("custom.pages.chat.context.limit_files_for_suggestion", {
            max: activePendingPreset.context.max_files,
          }),
          { type: "warning" },
        );
        return;
      }

      pendingPresetRef.current = null;
      setContextPickerOpen(false);
      void applyPromptPreset(activePendingPreset, resolvedPaths);
    },
    [applyPromptPreset, contextFilePathsRef, notify, setCurrentContextFilePaths, translate],
  );

  return {
    contextPickerOpen,
    handleAddContextPaths,
    handleClearContextFiles,
    handleContextPickerOpenChange,
    handleOpenContextPicker,
    handlePresetClick,
    handleRemoveContextFile,
  };
}
