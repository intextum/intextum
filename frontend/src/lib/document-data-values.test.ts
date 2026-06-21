import assert from "node:assert/strict";
import test from "node:test";

import {
  coerceObjectListItemDraft,
  formatObjectListChildValue,
  mergeExtractionFieldsMeta,
  parseObjectListChildDraftValue,
} from "./document-data-values.ts";

test("object-list child list values render and save as arrays", () => {
  assert.equal(formatObjectListChildValue(["A", "B"], "list"), "A\nB");
  assert.deepEqual(parseObjectListChildDraftValue("A\nB", "list"), ["A", "B"]);
  assert.deepEqual(parseObjectListChildDraftValue('["A","B"]', "list"), ["A", "B"]);

  assert.deepEqual(
    coerceObjectListItemDraft(
      {
        label: "Condition group",
        conditions: "Keep trees\nAvoid runoff",
        amount: "1.234,56",
      },
      [
        { name: "label", dtype: "str" },
        { name: "conditions", dtype: "list" },
        { name: "amount", dtype: "float" },
      ],
    ),
    {
      label: "Condition group",
      conditions: ["Keep trees", "Avoid runoff"],
      amount: 1234.56,
    },
  );
});

test("field metadata merge preserves object-list child schema fields", () => {
  const merged = mergeExtractionFieldsMeta(
    {
      Katasterangaben: {
        dtype: "object_list",
        required: true,
        fields: [
          { name: "Gemarkung", dtype: "str" },
          { name: "Flur", dtype: "int" },
          { name: "Flurstück", dtype: "list" },
        ],
      },
    },
    {
      Katasterangaben: {
        dtype: "object_list",
        value: [
          {
            Gemarkung: "Mitlosheim",
            Flur: 8,
            Flurstück: ["2", "3", "4"],
          },
        ],
        confidence: 0.82,
        evidence: [{ doc_refs: ["#/texts/1"] }],
      },
    },
  );

  assert.deepEqual(merged?.Katasterangaben?.fields, [
    { name: "Gemarkung", dtype: "str" },
    { name: "Flur", dtype: "int" },
    { name: "Flurstück", dtype: "list" },
  ]);
  assert.equal(merged?.Katasterangaben?.confidence, 0.82);
  assert.deepEqual(merged?.Katasterangaben?.evidence, [{ doc_refs: ["#/texts/1"] }]);
});
