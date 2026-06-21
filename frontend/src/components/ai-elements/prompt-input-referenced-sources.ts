"use client";

import type { SourceDocumentUIPart } from "ai";

import { nanoid } from "nanoid";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

export interface ReferencedSourcesContext {
  sources: (SourceDocumentUIPart & { id: string })[];
  add: (sources: SourceDocumentUIPart[] | SourceDocumentUIPart) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const LocalReferencedSourcesContext = createContext<ReferencedSourcesContext | null>(null);

export const usePromptInputReferencedSources = () => {
  const context = useContext(LocalReferencedSourcesContext);
  if (!context) {
    throw new Error(
      "usePromptInputReferencedSources must be used within a LocalReferencedSourcesContext.Provider",
    );
  }
  return context;
};

interface UsePromptInputReferencedSourcesStateResult {
  clearReferencedSources: () => void;
  refsCtx: ReferencedSourcesContext;
}

export const usePromptInputReferencedSourcesState =
  (): UsePromptInputReferencedSourcesStateResult => {
    const [referencedSources, setReferencedSources] = useState<
      (SourceDocumentUIPart & { id: string })[]
    >([]);

    const clearReferencedSources = useCallback(() => setReferencedSources([]), []);

    const refsCtx = useMemo<ReferencedSourcesContext>(
      () => ({
        add: (incoming: SourceDocumentUIPart[] | SourceDocumentUIPart) => {
          const array = Array.isArray(incoming) ? incoming : [incoming];
          setReferencedSources((previous) => [
            ...previous,
            ...array.map((source) => ({ ...source, id: nanoid() })),
          ]);
        },
        clear: clearReferencedSources,
        remove: (id: string) => {
          setReferencedSources((previous) => previous.filter((source) => source.id !== id));
        },
        sources: referencedSources,
      }),
      [referencedSources, clearReferencedSources],
    );

    return {
      clearReferencedSources,
      refsCtx,
    };
  };
