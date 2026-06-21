import type { ContentItemInfo } from "../dataProvider.ts";

export const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export type ContentReviewState = "stale" | "needs_review" | "reviewed" | "none";
export type ContentDetailsMode = "document_data";

export interface ContentReviewSubmitDraft {
  classificationLabel?: string | null;
  extractionData?: Record<string, unknown> | null;
  includeClassification?: boolean;
  includeExtraction?: boolean;
}

export function buildContentReviewSubmitPayload(draft: ContentReviewSubmitDraft) {
  const payload: {
    classification_label?: string;
    extraction_data?: Record<string, unknown>;
  } = {};
  if (draft.includeClassification) {
    const label = draft.classificationLabel?.trim();
    if (label) {
      payload.classification_label = label;
    }
  }
  if (draft.includeExtraction && isObjectRecord(draft.extractionData)) {
    payload.extraction_data = draft.extractionData;
  }
  return Object.keys(payload).length > 0 ? payload : null;
}

export function getInitialContentDetailsMode(initialMode?: ContentDetailsMode): ContentDetailsMode {
  return initialMode ?? "document_data";
}

export function canReviewDocumentData(file: ContentItemInfo): boolean {
  return Boolean(
    file.status === "COMPLETED" &&
    file.capabilities?.supports_enrichment &&
    file.capabilities?.supports_review,
  );
}

export type ContentEnrichmentReviewReason =
  | "missing_required_fields"
  | "conflicted_fields"
  | "missing_evidence";

export function getDocumentClassificationLabel(value: unknown): string | null {
  if (!isObjectRecord(value)) {
    return null;
  }
  const label = value.label;
  return typeof label === "string" && label.trim() ? label.trim() : null;
}

export function getDocumentExtractionSchema(value: unknown): string | null {
  if (!isObjectRecord(value)) {
    return null;
  }
  const schemaName = value.schema_name;
  return typeof schemaName === "string" && schemaName.trim() ? schemaName.trim() : null;
}

export function hasStaleContentEnrichment(
  classificationLifecycle: unknown,
  extractionLifecycle: unknown,
): boolean {
  return Boolean(
    (isObjectRecord(classificationLifecycle) && classificationLifecycle.stale === true) ||
    (isObjectRecord(extractionLifecycle) && extractionLifecycle.stale === true),
  );
}

export function getContentEnrichmentReviewStatus(
  classification: unknown,
  extraction: unknown,
): "accepted" | "corrected" | "dismissed" | "unreviewed" | null {
  const classificationReviewStatus =
    isObjectRecord(classification) && typeof classification.review_status === "string"
      ? classification.review_status
      : null;
  const extractionReviewStatus =
    isObjectRecord(extraction) && typeof extraction.review_status === "string"
      ? extraction.review_status
      : null;
  const hasClassification = getDocumentClassificationLabel(classification) !== null;
  const hasExtraction = isObjectRecord(extraction);

  if (classificationReviewStatus === "corrected" || extractionReviewStatus === "corrected") {
    return "corrected";
  }
  if (
    (hasClassification && classificationReviewStatus == null) ||
    (hasExtraction && extractionReviewStatus == null)
  ) {
    return "unreviewed";
  }
  if (classificationReviewStatus === "accepted" || extractionReviewStatus === "accepted") {
    return "accepted";
  }
  if (classificationReviewStatus === "dismissed" || extractionReviewStatus === "dismissed") {
    return "dismissed";
  }
  return null;
}

export function hasNeedsReviewContentEnrichment(extraction: unknown): boolean {
  if (!isObjectRecord(extraction) || !isObjectRecord(extraction.summary)) {
    return false;
  }
  return extraction.summary.needs_review === true;
}

export function getContentReviewState(file: ContentItemInfo): ContentReviewState {
  if (
    file.review_state === "stale" ||
    file.review_state === "needs_review" ||
    file.review_state === "reviewed" ||
    file.review_state === "none"
  ) {
    return file.review_state;
  }

  if (
    hasStaleContentEnrichment(
      file.document_enrichment?.classification_lifecycle,
      file.document_enrichment?.extraction_lifecycle,
    )
  ) {
    return "stale";
  }

  const hasClassification = getDocumentClassificationLabel(file.document_classification) !== null;
  const hasExtraction = isObjectRecord(file.document_extraction);
  if (!hasClassification && !hasExtraction) {
    return "none";
  }

  const reviewStatus = getContentEnrichmentReviewStatus(
    file.document_classification,
    file.document_extraction,
  );
  const reasons = getContentEnrichmentReviewReasons(
    file.document_classification,
    file.document_extraction,
  );
  const needsReview =
    file.document_classification?.needs_review === true ||
    hasNeedsReviewContentEnrichment(file.document_extraction) ||
    reasons.length > 0 ||
    reviewStatus === "unreviewed";

  if (needsReview) {
    return "needs_review";
  }
  if (reviewStatus === "accepted" || reviewStatus === "corrected") {
    return "reviewed";
  }
  return "none";
}

