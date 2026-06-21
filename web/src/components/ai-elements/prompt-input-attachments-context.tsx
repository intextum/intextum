"use client";

import type { ReactNode } from "react";

import { createContext, useContext } from "react";
import type { AttachmentsContext } from "./prompt-input-provider";
import { useProviderAttachments } from "./prompt-input-provider";

const LocalAttachmentsContext = createContext<AttachmentsContext | null>(null);

interface PromptInputAttachmentsProviderProps {
  children: ReactNode;
  value: AttachmentsContext;
}

export const PromptInputAttachmentsProvider = ({
  children,
  value,
}: PromptInputAttachmentsProviderProps) => (
  <LocalAttachmentsContext.Provider value={value}>{children}</LocalAttachmentsContext.Provider>
);

export const usePromptInputAttachments = () => {
  const provider = useProviderAttachments(false);
  const local = useContext(LocalAttachmentsContext);
  const context = local ?? provider;
  if (!context) {
    throw new Error(
      "usePromptInputAttachments must be used within a PromptInput or PromptInputProvider",
    );
  }
  return context;
};
