import assert from "node:assert/strict";
import test from "node:test";

import {
  chunkMatchesHighlightRefs,
  findFirstHighlightedChunkValue,
} from "./content-chunk-highlights.ts";

test("chunkMatchesHighlightRefs ignores empty refs and matches normalized overlaps", () => {
  assert.equal(
    chunkMatchesHighlightRefs([" section-2 ", "table-1"], ["", "table-1", "table-1"]),
    true,
  );
  assert.equal(chunkMatchesHighlightRefs(["section-2"], undefined), false);
  assert.equal(chunkMatchesHighlightRefs(undefined, ["section-2"]), false);
});

test("findFirstHighlightedChunkValue returns the first matching chunk", () => {
  assert.equal(
    findFirstHighlightedChunkValue(
      {
        file_path: "docs/report.pdf",
        chunks: [
          {
            chunk_index: 0,
            word_count: 10,
            char_count: 42,
            page_numbers: [],
            doc_refs: ["overview"],
            headings: [],
            text: "",
            images: [],
          },
          {
            chunk_index: 1,
            word_count: 12,
            char_count: 57,
            page_numbers: [],
            doc_refs: ["deep-dive", "table-3"],
            headings: [],
            text: "",
            images: [],
          },
        ],
        total_chunks: 2,
        is_indexed: true,
      },
      ["table-3", "missing"],
    ),
    "chunk-1",
  );
});

test("findFirstHighlightedChunkValue returns undefined without a match", () => {
  assert.equal(
    findFirstHighlightedChunkValue(
      {
        file_path: "docs/report.pdf",
        chunks: [
          {
            chunk_index: 0,
            word_count: 10,
            char_count: 42,
            page_numbers: [],
            doc_refs: ["overview"],
            headings: [],
            text: "",
            images: [],
          },
        ],
        total_chunks: 1,
        is_indexed: true,
      },
      ["table-3"],
    ),
    undefined,
  );
});
