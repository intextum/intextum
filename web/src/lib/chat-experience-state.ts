export type ChatExperienceMode = "chat" | "research";

export interface ChatExperienceState {
  mode: ChatExperienceMode;
}

export const readChatExperienceState = (searchParams: URLSearchParams): ChatExperienceState => {
  const explicitMode = searchParams.get("mode") === "research" ? "research" : "chat";

  return {
    mode: explicitMode,
  };
};

export const buildChatExperienceSearch = (
  currentSearchParams: URLSearchParams,
  nextState: ChatExperienceState,
): URLSearchParams => {
  const nextSearchParams = new URLSearchParams(currentSearchParams);

  if (nextState.mode === "research") {
    nextSearchParams.set("mode", "research");
  } else {
    nextSearchParams.delete("mode");
  }

  return nextSearchParams;
};
