import assert from "node:assert/strict";
import test from "node:test";

import type { ContentItemInfo } from "../dataProvider.ts";
import {
  buildDocumentClassFilterChips,
  buildDocumentExtractionHighlights,
  buildContentReviewSubmitPayload,
  buildExtractionSchemaFilterChips,
  buildExtractionValueFilterChips,
  canReviewDocumentData,
  collectCommonDocumentClasses,
  collectCommonExtractionFields,
  getContentEnrichmentReviewReasons,
  getContentEnrichmentReviewStatus,
  getContentReviewState,
  getInitialContentDetailsMode,
  getDocumentClassificationLabel,
  getDocumentExtractionSchema,
  hasNeedsReviewContentEnrichment,
  hasStaleContentEnrichment,
  isObjectRecord,
  isUserCorrectedClassification,
  matchesDocumentClassificationFilter,
  matchesDocumentExtractionFilter,
} from "./content-enrichment.ts";

test("isObjectRecord matches plain JSON objects", () => {
  assert.equal(isObjectRecord({ a: 1 }), true);
  assert.equal(isObjectRecord(null), false);
  assert.equal(isObjectRecord(["a"]), false);
});

test("buildContentReviewSubmitPayload includes only confirmed review parts", () => {
  assert.deepEqual(
    buildContentReviewSubmitPayload({
      classificationLabel: " Invoice ",
      extractionData: { gross_amount: 19.99 },
      includeClassification: true,
      includeExtraction: true,
    }),
    {
      classification_label: "Invoice",
      extraction_data: { gross_amount: 19.99 },
    },
  );
  assert.equal(
    buildContentReviewSubmitPayload({
      classificationLabel: " ",
      extractionData: null,
      includeClassification: true,
      includeExtraction: true,
    }),
    null,
  );
});

test("content details mode defaults to document data", () => {
  assert.equal(getInitialContentDetailsMode(), "document_data");
  assert.equal(getInitialContentDetailsMode("document_data"), "document_data");
});

test("document data control is available only for processed reviewable enrichment items", () => {
  const reviewableCapabilities = {
    supports_chunking: true,
    supports_search: true,
    supports_enrichment: true,
    supports_review: true,
  };
  const reviewableFile = {
    status: "COMPLETED",
    capabilities: reviewableCapabilities,
  } as ContentItemInfo;
  assert.equal(canReviewDocumentData(reviewableFile), true);
  assert.equal(canReviewDocumentData({ ...reviewableFile, status: "PROCESSING" }), false);
  assert.equal(
    canReviewDocumentData({
      ...reviewableFile,
      capabilities: { ...reviewableCapabilities, supports_review: false },
    }),
    false,
  );
});

test("getContentReviewState maps accepted and corrected to reviewed", () => {
  assert.equal(
    getContentReviewState({
      document_classification: { review_status: "accepted" },
      document_extraction: { review_status: "corrected" },
    } as never),
    "reviewed",
  );
  assert.equal(
    getContentReviewState({
      document_classification: { label: "Invoice" },
    } as never),
    "needs_review",
  );
});

test("classification helpers read effective labels and correction provenance", () => {
  assert.equal(getDocumentClassificationLabel({ label: "Invoice" }), "Invoice");
  assert.equal(getDocumentClassificationLabel({ label: "" }), null);
  assert.equal(getDocumentClassificationLabel(null), null);
  assert.equal(getDocumentExtractionSchema({ schema_name: "invoice_fields" }), "invoice_fields");
  assert.equal(getDocumentExtractionSchema({ schema_name: "" }), null);
  assert.equal(isUserCorrectedClassification({ source: "user_override" }), true);
  assert.equal(isUserCorrectedClassification({ source: "model" }), false);
});

test("matchesDocumentClassificationFilter handles empty, partial, and missing labels", () => {
  assert.equal(matchesDocumentClassificationFilter({ label: "Invoice" }, ""), true);
  assert.equal(matchesDocumentClassificationFilter({ label: "Invoice" }, "invoice"), true);
  assert.equal(matchesDocumentClassificationFilter({ label: "Invoice" }, "voice"), true);
  assert.equal(matchesDocumentClassificationFilter({ label: "Permit" }, "invoice"), false);
  assert.equal(matchesDocumentClassificationFilter(null, "invoice"), false);
});

test("matchesDocumentExtractionFilter handles global and field-specific matches", () => {
  const extraction = {
    data: {
      invoice_number: "RE-2026-0042",
      gross_amount: 119.99,
      line_items: [{ label: "Planning" }, { label: "Survey" }],
    },
  };

  assert.equal(matchesDocumentExtractionFilter(extraction, ""), true);
  assert.equal(matchesDocumentExtractionFilter(extraction, "2026"), true);
  assert.equal(matchesDocumentExtractionFilter(extraction, "survey"), true);
  assert.equal(matchesDocumentExtractionFilter(extraction, "2026", "invoice_number"), true);
  assert.equal(matchesDocumentExtractionFilter(extraction, "119.99", "gross_amount"), true);
  assert.equal(matchesDocumentExtractionFilter(extraction, "survey", "invoice_number"), false);
  assert.equal(matchesDocumentExtractionFilter(extraction, "missing"), false);
  assert.equal(matchesDocumentExtractionFilter(null, "2026"), false);
});

