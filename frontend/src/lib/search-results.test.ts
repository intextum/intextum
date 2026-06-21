import assert from "node:assert/strict";
import test from "node:test";

import type { SearchResult } from "@/dataProvider";

import {
  buildHighlightedTextSegments,
  combineSearchResults,
  extractSearchTerms,
  groupSearchResults,
} from "./search-results.ts";

function createResult(overrides: Partial<SearchResult>): SearchResult {
  return {
    score: 0.5,
    file_path: "documents/report.pdf",
    content_item_id: null,
    display_name: "report.pdf",
    content_kind: "file",
    text: "Default text",
    chunk_index: 0,
    page_numbers: [],
    headings: [],
    images: [],
    doc_refs: [],
    payload: {},
    ...overrides,
  };
}

test("groupSearchResults keeps one group per content item and preserves first-seen order", () => {
  const groups = groupSearchResults([
    createResult({
      content_item_id: "content-a",
      file_path: "a.pdf",
      chunk_index: 0,
      score: 0.4,
    }),
    createResult({
      content_item_id: "content-b",
      file_path: "b.pdf",
      chunk_index: 0,
      score: 0.8,
    }),
    createResult({
      content_item_id: "content-a",
      file_path: "a.pdf",
      chunk_index: 1,
      score: 0.9,
    }),
  ]);

  assert.deepEqual(
    groups.map((group) => group.id),
    ["content-a", "content-b"],
  );
  assert.equal(groups[0].results.length, 2);
  assert.equal(groups[0].bestResult.chunk_index, 1);
});

test("combineSearchResults merges refs and page metadata for opening grouped hits", () => {
  const combined = combineSearchResults([
    createResult({
      score: 0.6,
      page_numbers: [2, 1],
      headings: ["Intro"],
      images: ["image-a"],
      doc_refs: ["chunk-1"],
    }),
    createResult({
      score: 0.9,
      page_numbers: [2, 3],
      headings: ["Intro", "Details"],
      images: ["image-a", "image-b"],
      doc_refs: ["chunk-2"],
    }),
  ]);

  assert.equal(combined.score, 0.9);
  assert.deepEqual(combined.page_numbers, [1, 2, 3]);
  assert.deepEqual(combined.headings, ["Intro", "Details"]);
  assert.deepEqual(combined.images, ["image-a", "image-b"]);
  assert.deepEqual(combined.doc_refs, ["chunk-1", "chunk-2"]);
});

test("extractSearchTerms normalizes quotes and duplicate terms", () => {
  assert.deepEqual(extractSearchTerms('"forest" forest soil'), ["forest", "soil"]);
});

test("buildHighlightedTextSegments marks query matches case-insensitively", () => {
  assert.deepEqual(buildHighlightedTextSegments("Forest soil profile", "soil forest"), [
    { text: "Forest", highlighted: true },
    { text: " ", highlighted: false },
    { text: "soil", highlighted: true },
    { text: " profile", highlighted: false },
  ]);
});
