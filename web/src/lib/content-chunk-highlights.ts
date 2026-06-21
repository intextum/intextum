import type { ContentItemChunksResponse } from "@/dataProvider";

const normalizeDocRefs = (docRefs?: string[] | null): string[] =>
  Array.from(
    new Set((docRefs ?? []).map((docRef) => docRef.trim()).filter((docRef) => docRef.length > 0)),
  );

export const chunkMatchesHighlightRefs = (
  chunkDocRefs: string[] | undefined,
  highlightDocRefs: string[] | undefined,
): boolean => {
  const normalizedHighlightRefs = normalizeDocRefs(highlightDocRefs);
  if (normalizedHighlightRefs.length === 0) {
    return false;
  }

  const highlightRefSet = new Set(normalizedHighlightRefs);
  return normalizeDocRefs(chunkDocRefs).some((docRef) => highlightRefSet.has(docRef));
};

export const findFirstHighlightedChunkValue = (
  chunksData: ContentItemChunksResponse | null,
  highlightDocRefs: string[] | undefined,
): string | undefined => {
  if (!chunksData || chunksData.chunks.length === 0) {
    return undefined;
  }

  const match = chunksData.chunks.find((chunk) =>
    chunkMatchesHighlightRefs(chunk.doc_refs, highlightDocRefs),
  );
  return match ? `chunk-${match.chunk_index}` : undefined;
};