test("collectCommonDocumentClasses counts and sorts visible classes", () => {
  assert.deepEqual(
    collectCommonDocumentClasses([
      { label: "Invoice" },
      { label: "Permit" },
      { label: "Invoice" },
      null,
      { label: " " },
    ]),
    ["Invoice", "Permit"],
  );
});

test("collectCommonExtractionFields counts top data keys", () => {
  assert.deepEqual(
    collectCommonExtractionFields([
      { data: { invoice_number: "A", gross_amount: 1 } },
      { data: { invoice_number: "B", currency: "EUR" } },
      { data: { gross_amount: 2 } },
      null,
    ]),
    ["gross_amount", "invoice_number", "currency"],
  );
});

test("buildDocumentExtractionHighlights prioritizes important scalar fields", () => {
  assert.deepEqual(
    buildDocumentExtractionHighlights({
      data: {
        authority: "Landkreis Example",
        invoice_number: "RE-2026-0042",
        gross_amount: 119.99,
        notes: { ignored: true },
      },
    }),
    [
      { key: "invoice_number", label: "invoice number", value: "RE-2026-0042" },
      { key: "gross_amount", label: "gross amount", value: "119.99" },
    ],
  );
});

test("buildDocumentClassFilterChips keeps the active filter visible", () => {
  assert.deepEqual(buildDocumentClassFilterChips([{ label: "Invoice", count: 4 }], "Permit"), [
    { value: "Permit", count: null, active: true },
    { value: "Invoice", count: 4, active: false },
  ]);
});

test("buildExtractionValueFilterChips marks active known values and preserves unknown ones", () => {
  assert.deepEqual(
    buildExtractionValueFilterChips(
      [
        { value: "approved", count: 4 },
        { value: "rejected", count: 2 },
      ],
      "rejected",
    ),
    [
      { value: "approved", count: 4, active: false },
      { value: "rejected", count: 2, active: true },
    ],
  );
  assert.deepEqual(buildExtractionValueFilterChips([{ value: "approved", count: 4 }], "pending"), [
    { value: "pending", count: null, active: true },
    { value: "approved", count: 4, active: false },
  ]);
});

test("buildExtractionSchemaFilterChips marks active known schemas and preserves unknown ones", () => {
  assert.deepEqual(
    buildExtractionSchemaFilterChips(
      [
        { schema_name: "invoice_fields", count: 4 },
        { schema_name: "permit_core", count: 2 },
      ],
      "permit_core",
    ),
    [
      { value: "invoice_fields", count: 4, active: false },
      { value: "permit_core", count: 2, active: true },
    ],
  );
  assert.deepEqual(
    buildExtractionSchemaFilterChips(
      [{ schema_name: "invoice_fields", count: 4 }],
      "custom_schema",
    ),
    [
      { value: "custom_schema", count: null, active: true },
      { value: "invoice_fields", count: 4, active: false },
    ],
  );
});

test("hasStaleContentEnrichment detects stale lifecycle state", () => {
  assert.equal(hasStaleContentEnrichment({ stale: true }, null), true);
  assert.equal(hasStaleContentEnrichment(null, { stale: true }), true);
  assert.equal(hasStaleContentEnrichment({ stale: false }, { stale: false }), false);
});

test("getContentEnrichmentReviewStatus prioritizes corrected, then unreviewed, then accepted", () => {
  assert.equal(
    getContentEnrichmentReviewStatus(
      { label: "Invoice", review_status: "accepted" },
      { review_status: "corrected" },
    ),
    "corrected",
  );
  assert.equal(
    getContentEnrichmentReviewStatus({ label: "Invoice" }, { review_status: "accepted" }),
    "unreviewed",
  );
  assert.equal(
    getContentEnrichmentReviewStatus(
      { label: "Invoice", review_status: "accepted" },
      { review_status: "accepted" },
    ),
    "accepted",
  );
  assert.equal(getContentEnrichmentReviewStatus(null, null), null);
});

test("hasNeedsReviewContentEnrichment reads effective extraction summary", () => {
  assert.equal(hasNeedsReviewContentEnrichment({ summary: { needs_review: true } }), true);
  assert.equal(hasNeedsReviewContentEnrichment({ summary: { needs_review: false } }), false);
  assert.equal(hasNeedsReviewContentEnrichment(null), false);
});

test("getContentEnrichmentReviewReasons merges classification and extraction reasons", () => {
  assert.deepEqual(
    getContentEnrichmentReviewReasons(
      { review_reasons: [{ code: "missing_evidence" }] },
      {
        summary: {
          review_reasons: [
            { code: "conflicted_fields" },
            { code: "missing_required_fields" },
            { code: "missing_evidence" },
          ],
        },
      },
    ),
    ["missing_required_fields", "conflicted_fields", "missing_evidence"],
  );
});
