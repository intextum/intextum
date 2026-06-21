/**
 * Extracted-field predicate filters: shared types, per-dtype operator metadata,
 * JSON-path segments, and URL/API (de)serialization for the content list
 * "field conditions" filter.
 */

export type FieldFilterDtype =
  | "str"
  | "int"
  | "float"
  | "bool"
  | "list"
  | "date"
  | "currency"
  | "object_list";

export type FieldFilterOperator =
  | "contains"
  | "not_contains"
  | "eq"
  | "ne"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "between"
  | "is_true"
  | "is_false";

/** One step of an extracted-data path: an object key or an array wildcard. */
export type FieldFilterSegment = { k: string } | { elem: true };

export interface FieldFilterPredicate {
  segments: FieldFilterSegment[];
  op: FieldFilterOperator;
  value: string;
  value2: string;
  dtype: FieldFilterDtype;
}

/** A selectable, typed leaf path offered by the field picker. */
export interface FieldFilterLeaf {
  label: string;
  segments: FieldFilterSegment[];
  dtype: FieldFilterDtype;
  count: number | null;
}

const NUMERIC_DTYPES: ReadonlySet<FieldFilterDtype> = new Set(["int", "float", "currency"]);
const KNOWN_OPERATORS: ReadonlySet<string> = new Set<FieldFilterOperator>([
  "contains",
  "not_contains",
  "eq",
  "ne",
  "gt",
  "gte",
  "lt",
  "lte",
  "between",
  "is_true",
  "is_false",
]);
const KNOWN_DTYPES: ReadonlySet<string> = new Set<FieldFilterDtype>([
  "str",
  "int",
  "float",
  "bool",
  "list",
  "date",
  "currency",
  "object_list",
]);

const NUMERIC_OPERATORS: FieldFilterOperator[] = ["eq", "ne", "gt", "gte", "lt", "lte", "between"];
const DATE_OPERATORS: FieldFilterOperator[] = ["eq", "lt", "gt", "between"];
const TEXT_OPERATORS: FieldFilterOperator[] = ["contains", "not_contains", "eq", "ne"];
const BOOL_OPERATORS: FieldFilterOperator[] = ["is_true", "is_false"];

export function operatorsForDtype(dtype: FieldFilterDtype): FieldFilterOperator[] {
  if (NUMERIC_DTYPES.has(dtype)) return NUMERIC_OPERATORS;
  if (dtype === "date") return DATE_OPERATORS;
  if (dtype === "bool") return BOOL_OPERATORS;
  return TEXT_OPERATORS;
}

export function defaultOperatorForDtype(dtype: FieldFilterDtype): FieldFilterOperator {
  return operatorsForDtype(dtype)[0];
}

/** Number of value inputs an operator needs (0 = boolean presence, 2 = range). */
export function operatorInputCount(op: FieldFilterOperator): 0 | 1 | 2 {
  if (op === "is_true" || op === "is_false") return 0;
  if (op === "between") return 2;
  return 1;
}

export function fieldFilterInputType(dtype: FieldFilterDtype): "number" | "date" | "text" {
  if (NUMERIC_DTYPES.has(dtype)) return "number";
  if (dtype === "date") return "date";
  return "text";
}

/**
 * The i18n key (under the content_list namespace) for an operator label. Date
 * comparisons read more naturally as before/after than </>.
 */
export function operatorLabelKey(op: FieldFilterOperator, dtype: FieldFilterDtype): string {
  if (dtype === "date") {
    if (op === "lt") return "field_op_before";
    if (op === "gt") return "field_op_after";
  }
  return `field_op_${op}`;
}

export function normalizeDtype(dtype: string | undefined): FieldFilterDtype {
  const normalized = (dtype ?? "").toLowerCase();
  return KNOWN_DTYPES.has(normalized) ? (normalized as FieldFilterDtype) : "str";
}

/** Human-readable path, e.g. ``line_items[].amount``. */
export function segmentsToLabel(segments: FieldFilterSegment[]): string {
  let label = "";
  for (const segment of segments) {
    if ("elem" in segment) {
      label += "[]";
    } else {
      label += label ? `.${segment.k}` : segment.k;
    }
  }
  return label;
}

/** The top-level field name (first key segment), used as the facet focus. */
export function topLevelField(segments: FieldFilterSegment[]): string {
  for (const segment of segments) {
    if ("k" in segment) return segment.k;
  }
  return "";
}

/** True when the path is a single top-level scalar key (value suggestions apply). */
export function isTopLevelScalarPath(segments: FieldFilterSegment[]): boolean {
  return segments.length === 1 && "k" in segments[0];
}

export function makeFieldFilterPredicate(
  segments: FieldFilterSegment[],
  dtype: FieldFilterDtype,
): FieldFilterPredicate {
  return { segments, op: defaultOperatorForDtype(dtype), value: "", value2: "", dtype };
}

export function isFieldFilterComplete(predicate: FieldFilterPredicate): boolean {
  if (predicate.segments.length === 0) return false;
  const inputs = operatorInputCount(predicate.op);
  if (inputs === 0) return true;
  if (inputs === 2) return predicate.value.trim() !== "" && predicate.value2.trim() !== "";
  return predicate.value.trim() !== "";
}

function normalizeSegments(raw: unknown): FieldFilterSegment[] {
  if (!Array.isArray(raw)) return [];
  const segments: FieldFilterSegment[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    if (record.elem === true) {
      segments.push({ elem: true });
    } else if (typeof record.k === "string" && record.k) {
      segments.push({ k: record.k });
    }
  }
  return segments;
}

/** JSON string of complete predicates for the API/URL, or undefined when none. */
export function serializeFieldFilters(predicates: FieldFilterPredicate[]): string | undefined {
  const complete = predicates.filter(isFieldFilterComplete).map((predicate) => ({
    segments: predicate.segments,
    op: predicate.op,
    value: predicate.value.trim(),
    value2: predicate.value2.trim(),
    dtype: predicate.dtype,
  }));
  return complete.length > 0 ? JSON.stringify(complete) : undefined;
}

export function parseFieldFilters(raw: string | null | undefined): FieldFilterPredicate[] {
  if (!raw) return [];
  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(decoded)) return [];

  const predicates: FieldFilterPredicate[] = [];
  for (const entry of decoded) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const op = typeof record.op === "string" ? record.op : "";
    if (!KNOWN_OPERATORS.has(op)) continue;
    let segments = normalizeSegments(record.segments);
    if (segments.length === 0 && typeof record.field === "string" && record.field) {
      // Legacy flat predicates carried a single top-level field name.
      segments = [{ k: record.field }];
    }
    if (segments.length === 0) continue;
    predicates.push({
      segments,
      op: op as FieldFilterOperator,
      value: typeof record.value === "string" ? record.value : "",
      value2: typeof record.value2 === "string" ? record.value2 : "",
      dtype: normalizeDtype(typeof record.dtype === "string" ? record.dtype : undefined),
    });
  }
  return predicates;
}
