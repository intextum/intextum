import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  conversationsApi,
  type ConversationRun,
  type CreateConversationRunResponse,
} from "@/dataProvider";
import {
  emptyRunValues,
  markConversationRunReady,
  markConversationRunStreaming,
  shouldDetachActiveRun,
  shouldJoinStoredRun,
  visibleConversationRunState,
  type ConversationRunStatusState,
  type ConversationRunValues,
} from "@/lib/conversation-run-state";
import {
  applyStreamMessageEvent,
  mergeChatStreamState,
  type ChatStreamState,
  type ThreadMessage,
} from "@/lib/chat-stream";
import { readSseStream } from "@/lib/sse-stream";

export interface ConversationProgressEvent {
  event: string;
  message: string;
  phase?: string;
}

interface StoredRunState {
  runId: string;
  lastEventId?: string;
}

interface ActiveRunState {
  conversationId: string;
  runId: string;
  mode: ConversationRun["mode"];
}

interface SubmitRunInput {
  conversationId: string;
  mode: ConversationRun["mode"];
  messages: ThreadMessage[];
  contextFilePaths: string[];
  optimisticValues?: ChatStreamState;
}

const terminalStatuses = new Set<ConversationRun["status"]>(["COMPLETED", "FAILED", "CANCELLED"]);

const storageKeyForConversation = (conversationId: string): string => `chat-run:${conversationId}`;

const readStoredRunState = (conversationId: string): StoredRunState | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.sessionStorage.getItem(storageKeyForConversation(conversationId));
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<StoredRunState>;
    return typeof parsed.runId === "string"
      ? { runId: parsed.runId, lastEventId: parsed.lastEventId }
      : null;
  } catch {
    return null;
  }
};

const writeStoredRunState = (conversationId: string, value: StoredRunState): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(storageKeyForConversation(conversationId), JSON.stringify(value));
};

const clearStoredRunState = (conversationId: string): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(storageKeyForConversation(conversationId));
};

const runStreamUrl = (runId: string, lastEventId?: string): string => {
  const params = new URLSearchParams();
  if (lastEventId) {
    params.set("after", lastEventId);
  }
  const suffix = params.toString();
  return `/api/conversations/runs/${encodeURIComponent(runId)}/stream${suffix ? `?${suffix}` : ""}`;
};

const isActiveRun = (
  activeRun: ActiveRunState | null,
  conversationId: string,
  runId: string,
): boolean => activeRun?.conversationId === conversationId && activeRun.runId === runId;

