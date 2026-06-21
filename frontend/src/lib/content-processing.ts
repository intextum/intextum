export interface ContentItemProcessingModeSummaryLike {
  mode: "full" | "enrichment_only";
}

const MISSING_STORED_CHUNKS_ERROR =
  "No stored chunks available for enrichment-only rerun; run full processing first";

export function buildEnrichmentOnlyProcessingConfig(): Record<string, unknown> {
  return {
    enrichment_only: true,
    document_enrichment: true,
  };
}

export function isMissingStoredChunksProcessingError(error?: string | null): boolean {
  return typeof error === "string" && error.includes(MISSING_STORED_CHUNKS_ERROR);
}

export function isTerminalContentProcessingStatus(status?: string | null): boolean {
  return status === "COMPLETED" || status === "FAILED" || status === "REVOKED";
}

export function getFileProcessingModeTranslationKey(
  processingMode: ContentItemProcessingModeSummaryLike | null | undefined,
): string | null {
  switch (processingMode?.mode) {
    case "full":
      return "custom.content.details.processing_mode_full";
    case "enrichment_only":
      return "custom.content.details.processing_mode_enrichment_only";
    default:
      return null;
  }
}
