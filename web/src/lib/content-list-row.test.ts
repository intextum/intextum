import assert from "node:assert/strict";
import test from "node:test";

import type { ContentItemInfo } from "@/dataProvider";

import { buildContentListRowModel } from "./content-list-row.ts";

function createContentItem(overrides: Partial<ContentItemInfo> = {}): ContentItemInfo {
  return {
    id: "item-1",
    name: "permit.pdf",
    display_name: "permit.pdf",
    path: "inbox/permit.pdf",
    kind: "file",
    type: "file",
    extension: "pdf",
    size_bytes: 1024,
    size_human: "1 KB",
    modified_at: "2026-06-21T10:00:00Z",
    is_hidden: false,
    status: "COMPLETED",
    ...overrides,
  };
}

test("buildContentListRowModel keeps completed processed rows quiet", () => {
  const model = buildContentListRowModel(
    createContentItem({
      processing_mode: {
        mode: "enrichment_only",
        enrichment_only: true,
        document_enrichment: true,
      },
      document_extraction: {
        schema_name: "PermitExtraction",
      },
    }),
  );

  assert.deepEqual(model, {
    folderPath: "inbox",
    isProcessing: false,
    visibleStatus: null,
    showDocumentClassBadge: false,
    showNeedsReviewBadge: false,
  });
});

test("buildContentListRowModel preserves row-level attention signals", () => {
  const model = buildContentListRowModel(
    createContentItem({
      status: "FAILED",
      document_classification: {
        label: "Building permit",
      },
      document_extraction: {
        summary: {
          needs_review: true,
        },
      },
      document_enrichment: {
        review_state: "needs_review",
      },
    }),
  );

  assert.deepEqual(model, {
    folderPath: "inbox",
    isProcessing: false,
    visibleStatus: "FAILED",
    showDocumentClassBadge: true,
    showNeedsReviewBadge: true,
  });
});

test("buildContentListRowModel keeps active processing visible and disables rerun action", () => {
  const model = buildContentListRowModel(
    createContentItem({
      status: "PROCESSING",
      path: "permit.pdf",
    }),
  );

  assert.deepEqual(model, {
    folderPath: "",
    isProcessing: true,
    visibleStatus: "PROCESSING",
    showDocumentClassBadge: false,
    showNeedsReviewBadge: false,
  });
});
