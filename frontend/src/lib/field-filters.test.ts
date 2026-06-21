import { test } from "node:test";
import assert from "node:assert/strict";

import {
  defaultOperatorForDtype,
  fieldFilterInputType,
  isFieldFilterComplete,
  isTopLevelScalarPath,
  makeFieldFilterPredicate,
  operatorInputCount,
  operatorLabelKey,
  operatorsForDtype,
  parseFieldFilters,
  segmentsToLabel,
  serializeFieldFilters,
  topLevelField,
  type FieldFilterPredicate,
} from "./field-filters.ts";

test("operatorsForDtype returns dtype-appropriate operators", () => {
  assert.deepEqual(operatorsForDtype("currency"), [
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
  ]);
  assert.deepEqual(operatorsForDtype("date"), ["eq", "lt", "gt", "between"]);
  assert.deepEqual(operatorsForDtype("bool"), ["is_true", "is_false"]);
  assert.deepEqual(operatorsForDtype("str"), ["contains", "not_contains", "eq", "ne"]);
  assert.deepEqual(operatorsForDtype("object_list"), ["contains", "not_contains", "eq", "ne"]);
});

test("defaultOperatorForDtype picks the first operator", () => {
  assert.equal(defaultOperatorForDtype("int"), "eq");
  assert.equal(defaultOperatorForDtype("str"), "contains");
  assert.equal(defaultOperatorForDtype("bool"), "is_true");
});

test("operatorInputCount reflects required value inputs", () => {
  assert.equal(operatorInputCount("is_true"), 0);
  assert.equal(operatorInputCount("between"), 2);
  assert.equal(operatorInputCount("gt"), 1);
});

test("fieldFilterInputType maps dtype to an input type", () => {
  assert.equal(fieldFilterInputType("float"), "number");
  assert.equal(fieldFilterInputType("date"), "date");
  assert.equal(fieldFilterInputType("str"), "text");
});

test("operatorLabelKey relabels date comparisons as before/after", () => {
  assert.equal(operatorLabelKey("lt", "date"), "field_op_before");
  assert.equal(operatorLabelKey("gt", "date"), "field_op_after");
  assert.equal(operatorLabelKey("lt", "int"), "field_op_lt");
});

test("segmentsToLabel and topLevelField read structured paths", () => {
  const segments = [{ k: "line_items" }, { elem: true as const }, { k: "amount" }];
  assert.equal(segmentsToLabel(segments), "line_items[].amount");
  assert.equal(topLevelField(segments), "line_items");
  assert.equal(isTopLevelScalarPath([{ k: "vendor" }]), true);
  assert.equal(isTopLevelScalarPath(segments), false);
});

test("isFieldFilterComplete enforces value requirements per operator", () => {
  assert.equal(isFieldFilterComplete(makeFieldFilterPredicate([], "str")), false);
  assert.equal(
    isFieldFilterComplete({
      segments: [{ k: "flag" }],
      op: "is_true",
      value: "",
      value2: "",
      dtype: "bool",
    }),
    true,
  );
  assert.equal(
    isFieldFilterComplete({
      segments: [{ k: "amount" }],
      op: "gt",
      value: "",
      value2: "",
      dtype: "float",
    }),
    false,
  );
  assert.equal(
    isFieldFilterComplete({
      segments: [{ k: "d" }],
      op: "between",
      value: "1",
      value2: "",
      dtype: "date",
    }),
    false,
  );
});

test("serializeFieldFilters drops incomplete predicates and trims", () => {
  const predicates: FieldFilterPredicate[] = [
    { segments: [{ k: "vendor" }], op: "contains", value: " ACME ", value2: "", dtype: "str" },
    { segments: [{ k: "amount" }], op: "gt", value: "", value2: "", dtype: "float" },
  ];
  const serialized = serializeFieldFilters(predicates);
  assert.deepEqual(JSON.parse(serialized!), [
    { segments: [{ k: "vendor" }], op: "contains", value: "ACME", value2: "", dtype: "str" },
  ]);
  assert.equal(serializeFieldFilters([]), undefined);
});

test("parseFieldFilters reads segments and shims legacy flat fields", () => {
  const raw = JSON.stringify([
    {
      segments: [{ k: "line_items" }, { elem: true }, { k: "amount" }],
      op: "gte",
      value: "500",
      dtype: "float",
    },
    { field: "vendor", op: "contains", value: "ACME", dtype: "str" },
    { op: "contains", value: "x" },
    { field: "vendor", op: "bogus", value: "y" },
  ]);
  const parsed = parseFieldFilters(raw);
  assert.equal(parsed.length, 2);
  assert.deepEqual(parsed[0].segments, [{ k: "line_items" }, { elem: true }, { k: "amount" }]);
  assert.equal(parsed[0].op, "gte");
  assert.deepEqual(parsed[1].segments, [{ k: "vendor" }]);
  assert.deepEqual(parseFieldFilters(null), []);
  assert.deepEqual(parseFieldFilters("not json"), []);
});
