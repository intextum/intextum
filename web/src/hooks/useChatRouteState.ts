import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ConversationMessage } from "@/dataProvider";
import { conversationMessagesEqual, createClientId } from "@/lib/chat-stream";

type ScopedState<T> = {
  scopeKey: string;
  value: T;
};

export function useChatRouteState({
  defaultPendingThreadId,
  routeScopeKey,
}: {
  defaultPendingThreadId: string | null;
  routeScopeKey: string;
}) {
  const [contextState, setContextState] = useState<ScopedState<string[]>>({
    scopeKey: routeScopeKey,
    value: [],
  });
  const [loadedMessageState, setLoadedMessageState] = useState<ScopedState<ConversationMessage[]>>({
    scopeKey: routeScopeKey,
    value: [],
  });
  const [conversationTitleState, setConversationTitleState] = useState<ScopedState<string | null>>({
    scopeKey: routeScopeKey,
    value: null,
  });
  const [pendingThreadState, setPendingThreadState] = useState<ScopedState<string | null>>({
    scopeKey: routeScopeKey,
    value: defaultPendingThreadId,
  });

  const contextFilePaths = useMemo(
    () => (contextState.scopeKey === routeScopeKey ? contextState.value : []),
    [contextState.scopeKey, contextState.value, routeScopeKey],
  );
  const loadedMessages = useMemo(
    () => (loadedMessageState.scopeKey === routeScopeKey ? loadedMessageState.value : []),
    [loadedMessageState.scopeKey, loadedMessageState.value, routeScopeKey],
  );
  const conversationTitle = useMemo(
    () => (conversationTitleState.scopeKey === routeScopeKey ? conversationTitleState.value : null),
    [conversationTitleState.scopeKey, conversationTitleState.value, routeScopeKey],
  );
  const pendingThreadId =
    pendingThreadState.scopeKey === routeScopeKey
      ? pendingThreadState.value
      : defaultPendingThreadId;

  const contextFilePathsRef = useRef(contextFilePaths);
  useEffect(() => {
    contextFilePathsRef.current = contextFilePaths;
  }, [contextFilePaths]);

  const setConversationTitle = useCallback(
    (title: string | null) => {
      setConversationTitleState({
        scopeKey: routeScopeKey,
        value: title,
      });
    },
    [routeScopeKey],
  );

  const setCurrentContextFilePaths = useCallback(
    (paths: string[]) => {
      contextFilePathsRef.current = paths;
      setContextState({
        scopeKey: routeScopeKey,
        value: paths,
      });
    },
    [routeScopeKey],
  );

  const setContextFilePathsForScope = useCallback((scopeKey: string, paths: string[]) => {
    contextFilePathsRef.current = paths;
    setContextState({
      scopeKey,
      value: paths,
    });
  }, []);

  const updateCurrentContextFilePaths = useCallback(
    (updater: (paths: string[]) => string[]) => {
      setContextState((current) => {
        const nextPaths = updater(current.scopeKey === routeScopeKey ? current.value : []);
        contextFilePathsRef.current = nextPaths;
        return {
          scopeKey: routeScopeKey,
          value: nextPaths,
        };
      });
    },
    [routeScopeKey],
  );

  const syncLoadedMessages = useCallback(
    (nextMessages: ConversationMessage[]) => {
      setLoadedMessageState((current) => {
        if (
          current.scopeKey === routeScopeKey &&
          conversationMessagesEqual(current.value, nextMessages)
        ) {
          return current;
        }

        return {
          scopeKey: routeScopeKey,
          value: nextMessages,
        };
      });
    },
    [routeScopeKey],
  );

  const resetPendingThread = useCallback(() => {
    setPendingThreadState({
      scopeKey: routeScopeKey,
      value: createClientId("thread"),
    });
  }, [routeScopeKey]);

  return {
    contextFilePaths,
    contextFilePathsRef,
    conversationTitle,
    loadedMessages,
    pendingThreadId,
    resetPendingThread,
    setContextFilePathsForScope,
    setConversationTitle,
    setCurrentContextFilePaths,
    syncLoadedMessages,
    updateCurrentContextFilePaths,
  };
}
