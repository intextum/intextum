import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEnrichmentOnlyProcessingConfig,
  getFileProcessingModeTranslationKey,
  isMissingStoredChunksProcessingError,
  isTerminalContentProcessingStatus,
} from "./content-processing.ts";

test("buildEnrichmentOnlyProcessingConfig always reruns classification and extraction", () => {
  assert.deepEqual(buildEnrichmentOnlyProcessingConfig(), {
    enrichment_only: true,
    document_enrichment: true,
  });
});

test("isMissingStoredChunksProcessingError detects enrichment-only fallback errors", () => {
  assert.equal(
    isMissingStoredChunksProcessingError(
      "No stored chunks available for enrichment-only rerun; run full processing first",
    ),
    true,
  );
  assert.equal(isMissingStoredChunksProcessingError("some other processing error"), false);
  assert.equal(isMissingStoredChunksProcessingError(null), false);
});

test("isTerminalContentProcessingStatus treats revoked processing as finished", () => {
  assert.equal(isTerminalContentProcessingStatus("COMPLETED"), true);
  assert.equal(isTerminalContentProcessingStatus("FAILED"), true);
  assert.equal(isTerminalContentProcessingStatus("REVOKED"), true);
  assert.equal(isTerminalContentProcessingStatus("PROCESSING"), false);
  assert.equal(isTerminalContentProcessingStatus(undefined), false);
});

test("getFileProcessingModeTranslationKey maps stored processing modes", () => {
  assert.equal(
    getFileProcessingModeTranslationKey({ mode: "enrichment_only" }),
    "custom.content.details.processing_mode_enrichment_only",
  );
  assert.equal(
    getFileProcessingModeTranslationKey({ mode: "full" }),
    "custom.content.details.processing_mode_full",
  );
  assert.equal(getFileProcessingModeTranslationKey(null), null);
});
