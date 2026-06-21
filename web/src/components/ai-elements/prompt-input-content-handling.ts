"use client";

import type { FileUIPart } from "ai";
import type { ChangeEventHandler, RefObject } from "react";

import { nanoid } from "nanoid";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AttachmentsContext, PromptInputControllerProps } from "./prompt-input-provider";

export interface PromptInputFileError {
  code: "max_files" | "max_file_size" | "accept";
  message: string;
}

interface UsePromptInputFileHandlingParams {
  accept?: string;
  controller: PromptInputControllerProps | null;
  globalDrop?: boolean;
  maxFiles?: number;
  maxFileSize?: number;
  onError?: (error: PromptInputFileError) => void;
  syncHiddenInput?: boolean;
}

interface UsePromptInputFileHandlingResult {
  attachmentsCtx: AttachmentsContext;
  clearAttachments: () => void;
  files: (FileUIPart & { id: string })[];
  formRef: RefObject<HTMLFormElement | null>;
  handleChange: ChangeEventHandler<HTMLInputElement>;
  inputRef: RefObject<HTMLInputElement | null>;
}

export const usePromptInputFileHandling = ({
  accept,
  controller,
  globalDrop,
  maxFiles,
  maxFileSize,
  onError,
  syncHiddenInput,
}: UsePromptInputFileHandlingParams): UsePromptInputFileHandlingResult => {
  const usingProvider = !!controller;

  const inputRef = useRef<HTMLInputElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const [items, setItems] = useState<(FileUIPart & { id: string })[]>([]);
  const files = useMemo(
    () => (usingProvider ? (controller?.attachments.files ?? []) : items),
    [controller, items, usingProvider],
  );

  // Keep a ref to local files for cleanup on unmount (avoids stale closure)
  const filesRef = useRef(files);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  const openFileDialogLocal = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const matchesAccept = useCallback(
    (file: File) => {
      if (!accept || accept.trim() === "") {
        return true;
      }

      const patterns = accept
        .split(",")
        .map((entry) => entry.trim())
        .filter(Boolean);

      return patterns.some((pattern) => {
        if (pattern.endsWith("/*")) {
          const prefix = pattern.slice(0, -1);
          return file.type.startsWith(prefix);
        }
        return file.type === pattern;
      });
    },
    [accept],
  );

  const addLocal = useCallback(
    (fileList: File[] | FileList) => {
      const incoming = [...fileList];
      const accepted = incoming.filter((file) => matchesAccept(file));
      if (incoming.length && accepted.length === 0) {
        onError?.({
          code: "accept",
          message: "No files match the accepted types.",
        });
        return;
      }

      const withinSize = (file: File) => (maxFileSize ? file.size <= maxFileSize : true);
      const sized = accepted.filter(withinSize);
      if (accepted.length > 0 && sized.length === 0) {
        onError?.({
          code: "max_file_size",
          message: "All files exceed the maximum size.",
        });
        return;
      }

      setItems((previous) => {
        const capacity =
          typeof maxFiles === "number" ? Math.max(0, maxFiles - previous.length) : undefined;
        const capped = typeof capacity === "number" ? sized.slice(0, capacity) : sized;
        if (typeof capacity === "number" && sized.length > capacity) {
          onError?.({
            code: "max_files",
            message: "Too many files. Some were not added.",
          });
        }

        const next: (FileUIPart & { id: string })[] = [];
        for (const file of capped) {
          next.push({
            filename: file.name,
            id: nanoid(),
            mediaType: file.type,
            type: "file",
            url: URL.createObjectURL(file),
          });
        }

        return [...previous, ...next];
      });
    },
    [matchesAccept, maxFileSize, maxFiles, onError],
  );

  const removeLocal = useCallback(
    (id: string) =>
      setItems((previous) => {
        const found = previous.find((file) => file.id === id);
        if (found?.url) {
          URL.revokeObjectURL(found.url);
        }
        return previous.filter((file) => file.id !== id);
      }),
    [],
  );

  // Validate files before delegating to provider add.
  const addWithProviderValidation = useCallback(
    (fileList: File[] | FileList) => {
      const incoming = [...fileList];
      const accepted = incoming.filter((file) => matchesAccept(file));
      if (incoming.length && accepted.length === 0) {
        onError?.({
          code: "accept",
          message: "No files match the accepted types.",
        });
        return;
      }

      const withinSize = (file: File) => (maxFileSize ? file.size <= maxFileSize : true);
      const sized = accepted.filter(withinSize);
      if (accepted.length > 0 && sized.length === 0) {
        onError?.({
          code: "max_file_size",
          message: "All files exceed the maximum size.",
        });
        return;
      }

      const currentCount = files.length;
      const capacity =
        typeof maxFiles === "number" ? Math.max(0, maxFiles - currentCount) : undefined;
      const capped = typeof capacity === "number" ? sized.slice(0, capacity) : sized;
      if (typeof capacity === "number" && sized.length > capacity) {
        onError?.({
          code: "max_files",
          message: "Too many files. Some were not added.",
        });
      }

      if (capped.length > 0) {
        controller?.attachments.add(capped);
      }
    },
    [controller, files.length, matchesAccept, maxFileSize, maxFiles, onError],
  );

  const clearAttachments = useCallback(
    () =>
      usingProvider
        ? controller?.attachments.clear()
        : setItems((previous) => {
            for (const file of previous) {
              if (file.url) {
                URL.revokeObjectURL(file.url);
              }
            }
            return [];
          }),
    [controller, usingProvider],
  );

  const add = usingProvider ? addWithProviderValidation : addLocal;
  const remove = usingProvider ? controller.attachments.remove : removeLocal;
  const openFileDialog = usingProvider
    ? controller.attachments.openFileDialog
    : openFileDialogLocal;

  // Let provider know about this file input so external menus can trigger it.
  useEffect(() => {
    if (!usingProvider) {
      return;
    }
    controller.__registerFileInput(inputRef, () => inputRef.current?.click());
  }, [controller, usingProvider]);

  // Note: File input cannot be programmatically set for security reasons.
  // syncHiddenInput is only used to clear the control when attachments are empty.
  useEffect(() => {
    if (syncHiddenInput && inputRef.current && files.length === 0) {
      inputRef.current.value = "";
    }
  }, [files, syncHiddenInput]);

  useEffect(() => {
    const form = formRef.current;
    if (!form || globalDrop) {
      return;
    }

    const onDragOver = (event: DragEvent) => {
      if (event.dataTransfer?.types?.includes("Files")) {
        event.preventDefault();
      }
    };
    const onDrop = (event: DragEvent) => {
      if (event.dataTransfer?.types?.includes("Files")) {
        event.preventDefault();
      }
      if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
        add(event.dataTransfer.files);
      }
    };
    form.addEventListener("dragover", onDragOver);
    form.addEventListener("drop", onDrop);
    return () => {
      form.removeEventListener("dragover", onDragOver);
      form.removeEventListener("drop", onDrop);
    };
  }, [add, globalDrop]);

  useEffect(() => {
    if (!globalDrop) {
      return;
    }

    const onDragOver = (event: DragEvent) => {
      if (event.dataTransfer?.types?.includes("Files")) {
        event.preventDefault();
      }
    };
    const onDrop = (event: DragEvent) => {
      if (event.dataTransfer?.types?.includes("Files")) {
        event.preventDefault();
      }
      if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
        add(event.dataTransfer.files);
      }
    };
    document.addEventListener("dragover", onDragOver);
    document.addEventListener("drop", onDrop);
    return () => {
      document.removeEventListener("dragover", onDragOver);
      document.removeEventListener("drop", onDrop);
    };
  }, [add, globalDrop]);

  useEffect(
    () => () => {
      if (!usingProvider) {
        for (const file of filesRef.current) {
          if (file.url) {
            URL.revokeObjectURL(file.url);
          }
        }
      }
    },
    [usingProvider],
  );

  const handleChange: ChangeEventHandler<HTMLInputElement> = useCallback(
    (event) => {
      if (event.currentTarget.files) {
        add(event.currentTarget.files);
      }
      // Reset input value to allow selecting files that were previously removed.
      event.currentTarget.value = "";
    },
    [add],
  );

  const attachmentsCtx = useMemo<AttachmentsContext>(
    () => ({
      add,
      clear: clearAttachments,
      fileInputRef: inputRef,
      files: files.map((file) => ({ ...file, id: file.id })),
      openFileDialog,
      remove,
    }),
    [files, add, clearAttachments, openFileDialog, remove],
  );

  return {
    attachmentsCtx,
    clearAttachments,
    files,
    formRef,
    handleChange,
    inputRef,
  };
};
