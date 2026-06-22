import assert from "node:assert/strict";
import test from "node:test";

import type { ConversationMessage, ResearchReportMessageMetadata } from "../dataProvider.ts";
import {
  buildAssistantResponseExportDocument,
  buildConversationExportDocument,
  buildResearchResponseExportDocument,
  extractMarkdownEmbeddedImages,
  sanitizeExportFilenameBase,
} from "./chat-export.ts";

const labels = {
  assistantDefaultTitle: "Assistant response",
  assistantLabel: "Assistant",
  conversationDefaultTitle: "Conversation",
  contextFilesHeading: "Context files",
  researchDefaultTitle: "Research report",
  sourcesHeading: "Sources",
  userLabel: "User",
  imagesHeading: "Images",
  verificationHeading: "Verification notes",
};
const exportUrlOptions = {
  absoluteBaseUrl: "https://intextum.example.test",
};

test("buildAssistantResponseExportDocument adds a title and sources section", () => {
  const message: ConversationMessage = {
    id: "msg-1",
    role: "assistant",
    content: "Retention improved after the program [1].",
    sources: [
      {
        file_path: "docs/report.pdf",
        title: "Retention Report",
        page_numbers: [4],
        doc_refs: ["ref-1"],
        citation_index: 1,
        images: [],
        quote: "Retention improved after the program.",
      },
    ],
  };

  const document = buildAssistantResponseExportDocument(message, labels, exportUrlOptions);

  assert.equal(document.title, "Retention improved after the program [1].");
  assert.equal(document.filenameBase, "Retention improved after the program [1]");
  assert.match(document.markdown, /^# Retention improved after the program \[1\]\./);
  assert.match(document.markdown, /## Sources/);
  assert.match(
    document.markdown,
    /- \[1\] Retention Report: \[docs\/report\.pdf\]\(https:\/\/intextum\.example\.test\/api\/content\/preview\/docs%2Freport\.pdf\) \(pages 4\)/,
  );
  assert.match(document.markdown, /> Retention improved after the program\./);
});

test("buildAssistantResponseExportDocument does not duplicate an existing markdown title", () => {
  const message: ConversationMessage = {
    id: "msg-2",
    role: "assistant",
    content: "# Quarterly review\n\nMain findings [1].",
    sources: [],
  };

  const document = buildAssistantResponseExportDocument(message, labels, exportUrlOptions);

  assert.equal(document.title, "Quarterly review");
  assert.equal(document.markdown.match(/^# Quarterly review$/gm)?.length, 1);
});

test("buildAssistantResponseExportDocument rewrites inline file links to absolute preview URLs", () => {
  const message: ConversationMessage = {
    id: "msg-inline-link",
    role: "assistant",
    content:
      "See [Retention Report](/api/content/download/docs%2Freport.pdf) for the full document.",
    sources: [],
  };

  const document = buildAssistantResponseExportDocument(message, labels, exportUrlOptions);

  assert.match(
    document.markdown,
    /\[Retention Report\]\(https:\/\/intextum\.example\.test\/api\/content\/preview\/docs%2Freport\.pdf\)/,
  );
});

test("buildResearchResponseExportDocument keeps report markdown and appends extras once", () => {
  const report = {
    kind: "research_report",
    report_id: "report-1",
    conversation_id: "thread-1",
    id: "report-1",
    title: "Program Review",
    prompt: "Assess the sustainability program.",
    status: "COMPLETED",
    context_file_paths: [],
    outline: ["Summary"],
    sections: [{ heading: "Summary", body: "Emissions fell by 12 percent [1]." }],
    sources: [
      {
        file_path: "docs/program.pdf",
        title: "Program Review",
        page_numbers: [3],
        doc_refs: ["ref-1"],
        citation_index: 1,
        images: [],
        quote: "Emissions fell by 12 percent.",
      },
    ],
    images: [
      { url: "/api/content/extracted-asset/file-1/chart.png", title: "Chart", citation_index: 1 },
    ],
    verification: {
      issues: ["Summary: section evidence was retrieved but the draft cites none of it"],
    },
    content_markdown:
      "# Program Review\n\n## Summary\n\nEmissions fell by 12 percent [1].\n\n## Sources\n\n- [1] Program Review: `docs/program.pdf` (pages 3)",
    created_at: "2026-04-24T10:00:00Z",
    updated_at: "2026-04-24T10:10:00Z",
  } satisfies ResearchReportMessageMetadata;

  const document = buildResearchResponseExportDocument(report, labels, exportUrlOptions);

  assert.equal(document.title, "Program Review");
  assert.equal(document.filenameBase, "Program Review");
  assert.equal(document.markdown.match(/^## Sources$/gm)?.length, 1);
  assert.match(
    document.markdown,
    /- \[1\] Program Review: \[docs\/program\.pdf\]\(https:\/\/intextum\.example\.test\/api\/content\/preview\/docs%2Fprogram\.pdf\) \(pages 3\)/,
  );
  assert.match(document.markdown, /## Images/);
  assert.match(
    document.markdown,
    /- \[1\] \[Chart\]\(https:\/\/intextum\.example\.test\/api\/content\/extracted-asset\/file-1\/chart\.png\)/,
  );
  assert.match(
    document.markdown,
    /!\[Chart\]\(https:\/\/intextum\.example\.test\/api\/content\/extracted-asset\/file-1\/chart\.png\)/,
  );
  assert.match(document.markdown, /## Verification notes/);
  assert.match(
    document.markdown,
    /Summary: section evidence was retrieved but the draft cites none of it/,
  );
});

test("buildResearchResponseExportDocument rewrites inline markdown URLs before export", () => {
  const report = {
    kind: "research_report",
    report_id: "report-inline-urls",
    conversation_id: "thread-inline-urls",
    id: "report-inline-urls",
    title: "Linked Review",
    prompt: "Check inline links.",
    status: "COMPLETED",
    context_file_paths: [],
    outline: ["Summary"],
    sections: [{ heading: "Summary", body: "See the linked source." }],
    sources: [],
    images: [],
    verification: { issues: [] },
    content_markdown:
      "# Linked Review\n\n## Summary\n\nSee [Report](/api/content/download/docs%2Flinked.pdf).\n\n![Chart](/api/content/extracted-asset/file-1/chart.png)",
    created_at: "2026-04-24T10:00:00Z",
    updated_at: "2026-04-24T10:10:00Z",
  } satisfies ResearchReportMessageMetadata;

  const document = buildResearchResponseExportDocument(report, labels, exportUrlOptions);

  assert.match(
    document.markdown,
    /\[Report\]\(https:\/\/intextum\.example\.test\/api\/content\/preview\/docs%2Flinked\.pdf\)/,
  );
  assert.match(
    document.markdown,
    /!\[Chart\]\(https:\/\/intextum\.example\.test\/api\/content\/extracted-asset\/file-1\/chart\.png\)/,
  );
});

test("extractMarkdownEmbeddedImages returns unique image references in order", () => {
  const references = extractMarkdownEmbeddedImages(
    [
      "## Images",
      "",
      "- [1] [Chart](https://intextum.example.test/chart.png)",
      "  ![Chart](https://intextum.example.test/chart.png)",
      "  ![Chart](https://intextum.example.test/chart.png)",
      "  ![Appendix](https://intextum.example.test/appendix.png)",
    ].join("\n"),
  );

  assert.deepEqual(references, [
    { altText: "Chart", url: "https://intextum.example.test/chart.png" },
    { altText: "Appendix", url: "https://intextum.example.test/appendix.png" },
  ]);
});

test("buildConversationExportDocument assembles user, assistant, and research transcript sections", () => {
  const report = {
    kind: "research_report",
    report_id: "report-1",
    conversation_id: "thread-1",
    id: "report-1",
    title: "Program Review",
    prompt: "Assess the sustainability program.",
    status: "COMPLETED",
    context_file_paths: [],
    outline: ["Summary"],
    sections: [{ heading: "Summary", body: "Emissions fell by 12 percent [1]." }],
    sources: [
      {
        file_path: "docs/program.pdf",
        title: "Program Review",
        page_numbers: [3],
        doc_refs: ["ref-1"],
        citation_index: 1,
        images: [],
        quote: "Emissions fell by 12 percent.",
      },
    ],
    images: [],
    verification: {
      issues: [],
    },
    content_markdown:
      "# Program Review\n\n## Summary\n\nEmissions fell by 12 percent [1].\n\n## Sources\n\n- [1] Program Review: `docs/program.pdf` (pages 3)",
    created_at: "2026-04-24T10:00:00Z",
    updated_at: "2026-04-24T10:10:00Z",
  } satisfies ResearchReportMessageMetadata;

  const messages: ConversationMessage[] = [
    {
      id: "msg-1",
      role: "user",
      content: "Please review the sustainability program.",
      sources: [],
      metadata: {
        context_file_paths: ["docs/program.pdf", "docs/appendix.pdf"],
      },
    },
    {
      id: "msg-2",
      role: "assistant",
      content: "I reviewed the report [1].",
      sources: [
        {
          file_path: "docs/program.pdf",
          title: "Program Review",
          page_numbers: [3],
          doc_refs: ["ref-1"],
          citation_index: 1,
          images: [],
          quote: "Emissions fell by 12 percent.",
        },
      ],
    },
    {
      id: "msg-3",
      role: "assistant",
      content: "Research completed.",
      sources: [],
      metadata: report,
    },
  ];

  const document = buildConversationExportDocument(
    {
      title: "Sustainability review",
      messages,
    },
    labels,
    exportUrlOptions,
  );

  assert.equal(document.title, "Sustainability review");
  assert.equal(document.filenameBase, "Sustainability review");
  assert.match(document.markdown, /^# Sustainability review$/m);
  assert.match(document.markdown, /^## User 1$/m);
  assert.match(document.markdown, /Please review the sustainability program\./);
  assert.match(document.markdown, /^## Context files$/m);
  assert.match(
    document.markdown,
    /- \[docs\/program\.pdf\]\(https:\/\/intextum\.example\.test\/api\/content\/preview\/docs%2Fprogram\.pdf\)/,
  );
  assert.match(document.markdown, /^## Assistant 2$/m);
  assert.match(document.markdown, /I reviewed the report \[1\]\./);
  assert.match(
    document.markdown,
    /- \[1\] Program Review: \[docs\/program\.pdf\]\(https:\/\/intextum\.example\.test\/api\/content\/preview\/docs%2Fprogram\.pdf\) \(pages 3\)/,
  );
  assert.match(document.markdown, /^## Assistant 3$/m);
  assert.match(document.markdown, /^### Program Review$/m);
  assert.match(document.markdown, /^#### Summary$/m);
});

test("buildConversationExportDocument derives a fallback title from the transcript", () => {
  const document = buildConversationExportDocument(
    {
      messages: [
        {
          id: "msg-1",
          role: "user",
          content: "Please summarize the retention report and highlight risks.",
          sources: [],
        },
      ],
    },
    labels,
    exportUrlOptions,
  );

  assert.equal(document.title, "Please summarize the retention report and highlight risks.");
});

test("sanitizeExportFilenameBase keeps readable unicode while removing invalid separators", () => {
  assert.equal(
    sanitizeExportFilenameBase("Überblick / Q1: Bericht", "fallback"),
    "Überblick - Q1- Bericht",
  );
  assert.equal(sanitizeExportFilenameBase("   ", "fallback"), "fallback");
});
