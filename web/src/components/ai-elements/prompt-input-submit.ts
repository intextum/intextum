"use client";

import type { FileUIPart } from "ai";
import type { FormEvent, FormEventHandler } from "react";

import { useCallback } from "react";
import type { PromptInputControllerProps } from "./prompt-input-provider";

interface PromptInputSubmitMessage {
  files: FileUIPart[];
  text: string;
}

interface UsePromptInputSubmitParams {
  clear: () => void;
  controller: PromptInputControllerProps | null;
  files: (FileUIPart & { id: string })[];
  onSubmit: (
    message: PromptInputSubmitMessage,
    event: FormEvent<HTMLFormElement>,
  ) => void | Promise<void>;
}

const convertBlobUrlToDataUrl = async (url: string): Promise<string | null> => {
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    // FileReader uses callback-based API, wrapping in Promise is necessary.
    // oxlint-disable-next-line eslint-plugin-promise(avoid-new)
    return new Promise((resolve) => {
      const reader = new FileReader();
      // oxlint-disable-next-line eslint-plugin-unicorn(prefer-add-event-listener)
      reader.onloadend = () => resolve(reader.result as string);
      // oxlint-disable-next-line eslint-plugin-unicorn(prefer-add-event-listener)
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
};

export const usePromptInputSubmit = ({
  clear,
  controller,
  files,
  onSubmit,
}: UsePromptInputSubmitParams): FormEventHandler<HTMLFormElement> => {
  const usingProvider = !!controller;

  return useCallback(
    async (event) => {
      event.preventDefault();

      const form = event.currentTarget;
      const text = usingProvider
        ? (controller?.textInput.value ?? "")
        : (() => {
            const formData = new FormData(form);
            return (formData.get("message") as string) || "";
          })();

      // Reset form immediately after capturing text to avoid race condition
      // where user input during async blob conversion would be lost.
      if (!usingProvider) {
        form.reset();
      }

      try {
        // Convert blob URLs to data URLs asynchronously.
        const convertedFiles: FileUIPart[] = await Promise.all(
          files.map(async ({ id: _id, ...item }) => {
            if (item.url?.startsWith("blob:")) {
              const dataUrl = await convertBlobUrlToDataUrl(item.url);
              // If conversion failed, keep the original blob URL.
              return {
                ...item,
                url: dataUrl ?? item.url,
              };
            }
            return item;
          }),
        );

        const result = onSubmit({ files: convertedFiles, text }, event);

        // Handle both sync and async onSubmit.
        if (result instanceof Promise) {
          try {
            await result;
            clear();
            if (usingProvider) {
              controller?.textInput.clear();
            }
          } catch {
            // Don't clear on error; user may want to retry.
          }
        } else {
          // Sync function completed without throwing; clear inputs.
          clear();
          if (usingProvider) {
            controller?.textInput.clear();
          }
        }
      } catch {
        // Don't clear on error; user may want to retry.
      }
    },
    [clear, controller, files, onSubmit, usingProvider],
  );
};
