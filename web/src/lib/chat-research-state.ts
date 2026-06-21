export interface ResearchRunSettledState {
  currentMode: "chat" | "research";
  activeThreadId: string | null;
  settledConversationId: string;
  settledMode: "chat" | "research";
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
}

export const shouldResetResearchComposerMode = ({
  currentMode,
  activeThreadId,
  settledConversationId,
  settledMode,
  status,
}: ResearchRunSettledState): boolean =>
  currentMode === "research" &&
  settledMode === "research" &&
  status === "COMPLETED" &&
  activeThreadId === settledConversationId;

export const shouldShowTransientResearchBlock = ({
  activeRunMode,
  progressEventCount,
}: {
  activeRunMode: "chat" | "research" | null;
  progressEventCount: number;
}): boolean => activeRunMode === "research" || progressEventCount > 0;
