export type DocumentExtractionDtype =
  | "str"
  | "int"
  | "float"
  | "bool"
  | "list"
  | "date"
  | "currency"
  | "object_list";

export type DocumentExtractionChildDtype = Exclude<DocumentExtractionDtype, "object_list">;

export interface DocumentExtractionFieldDraft {
  name: string;
  dtype: DocumentExtractionDtype;
  description: string;
  required: boolean;
  clustered_under_heading: boolean;
  fields: DocumentExtractionChildFieldDraft[];
  examples: DocumentExtractionExampleDraft[];
}

export interface DocumentExtractionExampleDraft {
  text: string;
  value: string;
  child_values: Record<string, string>;
  extraction_text: string;
}

export interface DocumentExtractionChildFieldDraft {
  name: string;
  dtype: DocumentExtractionChildDtype;
  description: string;
  required: boolean;
}

export interface DocumentExtractionSceneExtractionDraft {
  id: string;
  field: string;
  extraction_text: string;
  value: string;
  child_values: Record<string, string>;
}

export interface DocumentExtractionSceneDraft {
  id: string;
  text: string;
  extractions: DocumentExtractionSceneExtractionDraft[];
}

export interface DocumentExtractionSchemaDraft {
  id: string;
  name: string;
  version: number | null;
  description: string;
  fields: DocumentExtractionFieldDraft[];
  scenes: DocumentExtractionSceneDraft[];
}

export interface DocumentClassDraft {
  id: string;
  name: string;
  version: number | null;
  description: string;
  aliases_text: string;
  extraction_schema: DocumentExtractionSchemaDraft | null;
}

export type ContentEnrichmentValidationError =
  | "class_name_required"
  | "class_name_duplicate"
  | "schema_name_required"
  | "schema_name_duplicate"
  | "field_name_required"
  | "field_name_duplicate"
  | "field_description_required"
  | "field_example_required"
  | "scene_extraction_field_unknown"
  | "scene_extraction_anchor_not_in_text";

export interface ContentEnrichmentQueueSummary {
  staleCount: number;
  hasStaleFiles: boolean;
}

export interface ContentEnrichmentRerunSummary {
  queuedCount: number;
  matchedCount: number;
  errorCount: number;
  hasQueuedFiles: boolean;
}

export const CONTENT_ENRICHMENT_CLASSIFICATION_SETTINGS_KIND =
  "content_enrichment_classification_settings" as const;
export const CONTENT_ENRICHMENT_EXTRACTION_SETTINGS_KIND =
  "content_enrichment_extraction_settings" as const;
export const CONTENT_ENRICHMENT_CLASS_SETTINGS_KIND = "content_enrichment_class_settings" as const;
export const CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION = 1;

export interface ContentEnrichmentClassificationSettingsExport {
  kind: typeof CONTENT_ENRICHMENT_CLASSIFICATION_SETTINGS_KIND;
  schema_version: typeof CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION;
  classification: {
    name: string;
    description: string;
    aliases: string[];
  };
}

export interface ContentEnrichmentExtractionSettingsExport {
  kind: typeof CONTENT_ENRICHMENT_EXTRACTION_SETTINGS_KIND;
  schema_version: typeof CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION;
  extraction: {
    enabled: boolean;
    schema: Record<string, unknown> | null;
  };
}

export interface ContentEnrichmentClassSettingsExport {
  kind: typeof CONTENT_ENRICHMENT_CLASS_SETTINGS_KIND;
  schema_version: typeof CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION;
  classification: ContentEnrichmentClassificationSettingsExport["classification"];
  extraction: ContentEnrichmentExtractionSettingsExport["extraction"];
}

const EXTRACTION_DTYPES: DocumentExtractionDtype[] = [
  "str",
  "int",
  "float",
  "bool",
  "list",
  "date",
  "currency",
  "object_list",
];

const CHILD_EXTRACTION_DTYPES: DocumentExtractionChildDtype[] = [
  "str",
  "int",
  "float",
  "bool",
  "list",
  "date",
  "currency",
];

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const exampleValueToDraftString = (value: unknown): string => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "")).join("\n");
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "";
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
};

