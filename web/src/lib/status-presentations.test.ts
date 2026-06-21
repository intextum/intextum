import assert from "node:assert/strict";
import test from "node:test";

import type { ContentItemInfo } from "../dataProvider.ts";
import {
  contentStatusPresentation,
  itemFlowPresentation,
  reviewStatePresentation,
  stageLabel,
} from "./status-presentations.ts";

const contentItem = (overrides: Partial<ContentItemInfo> = {}): ContentItemInfo =>
  ({
    id: "content-1",
    name: "invoice.pdf",
    display_name: "invoice.pdf",
    path: "/inbox/invoice.pdf",
    kind: "file",
    type: "file",
    size_bytes: 128,
    size_human: "128 B",
    modified_at: "2026-04-30T10:00:00Z",
    is_hidden: false,
    ...overrides,
  }) as ContentItemInfo;

test("contentStatusPresentation maps processing failures to actionable error copy", () => {
  const presentation = contentStatusPresentation("FAILED");

  assert.equal(presentation.severity, "error");
  assert.equal(presentation.badgeVariant, "destructive");
  assert.equal(presentation.labelKey, "custom.content.status.failed");
  assert.equal(presentation.descriptionKey, "custom.status_presentations.content.failed");
  assert.equal(presentation.actionKey, "custom.status_presentations.content.failed_action");
});

test("contentStatusPresentation treats missing status as uploaded and not processed", () => {
  const presentation = contentStatusPresentation(undefined);

  assert.equal(presentation.severity, "neutral");
  assert.equal(presentation.labelKey, "custom.status_presentations.content.not_processed_label");
  assert.equal(presentation.actionKey, "custom.content.actions.process");
});

test("reviewStatePresentation prioritizes stale enrichment before review reasons", () => {
  const presentation = reviewStatePresentation(
    contentItem({
      document_enrichment: {
        review_state: "stale",
        classification_lifecycle: { stale: true },
      },
      document_extraction: {
        summary: { review_reasons: [{ code: "missing_evidence" }] },
      },
    }),
  );

  assert.equal(presentation.status, "stale");
  assert.equal(presentation.severity, "warning");
  assert.equal(presentation.actionKey, "custom.content.actions.rerun_enrichment");
});

test("reviewStatePresentation exposes missing evidence as review reason", () => {
  const presentation = reviewStatePresentation(
    contentItem({
      document_extraction: {
        summary: { review_reasons: [{ code: "missing_evidence" }] },
      },
    }),
  );

  assert.equal(presentation.status, "needs_review");
  assert.deepEqual(presentation.reasons, ["missing_evidence"]);
  assert.equal(presentation.descriptionKey, "custom.status_presentations.review.missing_evidence");
  assert.equal(
    presentation.actionKey,
    "custom.status_presentations.review.missing_evidence_action",
  );
});

test("reviewStatePresentation maps accepted and corrected outcomes", () => {
  const accepted = reviewStatePresentation(
    contentItem({
      document_classification: { review_status: "accepted" },
      document_extraction: { review_status: "accepted" },
    }),
  );
  const corrected = reviewStatePresentation(
    contentItem({
      document_classification: { review_status: "corrected" },
      document_extraction: { review_status: "accepted" },
    }),
  );

  assert.equal(accepted.status, "reviewed");
  assert.equal(accepted.severity, "success");
  assert.equal(corrected.status, "reviewed");
  assert.equal(corrected.severity, "success");
});

test("stageLabel returns null for empty stages without translating", () => {
  let calls = 0;
  const translate = (key: string) => {
    calls += 1;
    return key;
  };

  assert.equal(stageLabel(null, translate), null);
  assert.equal(stageLabel(undefined, translate), null);
  assert.equal(stageLabel("", translate), null);
  assert.equal(calls, 0);
});

test("stageLabel localizes known stages via the status_presentations namespace", () => {
  const translate = (key: string) => `t:${key}`;

  assert.equal(stageLabel("chunking", translate), "t:custom.status_presentations.stages.chunking");
});

test("stageLabel falls back to the raw key for unknown stages", () => {
  let calls = 0;
  const translate = (key: string) => {
    calls += 1;
    return key;
  };

  assert.equal(stageLabel("some_future_stage", translate), "some_future_stage");
  assert.equal(calls, 0);
});

test("itemFlowPresentation keeps failed processing ahead of review state", () => {
  const presentation = itemFlowPresentation(
    contentItem({
      status: "FAILED",
      document_classification: { review_status: "accepted" },
    }),
  );

  assert.equal(presentation.labelKey, "custom.content.status.failed");
  assert.equal(presentation.severity, "error");
});
