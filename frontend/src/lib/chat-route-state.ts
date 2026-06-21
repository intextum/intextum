interface PendingConversationLoadErrorInput {
  activeThreadId: string | null;
  conversationId: string;
  isLoading: boolean;
  status: number | undefined;
}

export const httpErrorStatus = (error: unknown): number | undefined => {
  if (typeof error !== "object" || error === null || !("status" in error)) {
    return undefined;
  }

  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : undefined;
};

export const shouldIgnorePendingConversationLoadError = ({
  activeThreadId,
  conversationId,
  isLoading,
  status,
}: PendingConversationLoadErrorInput): boolean =>
  status === 404 && isLoading && activeThreadId === conversationId;
