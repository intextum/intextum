export type ExtractionChildDtype = "str" | "int" | "float" | "bool" | "list" | "date" | "currency";

export interface ExtractionChildFieldDescriptor {
  name?: unknown;
  dtype?: unknown;
}

const EXTRACTION_CHILD_DTYPES = new Set<ExtractionChildDtype>([
  "str",
  "int",
  "float",
  "bool",
  "list",
  "date",
  "currency",
]);

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const childDtype = (dtype: unknown): ExtractionChildDtype | undefined =>
  typeof dtype === "string" && EXTRACTION_CHILD_DTYPES.has(dtype as ExtractionChildDtype)
    ? (dtype as ExtractionChildDtype)
    : undefined;

const formatDraftValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return value.map(formatDraftValue).filter(Boolean).join(", ");
  return JSON.stringify(value);
};

const normalizeDraftListValue = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value
      .map(formatDraftValue)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (typeof value !== "string") {
    const formatted = formatDraftValue(value).trim();
    return formatted ? [formatted] : [];
  }

  const trimmed = value.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (Array.isArray(parsed)) return normalizeDraftListValue(parsed);
    } catch {
      // Keep plain textarea parsing for non-JSON list drafts.
    }
  }
  return trimmed
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const parseNumberDraft = (value: string): number | null => {
  const compact = value.trim().replace(/\s/g, "");
  if (!compact) return null;
  const normalized =
    compact.includes(",") && compact.lastIndexOf(",") > compact.lastIndexOf(".")
      ? compact.replace(/\./g, "").replace(",", ".")
      : compact.replace(/,/g, "");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

export const formatObjectListChildValue = (value: unknown, dtype: unknown): string => {
  if (childDtype(dtype) === "list") return normalizeDraftListValue(value).join("\n");
  return formatDraftValue(value);
};

export const parseObjectListChildDraftValue = (value: unknown, dtype: unknown): unknown => {
  const resolvedDtype = childDtype(dtype);
  if (resolvedDtype === "list") return normalizeDraftListValue(value);
  if (typeof value !== "string") return value;

  const trimmed = value.trim();
  if (!trimmed) return "";
  if (resolvedDtype === "int") {
    const parsed = parseNumberDraft(trimmed);
    return parsed !== null ? Math.trunc(parsed) : trimmed;
  }
  if (resolvedDtype === "float") {
    const parsed = parseNumberDraft(trimmed);
    return parsed !== null ? parsed : trimmed;
  }
  if (resolvedDtype === "bool") {
    const normalized = trimmed.toLowerCase();
    if (["true", "yes", "1", "ja"].includes(normalized)) return true;
    if (["false", "no", "0", "nein"].includes(normalized)) return false;
    return trimmed;
  }
  if (resolvedDtype === "currency" && trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (isObjectRecord(parsed)) return parsed;
    } catch {
      return trimmed;
    }
  }
  return trimmed;
};

const hasDraftDisplayValue = (value: unknown): boolean => {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return true;
};

export const coerceObjectListItemDraft = (
  item: Record<string, unknown>,
  fields: ExtractionChildFieldDescriptor[],
): Record<string, unknown> => {
  const dtypeByName = new Map<string, unknown>();
  for (const field of fields) {
    if (typeof field.name === "string" && field.name.trim()) {
      dtypeByName.set(field.name.trim(), field.dtype);
    }
  }

  return Object.fromEntries(
    Object.entries(item)
      .map(([name, value]) => [name, parseObjectListChildDraftValue(value, dtypeByName.get(name))])
      .filter(([, value]) => hasDraftDisplayValue(value)),
  );
};

export const mergeExtractionFieldsMeta = (
  schemaMeta: Record<string, Record<string, unknown>> | null,
  runtimeMeta: Record<string, unknown> | null,
): Record<string, Record<string, unknown>> | null => {
  if (!schemaMeta && !runtimeMeta) return null;
  const keys = new Set<string>([
    ...Object.keys(schemaMeta ?? {}),
    ...Object.keys(runtimeMeta ?? {}),
  ]);
  const merged: Record<string, Record<string, unknown>> = {};
  for (const key of keys) {
    const schemaEntry = schemaMeta?.[key];
    const runtimeEntry = runtimeMeta?.[key];
    const schemaRecord = isObjectRecord(schemaEntry) ? schemaEntry : {};
    const runtimeRecord = isObjectRecord(runtimeEntry) ? runtimeEntry : {};
    const schemaFields = Array.isArray(schemaRecord.fields) ? schemaRecord.fields : [];
    const runtimeFields = Array.isArray(runtimeRecord.fields) ? runtimeRecord.fields : [];
    const entry: Record<string, unknown> = {
      ...schemaRecord,
      ...runtimeRecord,
    };
    if (runtimeFields.length > 0 || schemaFields.length > 0) {
      entry.fields = runtimeFields.length > 0 ? runtimeFields : schemaFields;
    }
    merged[key] = entry;
  }
  return merged;
};
