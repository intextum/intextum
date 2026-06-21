import { isObjectRecord } from "./content-enrichment.ts";

export type ReviewAuditStatus = "accepted" | "corrected" | "unreviewed";
export type ReviewAuditAction = "accepted" | "corrected" | "reset";

export interface ReviewAuditHistoryEntry {
  action: ReviewAuditAction;
  updatedAt: string | null;
  updatedBy: string | null;
  label: string | null;
  fields: string[];
}

export interface ClassificationAuditSummary {
  effectiveLabel: string | null;
  aiLabel: string | null;
  reviewStatus: ReviewAuditStatus | null;
  matchesAi: boolean | null;
  latestReviewEntry: ReviewAuditHistoryEntry | null;
}

export interface ExtractionAuditSummary {
  reviewStatus: ReviewAuditStatus | null;
  totalComparableFields: number;
  changedFieldCount: number;
  unchangedFieldCount: number;
  overrideFieldCount: number;
  fieldsWithEvidenceCount: number;
  missingEvidenceCount: number;
  missingRequiredCount: number;
  conflictedCount: number;
  reviewBlockerCount: number;
  changedFields: string[];
  latestReviewEntry: ReviewAuditHistoryEntry | null;
}

const readString = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value.trim() : null;

const readStringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];

const readReviewStatus = (value: unknown): ReviewAuditStatus | null => {
  if (!isObjectRecord(value)) {
    return null;
  }
  const status = value.review_status;
  if (status === "accepted" || status === "corrected") {
    return status;
  }
  return null;
};

const inferReviewStatusFromHistory = (
  entry: ReviewAuditHistoryEntry | null,
): ReviewAuditStatus | null => {
  if (!entry) {
    return null;
  }
  if (entry.action === "accepted" || entry.action === "corrected") {
    return entry.action;
  }
  if (entry.action === "reset") {
    return "unreviewed";
  }
  return null;
};

const readClassificationLabel = (value: unknown): string | null => {
  if (!isObjectRecord(value)) {
    return null;
  }
  return readString(value.label);
};

const readObject = (value: unknown, key: string): Record<string, unknown> | null => {
  if (!isObjectRecord(value) || !isObjectRecord(value[key])) {
    return null;
  }
  return value[key];
};

const stableSerialize = (value: unknown): string => {
  if (value === undefined) {
    return "__undefined__";
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    return Number.isNaN(value) ? "__nan__" : String(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(",")}]`;
  }
  if (isObjectRecord(value)) {
    return `{${Object.keys(value)
      .sort((a, b) => a.localeCompare(b))
      .map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? String(value);
};

const readHistoryEntries = (value: unknown): ReviewAuditHistoryEntry[] => {
  if (!isObjectRecord(value) || !Array.isArray(value.review_history)) {
    return [];
  }

  return value.review_history
    .filter(
      (item): item is Record<string, unknown> =>
        isObjectRecord(item) &&
        (item.action === "accepted" || item.action === "corrected" || item.action === "reset"),
    )
    .map((entry) => ({
      action: entry.action as ReviewAuditAction,
      updatedAt: readString(entry.updated_at),
      updatedBy: readString(entry.updated_by),
      label: readString(entry.label),
      fields: readStringList(entry.fields),
    }));
};

export function buildClassificationAuditSummary(
  classification: unknown,
  classificationSystem: unknown,
): ClassificationAuditSummary | null {
  const effectiveLabel = readClassificationLabel(classification);
  const aiLabel = readClassificationLabel(classificationSystem);
  const latestReviewEntry = readHistoryEntries(classification).at(-1) ?? null;

  if (effectiveLabel === null && aiLabel === null && latestReviewEntry === null) {
    return null;
  }

  const reviewStatus =
    readReviewStatus(classification) ??
    inferReviewStatusFromHistory(latestReviewEntry) ??
    (effectiveLabel !== null || aiLabel !== null ? "unreviewed" : null);
  const matchesAi = effectiveLabel !== null && aiLabel !== null ? effectiveLabel === aiLabel : null;

  return {
    effectiveLabel,
    aiLabel,
    reviewStatus,
    matchesAi,
    latestReviewEntry,
  };
}

export function buildExtractionAuditSummary(
  extraction: unknown,
  extractionSystem: unknown,
): ExtractionAuditSummary | null {
  const effectiveData = readObject(extraction, "data") ?? {};
  const aiData = readObject(extractionSystem, "data") ?? {};
  const fieldPayloads = readObject(extraction, "fields") ?? {};
  const summary = readObject(extraction, "summary");
  const latestReviewEntry = readHistoryEntries(extraction).at(-1) ?? null;

  const comparableFieldNames = [
    ...new Set([...Object.keys(aiData), ...Object.keys(effectiveData)]),
  ].sort((a, b) => a.localeCompare(b));
  const changedFields = comparableFieldNames.filter(
    (fieldName) => stableSerialize(effectiveData[fieldName]) !== stableSerialize(aiData[fieldName]),
  );
  const overrideFieldCount = Object.entries(fieldPayloads).filter(
    ([, value]) => isObjectRecord(value) && value.overridden === true,
  ).length;

  const fieldsWithEvidenceCount =
    summary && typeof summary.fields_with_evidence === "number"
      ? summary.fields_with_evidence
      : Object.values(fieldPayloads).filter(
          (value) =>
            isObjectRecord(value) && Array.isArray(value.evidence) && value.evidence.length > 0,
        ).length;
  const missingEvidenceCount = readStringList(summary?.fields_without_evidence).length;
  const missingRequiredFields = readStringList(summary?.missing_required_fields);
  const conflictedFields = readStringList(summary?.conflicted_fields);
  const missingRequiredCount = missingRequiredFields.length;
  const conflictedCount = conflictedFields.length;
  const reviewBlockerCount = new Set([...missingRequiredFields, ...conflictedFields]).size;
  const reviewStatus =
    readReviewStatus(extraction) ??
    inferReviewStatusFromHistory(latestReviewEntry) ??
    (comparableFieldNames.length > 0 || latestReviewEntry !== null ? "unreviewed" : null);

  if (reviewStatus === null && comparableFieldNames.length === 0 && latestReviewEntry === null) {
    return null;
  }

  return {
    reviewStatus,
    totalComparableFields: comparableFieldNames.length,
    changedFieldCount: changedFields.length,
    unchangedFieldCount: comparableFieldNames.length - changedFields.length,
    overrideFieldCount,
    fieldsWithEvidenceCount,
    missingEvidenceCount,
    missingRequiredCount,
    conflictedCount,
    reviewBlockerCount,
    changedFields,
    latestReviewEntry,
  };
}