export function getContentEnrichmentReviewReasons(
  classification: unknown,
  extraction: unknown,
): ContentEnrichmentReviewReason[] {
  const reasons = new Set<ContentEnrichmentReviewReason>();

  const classificationReasons =
    isObjectRecord(classification) && Array.isArray(classification.review_reasons)
      ? classification.review_reasons
      : [];
  const extractionReasons =
    isObjectRecord(extraction) &&
    isObjectRecord(extraction.summary) &&
    Array.isArray(extraction.summary.review_reasons)
      ? extraction.summary.review_reasons
      : [];

  for (const entry of [...classificationReasons, ...extractionReasons]) {
    if (!isObjectRecord(entry) || typeof entry.code !== "string") {
      continue;
    }
    if (
      entry.code === "missing_required_fields" ||
      entry.code === "conflicted_fields" ||
      entry.code === "missing_evidence"
    ) {
      reasons.add(entry.code);
    }
  }

  return [...reasons].sort(
    (a, b) => REVIEW_REASON_ORDER.indexOf(a) - REVIEW_REASON_ORDER.indexOf(b),
  );
}

export function matchesDocumentClassificationFilter(
  classification: unknown,
  rawFilter: string,
): boolean {
  const normalizedFilter = rawFilter.trim().toLowerCase();
  if (!normalizedFilter) {
    return true;
  }
  const label = getDocumentClassificationLabel(classification);
  if (!label) {
    return false;
  }
  return label.toLowerCase().includes(normalizedFilter);
}

export function matchesDocumentExtractionFilter(
  extraction: unknown,
  rawValueFilter: string,
  rawFieldFilter = "",
): boolean {
  const normalizedValueFilter = rawValueFilter.trim().toLowerCase();
  if (!normalizedValueFilter) {
    return true;
  }

  if (!isObjectRecord(extraction)) {
    return false;
  }
  const data = extraction.data;
  if (!isObjectRecord(data)) {
    return false;
  }

  const normalizedFieldFilter = rawFieldFilter.trim();
  if (normalizedFieldFilter) {
    return stringifyExtractionValue(data[normalizedFieldFilter])
      .toLowerCase()
      .includes(normalizedValueFilter);
  }

  return stringifyExtractionValue(data).toLowerCase().includes(normalizedValueFilter);
}

export function collectCommonDocumentClasses(
  classifications: readonly unknown[],
  limit = 6,
): string[] {
  return collectTopValues(
    classifications.map((value) => getDocumentClassificationLabel(value)),
    limit,
  );
}

export function collectCommonExtractionFields(
  extractions: readonly unknown[],
  limit = 6,
): string[] {
  const counts = new Map<string, number>();

  for (const extraction of extractions) {
    if (!isObjectRecord(extraction) || !isObjectRecord(extraction.data)) {
      continue;
    }
    for (const key of Object.keys(extraction.data)) {
      const normalizedKey = key.trim();
      if (!normalizedKey) {
        continue;
      }
      counts.set(normalizedKey, (counts.get(normalizedKey) ?? 0) + 1);
    }
  }

  return [...counts.entries()]
    .sort((a, b) => {
      if (b[1] !== a[1]) {
        return b[1] - a[1];
      }
      return a[0].localeCompare(b[0]);
    })
    .slice(0, limit)
    .map(([value]) => value);
}

const EXTRACTION_HIGHLIGHT_PRIORITY = [
  "invoice_number",
  "gross_amount",
  "net_amount",
  "vat_amount",
  "total_amount",
  "due_date",
  "invoice_date",
  "file_number",
  "permit_number",
  "authority",
  "applicant",
  "seller_name",
  "buyer_name",
  "currency",
];

export interface DocumentExtractionHighlight {
  key: string;
  label: string;
  value: string;
}

export interface FilterChip<T extends string> {
  value: T;
  count: number | null;
  active: boolean;
}

