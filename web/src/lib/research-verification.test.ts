import assert from "node:assert/strict";
import test from "node:test";

import {
  groupResearchVerificationIssuesBySection,
  makeResearchSectionAnchorId,
  relatedResearchSourcesForIssue,
  summarizeResearchVerification,
} from "./research-verification.ts";

test("summarizeResearchVerification returns a healthy summary without issues", () => {
  const summary = summarizeResearchVerification([]);

  assert.equal(summary.level, "healthy");
  assert.equal(summary.issueCount, 0);
  assert.equal(summary.warningCount, 0);
  assert.equal(summary.criticalCount, 0);
  assert.deepEqual(summary.affectedSections, []);
  assert.deepEqual(summary.issues, []);
});

test("summarizeResearchVerification classifies issues and tracks affected sections", () => {
  const summary = summarizeResearchVerification([
    "Summary: section evidence was retrieved but the draft cites none of it",
    "Recommendations: invalid citations 9",
    "Recommendations: cites sources outside the section evidence 1",
    "The report does not cite any retrieved evidence.",
  ]);

  assert.equal(summary.level, "critical");
  assert.equal(summary.issueCount, 4);
  assert.equal(summary.warningCount, 1);
  assert.equal(summary.criticalCount, 3);
  assert.deepEqual(summary.affectedSections, ["Summary", "Recommendations"]);
  assert.deepEqual(
    summary.issues.map((issue) => ({
      section: issue.section,
      sectionAnchorId: issue.sectionAnchorId,
      citationIndices: issue.citationIndices,
      severity: issue.severity,
      message: issue.message,
    })),
    [
      {
        section: "Summary",
        sectionAnchorId: "research-section-summary",
        citationIndices: [],
        severity: "warning",
        message: "section evidence was retrieved but the draft cites none of it",
      },
      {
        section: "Recommendations",
        sectionAnchorId: "research-section-recommendations",
        citationIndices: [9],
        severity: "critical",
        message: "invalid citations 9",
      },
      {
        section: "Recommendations",
        sectionAnchorId: "research-section-recommendations",
        citationIndices: [1],
        severity: "critical",
        message: "cites sources outside the section evidence 1",
      },
      {
        section: null,
        sectionAnchorId: null,
        citationIndices: [],
        severity: "critical",
        message: "The report does not cite any retrieved evidence.",
      },
    ],
  );
});

test("groupResearchVerificationIssuesBySection keeps only section-scoped issues", () => {
  const summary = summarizeResearchVerification([
    "Summary: section evidence was retrieved but the draft cites none of it",
    "The report does not cite any retrieved evidence.",
    "Recommendations: invalid citations 9",
  ]);

  assert.deepEqual(groupResearchVerificationIssuesBySection(summary.issues), {
    Summary: [summary.issues[0]],
    Recommendations: [summary.issues[2]],
  });
});

test("makeResearchSectionAnchorId creates stable section anchors", () => {
  assert.equal(
    makeResearchSectionAnchorId("Executive Summary / 2026"),
    "research-section-executive-summary-2026",
  );
});

test("relatedResearchSourcesForIssue returns sources in cited order", () => {
  const summary = summarizeResearchVerification([
    "Recommendations: invalid citations 9 and cites sources outside the section evidence 2 1",
  ]);

  assert.deepEqual(
    relatedResearchSourcesForIssue(summary.issues[0], [
      { citation_index: 1, file_path: "docs/summary.pdf", title: "Summary", doc_refs: [] },
      { citation_index: 2, file_path: "docs/roadmap.pdf", title: "Roadmap", doc_refs: ["sec-2"] },
      { citation_index: 9, file_path: "docs/broken.pdf", title: "Broken", doc_refs: [] },
    ]),
    [
      { citation_index: 9, file_path: "docs/broken.pdf", title: "Broken", doc_refs: [] },
      { citation_index: 2, file_path: "docs/roadmap.pdf", title: "Roadmap", doc_refs: ["sec-2"] },
      { citation_index: 1, file_path: "docs/summary.pdf", title: "Summary", doc_refs: [] },
    ],
  );
});
