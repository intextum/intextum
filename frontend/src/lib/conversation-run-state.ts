export type ConversationRunStatus = "ready" | "streaming";

export type ConversationRunValues = Record<string, unknown>;

export interface ConversationRunStatusState {
  conversationId: string | null;
  status: ConversationRunStatus;
}

export interface ActiveConversationRun {
  conversationId: string;
  runId: string;
}

export interface StoredConversationRunRecord {
  conversation_id: string;
  status?: string;
}

export interface VisibleConversationRunState {
  values: ConversationRunValues;
  isLoading: boolean;
}

export const emptyRunValues: ConversationRunValues = {};

export const markConversationRunStreaming = (
  conversationId: string,
): ConversationRunStatusState => ({
  conversationId,
  status: "streaming",
});

export const markConversationRunReady = (
  current: ConversationRunStatusState,
  conversationId: string,
): ConversationRunStatusState =>
  current.conversationId === conversationId ? { conversationId: null, status: "ready" } : current;

export const shouldDetachActiveRun = (
  activeRun: ActiveConversationRun | null,
  activeConversationId: string | null,
): boolean => Boolean(activeRun && activeRun.conversationId !== activeConversationId);

export const shouldJoinStoredRun = (
  run: StoredConversationRunRecord,
  activeConversationId: string | null,
): boolean => run.conversation_id === activeConversationId;

export const visibleConversationRunState = (
  valuesByConversation: Record<string, ConversationRunValues>,
  runStatus: ConversationRunStatusState,
  activeConversationId: string | null,
): VisibleConversationRunState => ({
  values: activeConversationId
    ? (valuesByConversation[activeConversationId] ?? emptyRunValues)
    : emptyRunValues,
  isLoading: runStatus.conversationId === activeConversationId && runStatus.status === "streaming",
});