export function buildDocumentExtractionHighlights(
  extraction: unknown,
  limit = 2,
): DocumentExtractionHighlight[] {
  if (!isObjectRecord(extraction) || !isObjectRecord(extraction.data)) {
    return [];
  }

  const candidates = Object.entries(extraction.data)
    .map(([key, value], index) => ({
      key,
      value: summarizeExtractionHighlightValue(value),
      index,
    }))
    .filter((entry) => entry.key !== "document_class" && entry.value);

  return candidates
    .sort((a, b) => {
      const aPriority = EXTRACTION_HIGHLIGHT_PRIORITY.indexOf(a.key);
      const bPriority = EXTRACTION_HIGHLIGHT_PRIORITY.indexOf(b.key);
      const normalizedAPriority = aPriority === -1 ? Number.MAX_SAFE_INTEGER : aPriority;
      const normalizedBPriority = bPriority === -1 ? Number.MAX_SAFE_INTEGER : bPriority;
      if (normalizedAPriority !== normalizedBPriority) {
        return normalizedAPriority - normalizedBPriority;
      }
      return a.index - b.index;
    })
    .slice(0, limit)
    .map((entry) => ({
      key: entry.key,
      label: entry.key.replaceAll("_", " "),
      value: entry.value,
    }));
}

export function buildDocumentClassFilterChips(
  facets: readonly { label: string; count: number }[],
  activeFilter: string,
): FilterChip<string>[] {
  return buildFilterChips(
    facets.map((facet) => ({ value: facet.label, count: facet.count })),
    activeFilter,
  );
}

export function buildExtractionValueFilterChips(
  facets: readonly { value: string; count: number }[],
  activeFilter: string,
): FilterChip<string>[] {
  return buildFilterChips(
    facets.map((facet) => ({ value: facet.value, count: facet.count })),
    activeFilter,
  );
}

export function buildExtractionSchemaFilterChips(
  facets: readonly { schema_name: string; count: number }[],
  activeFilter: string,
): FilterChip<string>[] {
  return buildFilterChips(
    facets.map((facet) => ({ value: facet.schema_name, count: facet.count })),
    activeFilter,
  );
}

function buildFilterChips(
  facets: readonly { value: string; count: number }[],
  activeFilter: string,
): FilterChip<string>[] {
  const normalizedActiveFilter = normalizeFilterValue(activeFilter);
  const chips = facets.map((facet) => ({
    value: facet.value,
    count: facet.count,
    active: normalizedActiveFilter === normalizeFilterValue(facet.value),
  }));

  if (!normalizedActiveFilter) {
    return chips;
  }

  const activeChip = chips.find((chip) => chip.active);
  if (activeChip) {
    return chips;
  }

  return [
    {
      value: activeFilter.trim(),
      count: null,
      active: true,
    },
    ...chips,
  ];
}

function normalizeFilterValue(value: string): string {
  return value.trim().toLowerCase();
}

function stringifyExtractionValue(value: unknown): string {
  if (value == null) {
    return "";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => stringifyExtractionValue(item))
      .filter(Boolean)
      .join(" ");
  }
  if (isObjectRecord(value)) {
    return Object.values(value)
      .map((item) => stringifyExtractionValue(item))
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

function summarizeExtractionHighlightValue(value: unknown): string {
  if (value == null) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim().slice(0, 64);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => summarizeExtractionHighlightValue(item))
      .filter(Boolean)
      .slice(0, 2)
      .join(", ")
      .slice(0, 64);
  }
  return "";
}

export function isUserCorrectedClassification(value: unknown): boolean {
  if (!isObjectRecord(value)) {
    return false;
  }
  return value.source === "user_override";
}

const REVIEW_REASON_ORDER: ContentEnrichmentReviewReason[] = [
  "missing_required_fields",
  "conflicted_fields",
  "missing_evidence",
];

function collectTopValues(values: Array<string | null>, limit = 6): string[] {
  const counts = new Map<string, number>();

  for (const value of values) {
    const normalizedValue = value?.trim();
    if (!normalizedValue) {
      continue;
    }
    counts.set(normalizedValue, (counts.get(normalizedValue) ?? 0) + 1);
  }

  return [...counts.entries()]
    .sort((a, b) => {
      if (b[1] !== a[1]) {
        return b[1] - a[1];
      }
      return a[0].localeCompare(b[0]);
    })
    .slice(0, limit)
    .map(([value]) => value);
}
