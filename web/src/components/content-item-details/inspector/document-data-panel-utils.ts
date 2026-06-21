import { type ContentEnrichmentCatalogSchema } from "@/dataProvider";
import { isObjectRecord } from "@/lib/content-enrichment";

export type FieldBucket = "attention" | "reviewed";

export interface CandidateOption {
  label: string;
  value: unknown;
  confidence: number | null;
  evidenceDocRefs: string[];
}

interface ListSuggestion {
  label: string;
  value: string;
  confidence: number | null;
}

interface ObjectListSuggestion {
  label: string;
  value: Record<string, unknown>;
  confidence: number | null;
}

export const fieldLabel = (key: string): string => key.replaceAll("_", " ");

export const formatValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return value.map(formatValue).filter(Boolean).join(", ");
  return JSON.stringify(value);
};

export const normalizeListValue = (value: unknown): string[] => {
  const values = Array.isArray(value)
    ? value
    : value === null || value === undefined
      ? []
      : [value];
  const normalized: string[] = [];
  for (const item of values) {
    const formatted = formatValue(item).trim();
    if (
      formatted &&
      !normalized.some((existing) => existing.toLowerCase() === formatted.toLowerCase())
    ) {
      normalized.push(formatted);
    }
  }
  return normalized;
};

export const mergeListValues = (currentValue: unknown, nextValue: unknown): string[] => {
  const current = normalizeListValue(currentValue);
  return [
    ...current,
    ...normalizeListValue(nextValue).filter(
      (item) => !current.some((existing) => existing.toLowerCase() === item.toLowerCase()),
    ),
  ];
};

export const listContainsValue = (currentValue: unknown, nextValue: unknown): boolean => {
  const current = normalizeListValue(currentValue).map((item) => item.toLowerCase());
  return normalizeListValue(nextValue).some((item) => current.includes(item.toLowerCase()));
};

export const normalizeObjectListValue = (value: unknown): Array<Record<string, unknown>> =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => isObjectRecord(item))
    : [];

export const objectListContainsValue = (currentValue: unknown, nextValue: unknown): boolean => {
  const current = normalizeObjectListValue(currentValue).map((item) => JSON.stringify(item));
  const nextItems = normalizeObjectListValue(Array.isArray(nextValue) ? nextValue : [nextValue]);
  return nextItems.some((item) => current.includes(JSON.stringify(item)));
};

export const mergeObjectListValues = (
  currentValue: unknown,
  nextValue: unknown,
): Array<Record<string, unknown>> => {
  const current = normalizeObjectListValue(currentValue);
  const nextItems = normalizeObjectListValue(Array.isArray(nextValue) ? nextValue : [nextValue]);
  const currentKeys = new Set(current.map((item) => JSON.stringify(item)));
  return [...current, ...nextItems.filter((item) => !currentKeys.has(JSON.stringify(item)))];
};

export const numericConfidence = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

export const formatConfidence = (value: number): string => {
  const pct = value >= 0 && value <= 1 ? value * 100 : value;
  return `${pct.toFixed(pct >= 10 ? 0 : 1).replace(/\.0+$/, "")}%`;
};

export const allDocRefs = (evidence: unknown): string[] => {
  if (!Array.isArray(evidence)) return [];
  const refs = new Set<string>();
  for (const entry of evidence) {
    if (!isObjectRecord(entry)) continue;
    const docRefs = entry.doc_refs;
    if (!Array.isArray(docRefs)) continue;
    for (const ref of docRefs) {
      if (typeof ref === "string" && ref.length > 0) refs.add(ref);
    }
  }
  return [...refs];
};

export const valuesEqual = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (a == null || b == null) return a == null && b == null;
  return formatValue(a) === formatValue(b);
};

export const hasDisplayValue = (value: unknown): boolean => {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return normalizeListValue(value).length > 0;
  return true;
};

export const objectChildFields = (meta: Record<string, unknown> | undefined) => {
  const fields = meta?.fields;
  if (!Array.isArray(fields)) return [];
  return fields.filter((field): field is Record<string, unknown> => isObjectRecord(field));
};

export const childFieldName = (field: Record<string, unknown>): string | null =>
  typeof field.name === "string" && field.name.trim() ? field.name.trim() : null;

export const emptyObjectListItem = (
  fields: Array<Record<string, unknown>>,
): Record<string, unknown> =>
  Object.fromEntries(
    fields
      .map((field) => childFieldName(field))
      .filter((name): name is string => Boolean(name))
      .map((name) => [name, ""]),
  );

export const stringifyDraft = (label: string | null, data: Record<string, unknown> | null) =>
  JSON.stringify({ label, data });

