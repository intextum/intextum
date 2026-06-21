import assert from "node:assert/strict";
import test from "node:test";

import {
  buildClassificationAuditSummary,
  buildExtractionAuditSummary,
} from "./content-review-audit.ts";

test("buildClassificationAuditSummary exposes review state and latest history entry", () => {
  const summary = buildClassificationAuditSummary(
    {
      label: "Permit",
      review_status: "corrected",
      review_history: [
        { action: "accepted", updated_by: "Alice", updated_at: "2026-04-20T10:00:00Z" },
        {
          action: "corrected",
          label: "Permit",
          updated_by: "Bob",
          updated_at: "2026-04-21T11:00:00Z",
        },
      ],
    },
    { label: "Invoice" },
  );

  assert.deepEqual(summary, {
    effectiveLabel: "Permit",
    aiLabel: "Invoice",
    reviewStatus: "corrected",
    matchesAi: false,
    latestReviewEntry: {
      action: "corrected",
      updatedAt: "2026-04-21T11:00:00Z",
      updatedBy: "Bob",
      label: "Permit",
      fields: [],
    },
  });
});

test("buildClassificationAuditSummary falls back to unreviewed when labels exist without review state", () => {
  const summary = buildClassificationAuditSummary({ label: "Invoice" }, { label: "Invoice" });

  assert.deepEqual(summary, {
    effectiveLabel: "Invoice",
    aiLabel: "Invoice",
    reviewStatus: "unreviewed",
    matchesAi: true,
    latestReviewEntry: null,
  });
});

test("buildExtractionAuditSummary counts changed, unchanged, override, and review blocker fields", () => {
  const summary = buildExtractionAuditSummary(
    {
      review_history: [
        {
          action: "corrected",
          fields: ["gross_amount", "line_items"],
          updated_by: "Casey",
          updated_at: "2026-04-22T12:00:00Z",
        },
      ],
      data: {
        gross_amount: 125,
        invoice_number: "RE-42",
        line_items: [{ qty: 1, label: "Planning" }],
      },
      fields: {
        gross_amount: { overridden: true, evidence: [] },
        invoice_number: { evidence: [{ snippet: "RE-42" }] },
        line_items: { overridden: true, evidence: [] },
      },
      summary: {
        fields_with_evidence: 1,
        fields_without_evidence: ["gross_amount"],
        missing_required_fields: ["due_date"],
        conflicted_fields: ["gross_amount", "line_items"],
      },
    },
    {
      data: {
        gross_amount: 119,
        invoice_number: "RE-42",
        line_items: [{ label: "Planning", qty: 1 }],
      },
    },
  );

  assert.deepEqual(summary, {
    reviewStatus: "corrected",
    totalComparableFields: 3,
    changedFieldCount: 1,
    unchangedFieldCount: 2,
    overrideFieldCount: 2,
    fieldsWithEvidenceCount: 1,
    missingEvidenceCount: 1,
    missingRequiredCount: 1,
    conflictedCount: 2,
    reviewBlockerCount: 3,
    changedFields: ["gross_amount"],
    latestReviewEntry: {
      action: "corrected",
      updatedAt: "2026-04-22T12:00:00Z",
      updatedBy: "Casey",
      label: null,
      fields: ["gross_amount", "line_items"],
    },
  });
});

test("buildExtractionAuditSummary returns null when no auditable extraction data exists", () => {
  assert.equal(buildExtractionAuditSummary(null, null), null);
});
