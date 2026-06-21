import { useCallback, type Dispatch, type MutableRefObject } from "react";
import type { NavigateFunction } from "react-router";
import { conversationsApi, type ChatPromptPreset, type ConversationMessage } from "@/dataProvider";
import { normalizeContextPaths } from "@/hooks/chat-context";
import type { useConversationRun } from "@/hooks/useConversationRun";
import { buildChatExperienceSearch, type ChatExperienceMode } from "@/lib/chat-experience-state";
import { localizedPresetText, promptPresetRequirementMessageKey } from "@/lib/chat-prompt-presets";
import { invalidateConversationQueries } from "@/lib/query-client";
import { buildUserThreadMessage, toConversationMessage, toThreadMessage } from "@/lib/chat-stream";
import { reportClientError } from "@/lib/report-client-error";

type TranslateFn = (key: string, options?: unknown) => string;
type NotifyFn = (
  message: string,
  options?: { type?: "info" | "success" | "warning" | "error" },
) => void;
type ConversationRunControls = ReturnType<typeof useConversationRun>;

export function useChatConversationActions({
  activeThreadId,
  contextFilePathsRef,
  conversationId,
  isLoading,
  joinCreatedRun,
  loadConversation,
  loadedMessages,
  locale,
  messages,
  mode,
  navigate,
  notify,
  pendingThreadId,
  searchParams,
  setChatExperienceMode,
  setComposerText,
  setContextFilePathsForScope,
  streamMessages,
  submit,
  syncLoadedMessages,
  stop,
  translate,
}: {
  activeThreadId: string | null;
  contextFilePathsRef: MutableRefObject<string[]>;
  conversationId: string | undefined;
  isLoading: boolean;
  joinCreatedRun: ConversationRunControls["joinCreatedRun"];
  loadConversation: (conversationId: string) => Promise<void>;
  loadedMessages: ConversationMessage[];
  locale: string;
  messages: ConversationMessage[];
  mode: ChatExperienceMode;
  navigate: NavigateFunction;
  notify: NotifyFn;
  pendingThreadId: string | null;
  searchParams: URLSearchParams;
  setChatExperienceMode: (mode: ChatExperienceMode) => void;
  setComposerText: Dispatch<string>;
  setContextFilePathsForScope: (scopeKey: string, paths: string[]) => void;
  streamMessages: ConversationMessage[];
  submit: ConversationRunControls["submit"];
  syncLoadedMessages: (messages: ConversationMessage[]) => void;
  stop: ConversationRunControls["stop"];
  translate: TranslateFn;
}) {
  const submitConversation = useCallback(
    async (
      runMode: "chat" | "research",
      nextInputMessages: ReturnType<typeof buildUserThreadMessage>[],
      optimisticMessages: ConversationMessage[],
      contextPaths: string[],
      threadId: string,
    ) => {
      await submit({
        conversationId: threadId,
        mode: runMode,
        messages: nextInputMessages,
        contextFilePaths: contextPaths,
        optimisticValues: {
          messages: optimisticMessages.map(toThreadMessage),
          context_file_paths: contextPaths,
        },
      });
    },
    [submit],
  );

  const handleStop = useCallback(() => {
    void stop();
  }, [stop]);

  const handleRegenerateMessage = useCallback(
    async (message: ConversationMessage) => {
      if (!conversationId || isLoading || mode === "research") {
        return;
      }
      const messageIndex = messages.findIndex((item) => item.id === message.id);
      if (message.role !== "assistant" || messageIndex <= 0) {
        return;
      }

      const previousMessages = messages;
      const optimisticMessages = messages.slice(0, messageIndex);
      syncLoadedMessages(optimisticMessages);

      try {
        const created = await conversationsApi.regenerateMessage(conversationId, message.id);
        joinCreatedRun(created, {
          messages: optimisticMessages.map(toThreadMessage),
          context_file_paths: contextFilePathsRef.current,
        });
        void invalidateConversationQueries();
      } catch (error) {
        reportClientError(error, undefined, { routeName: "chat:regenerate-message" });
        syncLoadedMessages(previousMessages);
        notify(
          translate("custom.pages.chat.regenerate_failed", {
            defaultValue: "Failed to regenerate message.",
          }),
          { type: "error" },
        );
        void loadConversation(conversationId);
      }
    },
    [
      contextFilePathsRef,
      conversationId,
      isLoading,
      joinCreatedRun,
      loadConversation,
      messages,
      mode,
      notify,
      syncLoadedMessages,
      translate,
    ],
  );

  const sendMessage = useCallback(
    async (runMode: "chat" | "research", text: string, contextPaths?: string[]) => {
      const trimmedPrompt = text.trim();
      if (!trimmedPrompt) {
        return;
      }
      const threadId = activeThreadId ?? pendingThreadId;
      if (!threadId) {
        throw new Error("No active chat thread ID available for submission.");
      }
      const normalizedContextPaths = contextPaths
        ? normalizeContextPaths(contextPaths)
        : contextFilePathsRef.current;
      const userMessage = buildUserThreadMessage(trimmedPrompt, normalizedContextPaths);
      const optimisticMessages = [
        ...(streamMessages.length > 0 ? streamMessages : loadedMessages),
        toConversationMessage(userMessage) as ConversationMessage,
      ];

      syncLoadedMessages(optimisticMessages);
      await submitConversation(
        runMode,
        [userMessage],
        optimisticMessages,
        normalizedContextPaths,
        threadId,
      );

      if (!conversationId) {
        setContextFilePathsForScope(`conversation:${threadId}`, normalizedContextPaths);
        if (runMode === "research") {
          navigate(
            {
              pathname: `/chat/${threadId}`,
              search: `?${buildChatExperienceSearch(searchParams, { mode: "research" }).toString()}`,
            },
            { replace: true },
          );
        } else {
          navigate(`/chat/${threadId}`, { replace: true });
        }
      }
    },
    [
      activeThreadId,
      contextFilePathsRef,
      conversationId,
      loadedMessages,
      navigate,
      pendingThreadId,
      searchParams,
      setContextFilePathsForScope,
      streamMessages,
      submitConversation,
      syncLoadedMessages,
    ],
  );

  const failureMessageKey = (runMode: "chat" | "research") =>
    runMode === "research"
      ? "custom.pages.research.create_failed"
      : "custom.pages.chat.stream_failed";

  const handleSubmit = useCallback(
    async (message: { text: string }) => {
      const text = message.text.trim();
      if (!text) return;
      try {
        await sendMessage(mode, text);
      } catch (error) {
        reportClientError(error, undefined, { routeName: `chat:submit:${mode}` });
        notify(
          translate(failureMessageKey(mode), {
            _: mode === "research" ? "Failed to start research." : "Chat response failed.",
          }),
          { type: "error" },
        );
      }
    },
    [mode, notify, sendMessage, translate],
  );

  const applyPromptPreset = useCallback(
    async (preset: ChatPromptPreset, contextPaths: string[]) => {
      const requirement = promptPresetRequirementMessageKey(preset, contextPaths.length);
      const prompt = localizedPresetText(preset.prompt, locale);
      setChatExperienceMode(preset.mode);
      setComposerText(prompt);

      if (requirement === "min" || requirement === "max") {
        return false;
      }

      if (preset.action === "fill") {
        return true;
      }

      try {
        await sendMessage(preset.mode, prompt, contextPaths);
        setComposerText("");
        return true;
      } catch (error) {
        reportClientError(error, undefined, { routeName: `chat:preset:${preset.mode}` });
        notify(translate(failureMessageKey(preset.mode)), { type: "error" });
        return false;
      }
    },
    [locale, notify, sendMessage, setChatExperienceMode, setComposerText, translate],
  );

  return {
    applyPromptPreset,
    handleRegenerateMessage,
    handleStop,
    handleSubmit,
  };
}