function normalizeAliases(value: string): string[] {
  return value
    .split(",")
    .map((alias) => alias.trim())
    .filter(Boolean);
}

function createCatalogDraftId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID().replace(/-/g, "");
  }
  return `draft_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
}

function isExtractionDtype(value: unknown): value is DocumentExtractionDtype {
  return typeof value === "string" && EXTRACTION_DTYPES.includes(value as DocumentExtractionDtype);
}

function isChildExtractionDtype(value: unknown): value is DocumentExtractionChildDtype {
  return (
    typeof value === "string" &&
    CHILD_EXTRACTION_DTYPES.includes(value as DocumentExtractionChildDtype)
  );
}

export function createEmptyExtractionFieldDraft(): DocumentExtractionFieldDraft {
  return {
    name: "",
    dtype: "str",
    description: "",
    required: false,
    clustered_under_heading: true,
    fields: [],
    examples: [],
  };
}

export function createEmptyExtractionChildFieldDraft(): DocumentExtractionChildFieldDraft {
  return {
    name: "",
    dtype: "str",
    description: "",
    required: false,
  };
}

export function createEmptyExtractionSchemaDraft(className = ""): DocumentExtractionSchemaDraft {
  const normalizedClassName = className.trim();
  return {
    id: createCatalogDraftId(),
    name: normalizedClassName ? `${normalizedClassName} Fields` : "",
    version: null,
    description: "",
    fields: [createEmptyExtractionFieldDraft()],
    scenes: [],
  };
}

export function createEmptySceneDraft(): DocumentExtractionSceneDraft {
  return {
    id: createCatalogDraftId(),
    text: "",
    extractions: [],
  };
}

export function createEmptySceneExtractionDraft(
  fieldName = "",
): DocumentExtractionSceneExtractionDraft {
  return {
    id: createCatalogDraftId(),
    field: fieldName,
    extraction_text: "",
    value: "",
    child_values: {},
  };
}

export function createEmptyDocumentClassDraft(): DocumentClassDraft {
  return {
    id: createCatalogDraftId(),
    name: "",
    version: null,
    description: "",
    aliases_text: "",
    extraction_schema: null,
  };
}

export function cloneDocumentClassDraft(draft: DocumentClassDraft): DocumentClassDraft {
  return {
    ...draft,
    extraction_schema: draft.extraction_schema
      ? {
          ...draft.extraction_schema,
          fields: draft.extraction_schema.fields.map((field) => ({
            ...field,
            fields: field.fields.map((child) => ({ ...child })),
            examples: field.examples.map((example) => ({
              ...example,
              child_values: { ...example.child_values },
            })),
          })),
          scenes: draft.extraction_schema.scenes.map((scene) => ({
            ...scene,
            extractions: scene.extractions.map((entry) => ({
              ...entry,
              child_values: { ...entry.child_values },
            })),
          })),
        }
      : null,
  };
}

export function replaceDocumentClassDraft(
  drafts: DocumentClassDraft[],
  index: number | null,
  draft: DocumentClassDraft,
): DocumentClassDraft[] {
  if (index === null) {
    return [...drafts, cloneDocumentClassDraft(draft)];
  }
  return drafts.map((entry, entryIndex) =>
    entryIndex === index ? cloneDocumentClassDraft(draft) : entry,
  );
}

export function removeDocumentClassDraft(
  drafts: DocumentClassDraft[],
  index: number,
): DocumentClassDraft[] {
  return drafts.filter((_, entryIndex) => entryIndex !== index);
}

function invalidSettingsImport(): Error {
  return new Error("invalid_import");
}

function validateImportEnvelope(
  value: unknown,
  kind: string,
): asserts value is Record<string, unknown> {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  if (value.kind !== kind || value.schema_version !== CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION) {
    throw invalidSettingsImport();
  }
}

function assertString(value: unknown): asserts value is string {
  if (typeof value !== "string") {
    throw invalidSettingsImport();
  }
}

function assertOptionalBoolean(value: unknown): void {
  if (value !== undefined && typeof value !== "boolean") {
    throw invalidSettingsImport();
  }
}

function assertExtractionExampleShape(value: unknown): void {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  assertString(value.text);
  if (value.extraction_text !== undefined) {
    assertString(value.extraction_text);
  }
}

function assertSceneExtractionShape(value: unknown): void {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  assertString(value.field);
  assertString(value.extraction_text);
}

function assertSceneShape(value: unknown): void {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  assertString(value.text);
  if (!Array.isArray(value.extractions)) {
    throw invalidSettingsImport();
  }
  value.extractions.forEach(assertSceneExtractionShape);
}

function assertChildFieldShape(value: unknown): void {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  assertString(value.name);
  if (!isChildExtractionDtype(value.dtype)) {
    throw invalidSettingsImport();
  }
  assertString(value.description);
  assertOptionalBoolean(value.required);
}

function assertExtractionFieldShape(value: unknown): void {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  assertString(value.name);
  if (!isExtractionDtype(value.dtype)) {
    throw invalidSettingsImport();
  }
  assertString(value.description);
  assertOptionalBoolean(value.required);
  assertOptionalBoolean(value.clustered_under_heading);
  if (value.fields !== undefined) {
    if (!Array.isArray(value.fields)) {
      throw invalidSettingsImport();
    }
    value.fields.forEach(assertChildFieldShape);
  }
  if (
    value.dtype === "object_list" &&
    (!Array.isArray(value.fields) || value.fields.length === 0)
  ) {
    throw invalidSettingsImport();
  }
  if (value.examples !== undefined) {
    if (!Array.isArray(value.examples)) {
      throw invalidSettingsImport();
    }
    value.examples.forEach(assertExtractionExampleShape);
  }
}

function assertExtractionSchemaShape(value: unknown): asserts value is Record<string, unknown> {
  if (!isObjectRecord(value)) {
    throw invalidSettingsImport();
  }
  assertString(value.name);
  assertString(value.description);
  if (!Array.isArray(value.fields)) {
    throw invalidSettingsImport();
  }
  value.fields.forEach(assertExtractionFieldShape);
  if (value.scenes !== undefined) {
    if (!Array.isArray(value.scenes)) {
      throw invalidSettingsImport();
    }
    value.scenes.forEach(assertSceneShape);
  }
}

function toExtractionSchemaDraft(value: unknown): DocumentExtractionSchemaDraft | null {
  if (!isObjectRecord(value)) return null;
  const fieldsByName = new Map<string, Record<string, unknown>>();
  if (Array.isArray(value.fields)) {
    for (const field of value.fields) {
      if (isObjectRecord(field) && typeof field.name === "string") {
        fieldsByName.set(field.name, field);
      }
    }
  }
  return {
    id: typeof value.id === "string" && value.id.trim() ? value.id : createCatalogDraftId(),
    name: typeof value.name === "string" ? value.name : "",
    version:
      typeof value.version === "number" && Number.isInteger(value.version) && value.version > 0
        ? value.version
        : null,
    description: typeof value.description === "string" ? value.description : "",
    scenes: Array.isArray(value.scenes)
      ? value.scenes
          .filter((scene): scene is Record<string, unknown> => isObjectRecord(scene))
          .map((scene) => ({
            id: createCatalogDraftId(),
            text: typeof scene.text === "string" ? scene.text : "",
            extractions: Array.isArray(scene.extractions)
              ? scene.extractions
                  .filter((entry): entry is Record<string, unknown> => isObjectRecord(entry))
                  .map((entry) => {
                    const fieldName = typeof entry.field === "string" ? entry.field : "";
                    const referencedField = fieldsByName.get(fieldName);
                    const referencedDtype =
                      referencedField && isExtractionDtype(referencedField.dtype)
                        ? referencedField.dtype
                        : "str";
                    return {
                      id: createCatalogDraftId(),
                      field: fieldName,
                      extraction_text:
                        typeof entry.extraction_text === "string" ? entry.extraction_text : "",
                      value:
                        referencedDtype === "object_list"
                          ? ""
                          : exampleValueToDraftString(entry.value),
                      child_values:
                        referencedDtype === "object_list" && isObjectRecord(entry.value)
                          ? Object.fromEntries(
                              Object.entries(entry.value).map(([key, entryValue]) => [
                                key,
                                exampleValueToDraftString(entryValue),
                              ]),
                            )
                          : {},
                    };
                  })
              : [],
          }))
      : [],
    fields: Array.isArray(value.fields)
      ? value.fields
          .filter((field): field is Record<string, unknown> => isObjectRecord(field))
          .map((field) => {
            const dtype = isExtractionDtype(field.dtype) ? field.dtype : "str";
            return {
              name: typeof field.name === "string" ? field.name : "",
              dtype,
              description: typeof field.description === "string" ? field.description : "",
              required: Boolean(field.required),
              clustered_under_heading:
                typeof field.clustered_under_heading === "boolean"
                  ? field.clustered_under_heading
                  : true,
              examples: Array.isArray(field.examples)
                ? field.examples
                    .filter((example): example is Record<string, unknown> =>
                      isObjectRecord(example),
                    )
                    .map((example) => ({
                      text: typeof example.text === "string" ? example.text : "",
                      value:
                        field.dtype === "object_list"
                          ? ""
                          : exampleValueToDraftString(example.value),
                      child_values:
                        field.dtype === "object_list" && isObjectRecord(example.value)
                          ? Object.fromEntries(
                              Object.entries(example.value).map(([key, entryValue]) => [
                                key,
                                exampleValueToDraftString(entryValue),
                              ]),
                            )
                          : {},
                      extraction_text:
                        typeof example.extraction_text === "string" ? example.extraction_text : "",
                    }))
                : [],
              fields: Array.isArray(field.fields)
                ? field.fields
                    .filter((child): child is Record<string, unknown> => isObjectRecord(child))
                    .map((child) => ({
                      name: typeof child.name === "string" ? child.name : "",
                      dtype: isChildExtractionDtype(child.dtype) ? child.dtype : "str",
                      description: typeof child.description === "string" ? child.description : "",
                      required: Boolean(child.required),
                    }))
                : [],
            };
          })
      : [],
  };
}

export function toDocumentClassDrafts(value: unknown): DocumentClassDraft[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is Record<string, unknown> => isObjectRecord(item))
    .map((item) => ({
      id: typeof item.id === "string" && item.id.trim() ? item.id : createCatalogDraftId(),
      name: typeof item.name === "string" ? item.name : "",
      version:
        typeof item.version === "number" && Number.isInteger(item.version) && item.version > 0
          ? item.version
          : null,
      description: typeof item.description === "string" ? item.description : "",
      aliases_text: Array.isArray(item.aliases)
        ? item.aliases.filter((alias): alias is string => typeof alias === "string").join(", ")
        : "",
      extraction_schema: toExtractionSchemaDraft(item.extraction_schema),
    }));
}

export function serializeDocumentClassDrafts(
  drafts: DocumentClassDraft[],
): Array<Record<string, unknown>> {
  return drafts.map((draft) => ({
    id: draft.id,
    name: draft.name.trim(),
    description: draft.description.trim(),
    aliases: normalizeAliases(draft.aliases_text),
    extraction_schema: draft.extraction_schema
      ? {
          id: draft.extraction_schema.id,
          name: draft.extraction_schema.name.trim(),
          description: draft.extraction_schema.description.trim(),
          ...(draft.extraction_schema.scenes.length > 0
            ? {
                scenes: serializeSceneDrafts(
                  draft.extraction_schema.scenes,
                  draft.extraction_schema.fields,
                ),
              }
            : {}),
          fields: draft.extraction_schema.fields.map((field) => ({
            name: field.name.trim(),
            dtype: field.dtype,
            description: field.description.trim(),
            required: field.required,
            ...(field.dtype === "list" || field.dtype === "object_list"
              ? { clustered_under_heading: field.clustered_under_heading }
              : {}),
            fields:
              field.dtype === "object_list"
                ? field.fields.map((child) => ({
                    name: child.name.trim(),
                    dtype: child.dtype,
                    description: child.description.trim(),
                    required: child.required,
                  }))
                : [],
            examples: field.examples
              .map((example) => {
                const anchor = example.extraction_text.trim();
                const serialized: Record<string, unknown> = {
                  text: example.text.trim(),
                  value: serializeExampleValue(field, example),
                };
                if (anchor) {
                  serialized.extraction_text = anchor;
                }
                return serialized;
              })
              .filter(
                (example) =>
                  typeof example.text === "string" &&
                  example.text &&
                  !isEmptyExampleValue(example.value),
              ),
          })),
        }
      : null,
  }));
}

export function buildClassificationSettingsExport(
  draft: DocumentClassDraft,
): ContentEnrichmentClassificationSettingsExport {
  const serialized = serializeDocumentClassDrafts([draft])[0] ?? {};
  return {
    kind: CONTENT_ENRICHMENT_CLASSIFICATION_SETTINGS_KIND,
    schema_version: CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION,
    classification: {
      name: typeof serialized.name === "string" ? serialized.name : "",
      description: typeof serialized.description === "string" ? serialized.description : "",
      aliases: Array.isArray(serialized.aliases)
        ? serialized.aliases.filter((alias): alias is string => typeof alias === "string")
        : [],
    },
  };
}

export function buildExtractionSettingsExport(
  draft: DocumentClassDraft,
): ContentEnrichmentExtractionSettingsExport {
  const serialized = serializeDocumentClassDrafts([draft])[0] ?? {};
  const schema = isObjectRecord(serialized.extraction_schema) ? serialized.extraction_schema : null;
  return {
    kind: CONTENT_ENRICHMENT_EXTRACTION_SETTINGS_KIND,
    schema_version: CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION,
    extraction: {
      enabled: schema !== null,
      schema,
    },
  };
}

function stripExtractionSchemaLifecycleFields(
  schema: Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (!schema) {
    return null;
  }
  const { id: _id, version: _version, ...settings } = schema;
  return settings;
}

export function buildClassSettingsExport(
  draft: DocumentClassDraft,
): ContentEnrichmentClassSettingsExport {
  const classification = buildClassificationSettingsExport(draft).classification;
  const extraction = buildExtractionSettingsExport(draft).extraction;
  const schema = stripExtractionSchemaLifecycleFields(extraction.schema);
  return {
    kind: CONTENT_ENRICHMENT_CLASS_SETTINGS_KIND,
    schema_version: CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION,
    classification,
    extraction: {
      enabled: schema !== null,
      schema,
    },
  };
}

export function applyClassificationSettingsImport(
  draft: DocumentClassDraft,
  value: unknown,
): DocumentClassDraft {
  validateImportEnvelope(value, CONTENT_ENRICHMENT_CLASSIFICATION_SETTINGS_KIND);
  const classification = value.classification;
  if (!isObjectRecord(classification)) {
    throw invalidSettingsImport();
  }
  assertString(classification.name);
  assertString(classification.description);
  if (!classification.name.trim() || !Array.isArray(classification.aliases)) {
    throw invalidSettingsImport();
  }
  const aliases = classification.aliases.map((alias) => {
    assertString(alias);
    return alias;
  });
  return {
    ...draft,
    name: classification.name,
    description: classification.description,
    aliases_text: aliases.join(", "),
  };
}

export function applyExtractionSettingsImport(
  draft: DocumentClassDraft,
  value: unknown,
): DocumentClassDraft {
  validateImportEnvelope(value, CONTENT_ENRICHMENT_EXTRACTION_SETTINGS_KIND);
  const extraction = value.extraction;
  if (!isObjectRecord(extraction) || typeof extraction.enabled !== "boolean") {
    throw invalidSettingsImport();
  }
  if (!extraction.enabled || extraction.schema === null) {
    return {
      ...draft,
      extraction_schema: null,
    };
  }

  assertExtractionSchemaShape(extraction.schema);
  const currentSchema = draft.extraction_schema ?? createEmptyExtractionSchemaDraft(draft.name);
  const schemaDraft = toExtractionSchemaDraft({
    ...extraction.schema,
    id: currentSchema.id,
    version: currentSchema.version,
  });
  if (schemaDraft === null) {
    throw invalidSettingsImport();
  }
  const nextDraft = {
    ...draft,
    extraction_schema: schemaDraft,
  };
  const validationError = validateContentEnrichmentDrafts([nextDraft]);
  if (validationError) {
    throw invalidSettingsImport();
  }
  return nextDraft;
}

export function applyClassSettingsImport(
  draft: DocumentClassDraft,
  value: unknown,
): DocumentClassDraft {
  validateImportEnvelope(value, CONTENT_ENRICHMENT_CLASS_SETTINGS_KIND);
  const nextDraft = applyClassificationSettingsImport(draft, {
    kind: CONTENT_ENRICHMENT_CLASSIFICATION_SETTINGS_KIND,
    schema_version: CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION,
    classification: value.classification,
  });
  return applyExtractionSettingsImport(nextDraft, {
    kind: CONTENT_ENRICHMENT_EXTRACTION_SETTINGS_KIND,
    schema_version: CONTENT_ENRICHMENT_SETTINGS_SCHEMA_VERSION,
    extraction: value.extraction,
  });
}

interface SerializedSceneExtraction {
  field: string;
  extraction_text: string;
  value: unknown;
}

interface SerializedScene {
  text: string;
  extractions: SerializedSceneExtraction[];
}

function serializeSceneDrafts(
  scenes: DocumentExtractionSceneDraft[],
  fields: DocumentExtractionFieldDraft[],
): SerializedScene[] {
  const fieldsByName = new Map(fields.map((field) => [field.name.trim(), field]));
  const results: SerializedScene[] = [];
  for (const scene of scenes) {
    const extractions: SerializedSceneExtraction[] = [];
    for (const entry of scene.extractions) {
      const referencedField = fieldsByName.get(entry.field.trim());
      if (!referencedField) continue;
      const anchor = entry.extraction_text.trim();
      if (!anchor) continue;
      const value = serializeSceneExtractionValue(referencedField, entry);
      if (isEmptyExampleValue(value)) continue;
      extractions.push({
        field: referencedField.name.trim(),
        extraction_text: anchor,
        value,
      });
    }
    const trimmedText = scene.text.trim();
    if (!trimmedText || extractions.length === 0) continue;
    results.push({ text: trimmedText, extractions });
  }
  return results;
}

function serializeSceneExtractionValue(
  field: DocumentExtractionFieldDraft,
  entry: DocumentExtractionSceneExtractionDraft,
): unknown {
  if (field.dtype === "object_list") {
    return Object.fromEntries(
      field.fields
        .map((child) => [
          child.name.trim(),
          coerceExampleScalarValue(child.dtype, entry.child_values[child.name] ?? ""),
        ])
        .filter(([name, value]) => name && !isEmptyExampleValue(value)),
    );
  }
  return coerceExampleScalarValue(field.dtype, entry.value);
}

function serializeExampleValue(
  field: DocumentExtractionFieldDraft | DocumentExtractionChildFieldDraft,
  example: DocumentExtractionExampleDraft,
): unknown {
  if ("fields" in field && field.dtype === "object_list") {
    return Object.fromEntries(
      field.fields
        .map((child) => [
          child.name.trim(),
          coerceExampleScalarValue(child.dtype, example.child_values[child.name] ?? ""),
        ])
        .filter(([name, value]) => name && !isEmptyExampleValue(value)),
    );
  }
  if (field.dtype === "object_list") {
    return {};
  }
  return coerceExampleScalarValue(field.dtype, example.value);
}

function coerceExampleScalarValue(dtype: DocumentExtractionChildDtype, value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (dtype === "bool") {
    const normalized = trimmed.toLowerCase();
    if (["true", "yes", "ja", "1"].includes(normalized)) return true;
    if (["false", "no", "nein", "0"].includes(normalized)) return false;
    return trimmed;
  }
  if (dtype === "int") {
    const parsed = Number.parseInt(trimmed, 10);
    return Number.isFinite(parsed) ? parsed : trimmed;
  }
  if (dtype === "float") {
    const parsed = Number.parseFloat(trimmed.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : trimmed;
  }
  if (dtype === "list") {
    return trimmed
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return trimmed;
}

function isEmptyExampleValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return !value.trim();
  if (Array.isArray(value)) return value.length === 0;
  if (isObjectRecord(value)) return Object.keys(value).length === 0;
  return false;
}

export function validateContentEnrichmentDrafts(
  classes: DocumentClassDraft[],
): ContentEnrichmentValidationError | null {
  const classIds = new Set<string>();
  const classNames = new Set<string>();
  const schemaIds = new Set<string>();
  const schemaNames = new Set<string>();

  for (const item of classes) {
    const classId = item.id.trim();
    const className = item.name.trim();
    if (!classId || !className) return "class_name_required";
    const classIdKey = classId.toLowerCase();
    const classNameKey = className.toLowerCase();
    if (classIds.has(classIdKey) || classNames.has(classNameKey)) {
      return "class_name_duplicate";
    }
    classIds.add(classIdKey);
    classNames.add(classNameKey);

    const schema = item.extraction_schema;
    if (!schema) continue;
    const schemaId = schema.id.trim();
    const schemaName = schema.name.trim();
    if (!schemaId || !schemaName) return "schema_name_required";
    const schemaIdKey = schemaId.toLowerCase();
    const schemaNameKey = schemaName.toLowerCase();
    if (schemaIds.has(schemaIdKey) || schemaNames.has(schemaNameKey)) {
      return "schema_name_duplicate";
    }
    schemaIds.add(schemaIdKey);
    schemaNames.add(schemaNameKey);

    const fieldNames = new Set<string>();
    const fieldsByName = new Map<string, DocumentExtractionFieldDraft>();
    for (const field of schema.fields) {
      const fieldName = field.name.trim();
      if (!fieldName) return "field_name_required";
      const fieldKey = fieldName.toLowerCase();
      if (fieldNames.has(fieldKey)) return "field_name_duplicate";
      fieldNames.add(fieldKey);
      fieldsByName.set(fieldKey, field);
      if (!field.description.trim()) return "field_description_required";
      if (field.dtype === "object_list" && field.fields.length === 0) {
        return "field_name_required";
      }
      if (field.dtype === "object_list") {
        const childNames = new Set<string>();
        for (const child of field.fields) {
          const childName = child.name.trim();
          if (!childName) return "field_name_required";
          const childKey = childName.toLowerCase();
          if (childNames.has(childKey)) return "field_name_duplicate";
          childNames.add(childKey);
          if (!child.description.trim()) return "field_description_required";
        }
      }
    }

    for (const scene of schema.scenes) {
      for (const entry of scene.extractions) {
        const fieldName = entry.field.trim();
        if (!fieldName) continue;
        const referencedField = fieldsByName.get(fieldName.toLowerCase());
        if (!referencedField) {
          return "scene_extraction_field_unknown";
        }
        const anchor = entry.extraction_text.trim();
        if (anchor && !scene.text.includes(anchor)) {
          return "scene_extraction_anchor_not_in_text";
        }
        if (anchor && isEmptyExampleValue(serializeSceneExtractionValue(referencedField, entry))) {
          return "field_example_required";
        }
      }
    }
  }

  return null;
}

export function summarizeContentEnrichmentQueue(staleCount: number): ContentEnrichmentQueueSummary {
  const normalizedCount = Number.isFinite(staleCount) ? Math.max(0, Math.trunc(staleCount)) : 0;
  return {
    staleCount: normalizedCount,
    hasStaleFiles: normalizedCount > 0,
  };
}

export function summarizeContentEnrichmentRerun(result: {
  queued: number;
  matched: number;
  errors: number;
}): ContentEnrichmentRerunSummary {
  const queuedCount = Number.isFinite(result.queued) ? Math.max(0, Math.trunc(result.queued)) : 0;
  const matchedCount = Number.isFinite(result.matched)
    ? Math.max(0, Math.trunc(result.matched))
    : 0;
  const errorCount = Number.isFinite(result.errors) ? Math.max(0, Math.trunc(result.errors)) : 0;
  return {
    queuedCount,
    matchedCount,
    errorCount,
    hasQueuedFiles: queuedCount > 0,
  };
}