export const normalizeLookup = (value: string | null | undefined): string =>
  typeof value === "string" ? value.trim().toLowerCase() : "";

export const documentClassFromPayload = (value: unknown): string | null => {
  if (!isObjectRecord(value)) return null;
  const documentClass = value.document_class;
  return typeof documentClass === "string" && documentClass.trim() ? documentClass.trim() : null;
};

const candidateLabel = (candidate: unknown): string | null => {
  if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  if (!isObjectRecord(candidate)) return null;
  for (const key of ["label", "name", "class_name", "class", "value", "document_class"]) {
    const value = candidate[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
};

const candidateConfidence = (candidate: unknown): number | null => {
  if (!isObjectRecord(candidate)) return null;
  for (const key of ["confidence", "score", "probability", "prob"]) {
    const confidence = numericConfidence(candidate[key]);
    if (confidence !== null) return confidence;
  }
  return null;
};

const candidateValue = (candidate: unknown): unknown => {
  if (isObjectRecord(candidate) && "value" in candidate) return candidate.value;
  return candidateLabel(candidate) ?? candidate;
};

const candidateEvidenceDocRefs = (candidate: unknown): string[] => {
  if (!isObjectRecord(candidate)) return [];
  return allDocRefs(candidate.evidence);
};

const addCandidate = (
  target: Map<string, CandidateOption>,
  value: unknown,
  confidence: number | null,
  evidenceDocRefs: string[] = [],
) => {
  const rawValue = candidateValue(value);
  const label = candidateLabel(value) ?? formatValue(rawValue);
  if (!label) return;
  const key = label.toLowerCase();
  const existing = target.get(key);
  if (existing && (existing.confidence ?? -1) >= (confidence ?? -1)) return;
  target.set(key, { label, value: rawValue, confidence, evidenceDocRefs });
};

export const rankedClassificationCandidates = (classification: unknown): CandidateOption[] => {
  if (!isObjectRecord(classification)) return [];
  const rawOutput = isObjectRecord(classification.raw_output)
    ? classification.raw_output
    : classification;
  const candidates = new Map<string, CandidateOption>();

  const directClass = rawOutput.document_class;
  if (Array.isArray(directClass)) {
    for (const candidate of directClass)
      addCandidate(candidates, candidate, candidateConfidence(candidate));
  } else if (directClass !== undefined) {
    addCandidate(candidates, directClass, candidateConfidence(directClass));
  }

  for (const key of ["candidates", "candidate_labels", "predictions", "labels"]) {
    const rawCandidates = rawOutput[key];
    if (!Array.isArray(rawCandidates)) continue;
    for (const candidate of rawCandidates)
      addCandidate(candidates, candidate, candidateConfidence(candidate));
  }

  for (const key of ["scores", "confidences", "probabilities", "confidence_by_label"]) {
    const scoreMap = rawOutput[key];
    if (!isObjectRecord(scoreMap)) continue;
    for (const [label, confidenceValue] of Object.entries(scoreMap)) {
      addCandidate(candidates, label, numericConfidence(confidenceValue));
    }
  }

  return [...candidates.values()].sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1));
};

export const fieldCandidates = (meta: Record<string, unknown> | undefined): CandidateOption[] => {
  const rawCandidates = meta?.candidate_values;
  if (!Array.isArray(rawCandidates)) return [];
  const candidates = new Map<string, CandidateOption>();
  for (const candidate of rawCandidates)
    addCandidate(
      candidates,
      candidate,
      candidateConfidence(candidate),
      candidateEvidenceDocRefs(candidate),
    );
  return [...candidates.values()];
};

const objectListItemKey = (item: Record<string, unknown>): string => JSON.stringify(item);

export const objectListItemCandidate = (
  meta: Record<string, unknown> | undefined,
  item: Record<string, unknown>,
): CandidateOption | null => {
  const itemKey = objectListItemKey(item);
  for (const candidate of fieldCandidates(meta)) {
    if (isObjectRecord(candidate.value) && objectListItemKey(candidate.value) === itemKey) {
      return candidate;
    }
  }
  return null;
};

export const objectListItemEvidenceDocRefs = (
  meta: Record<string, unknown> | undefined,
  item: Record<string, unknown>,
  index?: number,
): string[] => {
  const itemRefs = itemEvidenceDocRefs(meta, index);
  if (itemRefs.length > 0) return itemRefs;
  return objectListItemCandidate(meta, item)?.evidenceDocRefs ?? [];
};

