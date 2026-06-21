interface PromptSubmitDisabledInput {
  disableSend: boolean;
  inputText: string;
  isLoading: boolean;
}

export const shouldDisablePromptSubmit = ({
  disableSend,
  inputText,
  isLoading,
}: PromptSubmitDisabledInput): boolean => {
  if (isLoading) {
    return false;
  }
  return disableSend || !inputText.trim();
};
