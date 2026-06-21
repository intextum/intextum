import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { chatPromptPresetsApi, type ChatPromptPreset } from "@/dataProvider";
import { queryKeys } from "@/lib/query-client";
import { reportClientError } from "@/lib/report-client-error";

type TranslateFn = (key: string, options?: unknown) => string;
type NotifyFn = (
  message: string,
  options?: { type?: "info" | "success" | "warning" | "error" },
) => void;

const EMPTY_PROMPT_PRESETS: ChatPromptPreset[] = [];

export function useChatPromptPresets({
  notify,
  translate,
}: {
  notify: NotifyFn;
  translate: TranslateFn;
}) {
  const promptPresetsQuery = useQuery({
    queryKey: queryKeys.conversations.promptPresets,
    queryFn: chatPromptPresetsApi.list,
  });

  useEffect(() => {
    if (promptPresetsQuery.error) {
      reportClientError(promptPresetsQuery.error, undefined, {
        routeName: "chat:prompt-presets:load",
      });
      notify(translate("custom.pages.chat.presets.load_failed"), { type: "error" });
    }
  }, [notify, promptPresetsQuery.error, translate]);

  return promptPresetsQuery.data?.presets ?? EMPTY_PROMPT_PRESETS;
}
