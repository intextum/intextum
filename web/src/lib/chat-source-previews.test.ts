import assert from "node:assert/strict";
import test from "node:test";

import type { ConversationSource } from "../dataProvider.ts";
import {
  buildChatPanelSources,
  isReviewedEnrichmentSource,
  sourceContextLine,
  sourceDisplayPath,
  sourceDisplayTitle,
} from "./chat-source-previews.ts";

test("buildChatPanelSources sorts numbered sources and dedupes preview images", () => {
  const sources: ConversationSource[] = [
    {
      file_path: "docs/appendix.pdf",
      title: "Appendix",
      page_numbers: [5],
      doc_refs: [],
      citation_index: 2,
      images: [
        "/api/content/extracted-asset/file-2/fig-1.png",
        "/api/content/extracted-asset/file-2/fig-1.png",
      ],
    },
    {
      file_path: "docs/report.pdf",
      title: "Report",
      page_numbers: [3],
      doc_refs: [],
      citation_index: 1,
      images: [
        "/api/content/extracted-asset/file-1/fig-1.png",
        "/api/content/extracted-asset/file-1/fig-2.png",
      ],
    },
  ];

  const panelSources = buildChatPanelSources(sources);

  assert.deepEqual(
    panelSources.map((source) => source.file_path),
    ["docs/report.pdf", "docs/appendix.pdf"],
  );
  assert.deepEqual(panelSources[1].preview_images, [
    "/api/content/extracted-asset/file-2/fig-1.png",
  ]);
});

test("buildChatPanelSources merges unnumbered source previews by file path", () => {
  const sources: ConversationSource[] = [
    {
      file_path: "docs/report.pdf",
      title: "Report",
      page_numbers: [3],
      doc_refs: ["sec-1"],
      images: ["/api/content/extracted-asset/file-1/fig-1.png"],
    },
    {
      file_path: "docs/report.pdf",
      title: "Report duplicate",
      page_numbers: [4],
      doc_refs: ["sec-2"],
      images: ["/api/content/extracted-asset/file-1/fig-2.png"],
    },
  ];

  const panelSources = buildChatPanelSources(sources);

  assert.equal(panelSources.length, 1);
  assert.equal(panelSources[0].title, "Report");
  assert.deepEqual(panelSources[0].page_numbers, [3, 4]);
  assert.deepEqual(panelSources[0].doc_refs, ["sec-1", "sec-2"]);
  assert.deepEqual(panelSources[0].preview_images, [
    "/api/content/extracted-asset/file-1/fig-1.png",
    "/api/content/extracted-asset/file-1/fig-2.png",
  ]);
});

test("source display helpers preserve reviewed enrichment titles and badges", () => {
  const reviewedSource: ConversationSource = {
    file_path: "documents/invoice.pdf",
    title: "Reviewed enrichment evidence: Field invoice_number",
    display_name: "invoice.pdf",
    content_kind: "file",
    source_kind: "reviewed_enrichment",
    page_numbers: [1],
    doc_refs: ["#/texts/4"],
    citation_index: 1,
    images: [],
    quote: "RE-2026-42",
  };
  const plainSource: ConversationSource = {
    file_path: "documents/report.pdf",
    display_name: "report.pdf",
    content_kind: "file",
    page_numbers: [2],
    doc_refs: [],
    citation_index: 2,
    images: [],
  };

  assert.equal(
    sourceDisplayTitle(reviewedSource),
    "Reviewed enrichment evidence: Field invoice_number",
  );
  assert.equal(sourceDisplayPath(reviewedSource), "documents/invoice.pdf");
  assert.equal(isReviewedEnrichmentSource(reviewedSource), true);
  assert.equal(sourceDisplayTitle(plainSource), "report.pdf");
  assert.equal(sourceDisplayPath(plainSource), null);
  assert.equal(isReviewedEnrichmentSource(plainSource), false);
});

test("source context helper formats email and attachment metadata", () => {
  const translate = (key: string, options?: unknown) => {
    const resolvedOptions = (options ?? {}) as Record<string, unknown>;
    if (key === "custom.content.search.email_from") {
      return `From ${String(resolvedOptions.address)}`;
    }
    if (key === "custom.content.search.email_sent_at") {
      return `Sent ${String(resolvedOptions.date)}`;
    }
    if (key === "custom.content.search.attachment_parent") {
      return `From email ${String(resolvedOptions.name)}`;
    }
    return key;
  };

  const emailSource: ConversationSource = {
    file_path: "mailbox/Inbox/message.eml",
    display_name: "Quarterly update",
    content_kind: "email_message",
    email_from_address: "alice@example.com",
    email_sent_at: "2026-04-27T10:00:00Z",
    page_numbers: [],
    doc_refs: [],
    images: [],
  };
  const attachmentSource: ConversationSource = {
    file_path: "mailbox/Inbox/attachments/report.pdf",
    display_name: "report.pdf",
    content_kind: "attachment",
    parent_display_name: "Quarterly update",
    page_numbers: [],
    doc_refs: [],
    images: [],
  };

  const emailLine = sourceContextLine(emailSource, translate);
  assert.ok(emailLine?.includes("From alice@example.com"));
  assert.ok(emailLine?.includes("Sent "));
  assert.equal(sourceContextLine(attachmentSource, translate), "From email Quarterly update");
});
