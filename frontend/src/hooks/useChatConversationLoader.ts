import { useCallback, useEffect } from "react";
import type { NavigateFunction } from "react-router";
import { conversationsApi, type ConversationMessage } from "@/dataProvider";
import { normalizeContextPaths } from "@/hooks/chat-context";
import { httpErrorStatus, shouldIgnorePendingConversationLoadError } from "@/lib/chat-route-state";
import { reportClientError } from "@/lib/report-client-error";

type TranslateFn = (key: string, options?: unknown) => string;
type NotifyFn = (
  message: string,
  options?: { type?: "info" | "success" | "warning" | "error" },
) => void;

export function useChatConversationLoader({
  conversationId,
  navigate,
  notify,
  setConversationTitle,
  setCurrentContextFilePaths,
  syncLoadedMessages,
  translate,
}: {
  conversationId: string | undefined;
  navigate: NavigateFunction;
  notify: NotifyFn;
  setConversationTitle: (title: string | null) => void;
  setCurrentContextFilePaths: (paths: string[]) => void;
  syncLoadedMessages: (messages: ConversationMessage[]) => void;
  translate: TranslateFn;
}) {
  const handleConversationLoadError = useCallback(
    (error: unknown) => {
      reportClientError(error, undefined, { routeName: "chat:load-conversation" });
      notify(translate("custom.pages.chat.conversation_not_found"), { type: "error" });
      navigate("/chat", { replace: true });
    },
    [navigate, notify, translate],
  );

  const loadConversation = useCallback(
    async (targetConversationId: string) => {
      if (targetConversationId !== conversationId) {
        return;
      }

      try {
        const conversation = await conversationsApi.get(targetConversationId);
        setConversationTitle(conversation.title);
        setCurrentContextFilePaths(normalizeContextPaths(conversation.context_file_paths));
        syncLoadedMessages(conversation.messages);
      } catch (error) {
        handleConversationLoadError(error);
      }
    },
    [
      conversationId,
      handleConversationLoadError,
      setConversationTitle,
      setCurrentContextFilePaths,
      syncLoadedMessages,
    ],
  );

  return { handleConversationLoadError, loadConversation };
}

export function useChatConversationRouteLoad({
  activeThreadId,
  conversationId,
  handleConversationLoadError,
  isLoading,
  setConversationTitle,
  setCurrentContextFilePaths,
  syncLoadedMessages,
}: {
  activeThreadId: string | null;
  conversationId: string | undefined;
  handleConversationLoadError: (error: unknown) => void;
  isLoading: boolean;
  setConversationTitle: (title: string | null) => void;
  setCurrentContextFilePaths: (paths: string[]) => void;
  syncLoadedMessages: (messages: ConversationMessage[]) => void;
}) {
  useEffect(() => {
    if (!conversationId) {
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const conversation = await conversationsApi.get(conversationId);
        if (cancelled) return;
        setConversationTitle(conversation.title);
        setCurrentContextFilePaths(normalizeContextPaths(conversation.context_file_paths));
        syncLoadedMessages(conversation.messages);
      } catch (error) {
        if (cancelled) return;
        if (
          shouldIgnorePendingConversationLoadError({
            activeThreadId,
            conversationId,
            isLoading,
            status: httpErrorStatus(error),
          })
        ) {
          return;
        }
        handleConversationLoadError(error);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [
    activeThreadId,
    conversationId,
    handleConversationLoadError,
    isLoading,
    setConversationTitle,
    setCurrentContextFilePaths,
    syncLoadedMessages,
  ]);
}