export const listItemEvidenceDocRefs = (
  meta: Record<string, unknown> | undefined,
  item: unknown,
  index?: number,
): string[] => {
  const itemRefs = itemEvidenceDocRefs(meta, index);
  if (itemRefs.length > 0) return itemRefs;
  return listItemCandidate(meta, item)?.evidenceDocRefs ?? [];
};

const itemEvidenceDocRefs = (
  meta: Record<string, unknown> | undefined,
  index?: number,
): string[] => {
  if (index === undefined) return [];
  const itemEvidence = meta?.item_evidence;
  if (!Array.isArray(itemEvidence)) return [];
  return allDocRefs(itemEvidence[index]);
};

export const listItemCandidate = (
  meta: Record<string, unknown> | undefined,
  item: unknown,
): CandidateOption | null => {
  const itemKey = formatValue(item).trim().toLowerCase();
  if (!itemKey) return null;
  for (const candidate of fieldCandidates(meta)) {
    for (const value of normalizeListValue(candidate.value)) {
      if (value.toLowerCase() === itemKey) {
        return candidate;
      }
    }
  }
  return null;
};

const emptyValueForDtype = (dtype: string | undefined): unknown => {
  if (dtype === "bool") return false;
  if (dtype === "list" || dtype === "object_list") return [];
  return "";
};

export const schemaInitialData = (
  schema: ContentEnrichmentCatalogSchema | null,
): Record<string, unknown> | null => {
  if (!schema || schema.fields.length === 0) return null;
  return Object.fromEntries(
    schema.fields
      .filter((field) => field.name.trim())
      .map((field) => [field.name.trim(), emptyValueForDtype(field.dtype)]),
  );
};

export const schemaFieldsMeta = (
  schema: ContentEnrichmentCatalogSchema | null,
): Record<string, Record<string, unknown>> | null => {
  if (!schema || schema.fields.length === 0) return null;
  return Object.fromEntries(
    schema.fields
      .filter((field) => field.name.trim())
      .map((field) => [
        field.name.trim(),
        {
          dtype: field.dtype,
          required: field.required,
          description: field.description,
          fields: field.fields ?? [],
          evidence: [],
          candidate_values: [],
        },
      ]),
  );
};

const objectListItemLabel = (item: Record<string, unknown>): string => {
  const entries = Object.entries(item).filter(([, value]) => hasDisplayValue(value));
  if (entries.length === 0) return "{}";
  return entries
    .slice(0, 2)
    .map(([, value]) => formatValue(value))
    .filter(Boolean)
    .join(" · ");
};

export const collectListSuggestions = (
  draft: string[],
  aiValue: unknown,
  meta: Record<string, unknown> | undefined,
): ListSuggestion[] => {
  const taken = new Set(draft.map((item) => item.toLowerCase()));
  const result = new Map<string, ListSuggestion>();
  for (const item of normalizeListValue(aiValue)) {
    const key = item.toLowerCase();
    if (taken.has(key) || result.has(key)) continue;
    result.set(key, { label: item, value: item, confidence: null });
  }
  for (const candidate of fieldCandidates(meta)) {
    for (const item of normalizeListValue(candidate.value)) {
      const key = item.toLowerCase();
      if (taken.has(key) || result.has(key)) continue;
      result.set(key, { label: item, value: item, confidence: candidate.confidence });
    }
  }
  return [...result.values()].sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1));
};

export const collectObjectListSuggestions = (
  draft: Array<Record<string, unknown>>,
  aiValue: unknown,
  meta: Record<string, unknown> | undefined,
): ObjectListSuggestion[] => {
  const taken = new Set(draft.map((item) => JSON.stringify(item)));
  const result = new Map<string, ObjectListSuggestion>();
  for (const item of normalizeObjectListValue(aiValue)) {
    const key = JSON.stringify(item);
    if (taken.has(key) || result.has(key)) continue;
    result.set(key, { label: objectListItemLabel(item), value: item, confidence: null });
  }
  for (const candidate of fieldCandidates(meta)) {
    const items = isObjectRecord(candidate.value)
      ? [candidate.value]
      : normalizeObjectListValue(candidate.value);
    for (const item of items) {
      const key = JSON.stringify(item);
      if (taken.has(key) || result.has(key)) continue;
      result.set(key, {
        label: objectListItemLabel(item),
        value: item,
        confidence: candidate.confidence,
      });
    }
  }
  return [...result.values()].sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1));
};

export const fieldBucket = (
  rawValue: unknown,
  meta: Record<string, unknown> | undefined,
  fieldNeedsReview: boolean,
): FieldBucket => {
  if (fieldNeedsReview) return "attention";
  if (meta?.required === true && !hasDisplayValue(rawValue)) return "attention";
  return "reviewed";
};