export const useConversationRun = ({
  activeConversationId,
  onError,
  onRunSettled,
}: {
  activeConversationId: string | null;
  onError: (error: unknown) => void;
  onRunSettled?: (
    conversationId: string,
    mode: ConversationRun["mode"],
    status: ConversationRun["status"],
  ) => void;
}) => {
  const [valuesByConversation, setValuesByConversation] = useState<
    Record<string, ConversationRunValues>
  >({});
  const [eventsByConversation, setEventsByConversation] = useState<
    Record<string, ConversationProgressEvent[]>
  >({});
  const [runStatus, setRunStatus] = useState<ConversationRunStatusState>({
    conversationId: null,
    status: "ready",
  });
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRunRef = useRef<ActiveRunState | null>(null);

  const setConversationValues = useCallback(
    (
      conversationId: string,
      updater: ChatStreamState | ((current: ChatStreamState) => ChatStreamState),
    ) => {
      setValuesByConversation((current) => {
        const currentValues = (current[conversationId] ?? emptyRunValues) as ChatStreamState;
        const nextValues = typeof updater === "function" ? updater(currentValues) : updater;
        if (currentValues === nextValues) {
          return current;
        }
        return {
          ...current,
          [conversationId]: nextValues,
        };
      });
    },
    [],
  );

  const clearConversationValues = useCallback((conversationId: string) => {
    setValuesByConversation((current) => {
      if (!(conversationId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[conversationId];
      return next;
    });
  }, []);

  const markReady = useCallback((conversationId: string) => {
    setRunStatus((current) => markConversationRunReady(current, conversationId));
  }, []);

  const appendProgressEvent = useCallback(
    (conversationId: string, event: ConversationProgressEvent) => {
      setEventsByConversation((current) => ({
        ...current,
        [conversationId]: [...(current[conversationId] ?? []), event],
      }));
    },
    [],
  );

  const clearProgressEvents = useCallback((conversationId: string) => {
    setEventsByConversation((current) => {
      if (!(conversationId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[conversationId];
      return next;
    });
  }, []);

  const clearActiveRun = useCallback((conversationId: string, runId?: string) => {
    const stored = readStoredRunState(conversationId);
    if (!runId || stored?.runId === runId) {
      clearStoredRunState(conversationId);
    }
    if (
      activeRunRef.current?.conversationId === conversationId &&
      (!runId || activeRunRef.current.runId === runId)
    ) {
      activeRunRef.current = null;
    }
  }, []);

  const applyRunEvent = useCallback(
    (
      conversationId: string,
      runId: string,
      mode: ConversationRun["mode"],
      event: string,
      data: unknown,
      eventId?: string,
    ) => {
      if (eventId) {
        writeStoredRunState(conversationId, { runId, lastEventId: eventId });
      }

      if (event === "messages") {
        setConversationValues(conversationId, (current) => applyStreamMessageEvent(current, data));
        return;
      }
      if (event === "values") {
        setConversationValues(conversationId, (current) => mergeChatStreamState(current, data));
        return;
      }
      if (event === "progress" && typeof data === "object" && data !== null) {
        const payload = data as { message?: unknown; phase?: unknown };
        appendProgressEvent(conversationId, {
          event: "progress",
          message:
            typeof payload.message === "string" ? payload.message : "Research progress updated.",
          phase: typeof payload.phase === "string" ? payload.phase : undefined,
        });
        return;
      }
      if (event === "done") {
        const settledStatus =
          typeof data === "object" &&
          data !== null &&
          "status" in data &&
          typeof (data as { status?: unknown }).status === "string"
            ? ((data as { status: ConversationRun["status"] }).status ?? "COMPLETED")
            : "COMPLETED";
        clearProgressEvents(conversationId);
        if (mode === "research") {
          clearConversationValues(conversationId);
        }
        clearActiveRun(conversationId, runId);
        markReady(conversationId);
        onRunSettled?.(conversationId, mode, settledStatus);
        return;
      }
      if (event === "error") {
        clearProgressEvents(conversationId);
        if (mode === "research") {
          clearConversationValues(conversationId);
        }
        clearActiveRun(conversationId, runId);
        markReady(conversationId);
        onRunSettled?.(conversationId, mode, "FAILED");
        onError(data);
      }
    },
    [
      appendProgressEvent,
      clearProgressEvents,
      clearConversationValues,
      clearActiveRun,
      markReady,
      onError,
      onRunSettled,
      setConversationValues,
    ],
  );

  const joinRun = useCallback(
    async (
      conversationId: string,
      runId: string,
      mode: ConversationRun["mode"],
      lastEventId?: string,
    ) => {
      abortControllerRef.current?.abort();
      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      activeRunRef.current = { conversationId, runId, mode };
      setRunStatus(markConversationRunStreaming(conversationId));

      try {
        const response = await fetch(runStreamUrl(runId, lastEventId), {
          credentials: "include",
          signal: abortController.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error(`Failed to join chat run stream (${response.status})`);
        }

        await readSseStream(response.body, (frame) => {
          applyRunEvent(conversationId, runId, mode, frame.event, frame.data, frame.id);
        });

        const run = await conversationsApi.getRun(runId);
        if (terminalStatuses.has(run.status)) {
          clearProgressEvents(conversationId);
          if (mode === "research") {
            clearConversationValues(conversationId);
          }
          clearActiveRun(conversationId, runId);
          markReady(conversationId);
          onRunSettled?.(conversationId, mode, run.status);
        }
      } catch (error) {
        if (abortController.signal.aborted) {
          if (isActiveRun(activeRunRef.current, conversationId, runId)) {
            markReady(conversationId);
          }
          return;
        }
        markReady(conversationId);
        onError(error);
      }
    },
    [
      applyRunEvent,
      clearProgressEvents,
      clearActiveRun,
      clearConversationValues,
      markReady,
      onError,
      onRunSettled,
    ],
  );

  const submit = useCallback(
    async ({
      conversationId,
      mode,
      messages,
      contextFilePaths,
      optimisticValues,
    }: SubmitRunInput) => {
      if (optimisticValues) {
        setConversationValues(conversationId, optimisticValues);
      }
      if (mode === "research") {
        setEventsByConversation((current) => ({ ...current, [conversationId]: [] }));
      }
      const payload = {
        input: {
          messages,
          context_file_paths: contextFilePaths,
          mode,
        },
        config: {
          configurable: {
            thread_id: conversationId,
          },
        },
      };

      let created;
      try {
        created = await conversationsApi.createRun(payload);
      } catch (error) {
        markReady(conversationId);
        throw error;
      }

      writeStoredRunState(conversationId, { runId: created.run_id });
      void joinRun(conversationId, created.run_id, created.mode);
    },
    [joinRun, markReady, setConversationValues],
  );

  const joinCreatedRun = useCallback(
    (created: CreateConversationRunResponse, optimisticValues?: ChatStreamState) => {
      if (optimisticValues) {
        setConversationValues(created.conversation_id, optimisticValues);
      }
      if (created.mode === "research") {
        setEventsByConversation((current) => ({ ...current, [created.conversation_id]: [] }));
      }
      writeStoredRunState(created.conversation_id, { runId: created.run_id });
      void joinRun(created.conversation_id, created.run_id, created.mode);
    },
    [joinRun, setConversationValues],
  );

  const stop = useCallback(() => {
    const activeRun = activeRunRef.current;
    const activeConversation = activeRun?.conversationId;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    activeRunRef.current = null;
    if (activeConversation) {
      markReady(activeConversation);
    }
    if (!activeRun) {
      return;
    }
    if (activeRun.mode === "research") {
      clearProgressEvents(activeRun.conversationId);
      clearConversationValues(activeRun.conversationId);
    }
    void conversationsApi
      .cancelRun(activeRun.runId)
      .then(() => clearActiveRun(activeRun.conversationId, activeRun.runId))
      .catch(onError);
  }, [clearActiveRun, clearConversationValues, clearProgressEvents, markReady, onError]);

  useEffect(() => {
    const activeRun = activeRunRef.current;
    if (!shouldDetachActiveRun(activeRun, activeConversationId)) {
      return;
    }

    // Detach the visible UI from the previous run when navigating away.
    // The backend run keeps going and can be rejoined from sessionStorage later.
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    activeRunRef.current = null;
  }, [activeConversationId]);

  useEffect(() => {
    if (!activeConversationId) {
      return;
    }

    const stored = readStoredRunState(activeConversationId);
    if (!stored) {
      return;
    }
    if (
      activeRunRef.current?.conversationId === activeConversationId &&
      activeRunRef.current.runId === stored.runId
    ) {
      return;
    }

    void conversationsApi
      .getRun(stored.runId)
      .then((run) => {
        if (!shouldJoinStoredRun(run, activeConversationId)) {
          clearActiveRun(activeConversationId, stored.runId);
          return;
        }
        void joinRun(activeConversationId, stored.runId, run.mode, stored.lastEventId);
      })
      .catch(() => clearActiveRun(activeConversationId, stored.runId));
  }, [activeConversationId, clearActiveRun, joinRun]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const visibleState = visibleConversationRunState(
    valuesByConversation,
    runStatus,
    activeConversationId,
  );
  const activeProgressEvents = useMemo(
    () =>
      activeConversationId && eventsByConversation[activeConversationId]
        ? eventsByConversation[activeConversationId]
        : [],
    [activeConversationId, eventsByConversation],
  );
  const activeRunMode =
    activeRunRef.current?.conversationId === activeConversationId
      ? activeRunRef.current.mode
      : null;

  return useMemo(
    () => ({
      values: visibleState.values as ChatStreamState,
      progressEvents: activeProgressEvents,
      activeRunMode,
      joinCreatedRun,
      submit,
      stop,
      isLoading: visibleState.isLoading,
    }),
    [
      activeProgressEvents,
      activeRunMode,
      joinCreatedRun,
      stop,
      submit,
      visibleState.isLoading,
      visibleState.values,
    ],
  );
};
