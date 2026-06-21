import type {
  AllFilesBatchFilters,
  ContentEnrichmentFineTuneTargetKind,
  ContentEnrichmentModelRegistryEntry,
} from "@/dataProvider";

const REGISTRY_MODEL_PREFIX = "registry:";

export type ContentEnrichmentResolvedCurrentModel =
  | {
      kind: "base";
      model: string;
    }
  | {
      kind: "registry";
      model: string;
      registry_model_id: string;
      registry_model: ContentEnrichmentModelRegistryEntry;
    };

export interface ContentEnrichmentTrainingMetricsSummary {
  best_metric: number | null;
  train_loss: number | null;
  eval_loss: number | null;
  training_duration_seconds: number | null;
  artifact_size_bytes: number | null;
  global_step: number | null;
  epochs_completed: number | null;
  train_example_count: number | null;
  validation_example_count: number | null;
  validation_accuracy: number | null;
  validation_exact_match_rate: number | null;
  validation_field_accuracy: number | null;
  validation_status: string | null;
  validation_error: string | null;
}

export interface ContentEnrichmentPromotionImpactSummary {
  stale_count: number;
  stale_increase: number;
  review_path: string;
  target_kind: ContentEnrichmentFineTuneTargetKind;
  target_name: string | null;
}

export interface ContentEnrichmentPromotionRefreshPlan {
  filters: AllFilesBatchFilters;
}

function metricNumber(
  metrics: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  const value = metrics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function normalizeContentEnrichmentSchemaModels(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const normalized: Record<string, string> = {};
  for (const [key, rawValue] of Object.entries(value)) {
    if (typeof key !== "string" || typeof rawValue !== "string") {
      continue;
    }
    const schemaName = key.trim();
    const modelName = rawValue.trim();
    if (!schemaName || !modelName) {
      continue;
    }
    normalized[schemaName] = modelName;
  }
  return normalized;
}

export function parseContentEnrichmentRegistryModelRef(
  model: string | null | undefined,
): string | null {
  if (typeof model !== "string") {
    return null;
  }
  const normalized = model.trim();
  if (!normalized.startsWith(REGISTRY_MODEL_PREFIX)) {
    return null;
  }
  const modelId = normalized.slice(REGISTRY_MODEL_PREFIX.length).trim();
  return modelId || null;
}

export function resolveContentEnrichmentCurrentModel(
  model: string | null | undefined,
  registryModels: ContentEnrichmentModelRegistryEntry[] | null | undefined,
): ContentEnrichmentResolvedCurrentModel | null {
  if (typeof model !== "string" || !model.trim()) {
    return null;
  }
  const normalized = model.trim();
  const registryModelId = parseContentEnrichmentRegistryModelRef(normalized);
  if (!registryModelId) {
    return {
      kind: "base",
      model: normalized,
    };
  }
  const registryModel = registryModels?.find((item) => item.id === registryModelId) ?? null;
  if (!registryModel) {
    return {
      kind: "base",
      model: normalized,
    };
  }
  return {
    kind: "registry",
    model: normalized,
    registry_model_id: registryModelId,
    registry_model: registryModel,
  };
}

export function resolveContentEnrichmentExtractionModel(
  defaultModel: string | null | undefined,
  schemaName: string | null | undefined,
  schemaModels: Record<string, string> | null | undefined,
  registryModels: ContentEnrichmentModelRegistryEntry[] | null | undefined,
): ContentEnrichmentResolvedCurrentModel | null {
  const normalizedSchemaName = typeof schemaName === "string" ? schemaName.trim() : "";
  const normalizedSchemaModels = normalizeContentEnrichmentSchemaModels(schemaModels);
  const scopedModel = normalizedSchemaName ? normalizedSchemaModels[normalizedSchemaName] : null;
  return resolveContentEnrichmentCurrentModel(scopedModel ?? defaultModel, registryModels);
}

export function summarizeContentEnrichmentTrainingMetrics(
  metrics: Record<string, unknown> | null | undefined,
): ContentEnrichmentTrainingMetricsSummary {
  return {
    best_metric: metricNumber(metrics, "best_metric"),
    train_loss: metricNumber(metrics, "train_loss"),
    eval_loss: metricNumber(metrics, "eval_loss"),
    training_duration_seconds: metricNumber(metrics, "training_duration_seconds"),
    artifact_size_bytes: metricNumber(metrics, "artifact_size_bytes"),
    global_step: metricNumber(metrics, "global_step"),
    epochs_completed: metricNumber(metrics, "epochs_completed"),
    train_example_count: metricNumber(metrics, "train_example_count"),
    validation_example_count: metricNumber(metrics, "validation_example_count"),
    validation_accuracy: metricNumber(metrics, "validation_accuracy"),
    validation_exact_match_rate: metricNumber(metrics, "validation_exact_match_rate"),
    validation_field_accuracy: metricNumber(metrics, "validation_field_accuracy"),
    validation_status:
      typeof metrics?.validation_status === "string" ? metrics.validation_status : null,
    validation_error:
      typeof metrics?.validation_error === "string" ? metrics.validation_error : null,
  };
}

export function formatContentEnrichmentMetricNumber(
  value: number | null | undefined,
): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: value < 10 ? 2 : 0,
    maximumFractionDigits: value < 10 ? 3 : 0,
  });
}

export function formatContentEnrichmentMetricPercent(
  value: number | null | undefined,
): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return `${(value * 100).toLocaleString(undefined, {
    minimumFractionDigits: value < 0.1 ? 1 : 0,
    maximumFractionDigits: 1,
  })}%`;
}

export function formatContentEnrichmentMetricDuration(
  seconds: number | null | undefined,
): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) {
    return null;
  }
  if (seconds < 60) {
    return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

export function formatContentEnrichmentMetricSize(bytes: number | null | undefined): string | null {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) {
    return null;
  }
  if (bytes === 0) {
    return "0 B";
  }
  const sizeUnits = ["B", "KB", "MB", "GB", "TB"];
  const unitIndex = Math.floor(Math.log(bytes) / Math.log(1024));
  const unitValue = bytes / Math.pow(1024, unitIndex);
  return `${parseFloat(unitValue.toFixed(1))} ${sizeUnits[unitIndex]}`;
}

export function buildContentEnrichmentPromotionReviewPath(
  targetKind: ContentEnrichmentFineTuneTargetKind,
  targetName: string | null | undefined,
): string {
  const params = new URLSearchParams();
  params.set("stale_enrichment", "true");
  if (targetKind === "extraction" && typeof targetName === "string" && targetName.trim()) {
    params.set("extraction_schema", targetName.trim());
  }
  return `/content?${params.toString()}`;
}

export function summarizeContentEnrichmentPromotionImpact(args: {
  staleFileCount: number | null | undefined;
  newlyStaleFileCount: number | null | undefined;
  targetKind: ContentEnrichmentFineTuneTargetKind;
  targetName?: string | null;
}): ContentEnrichmentPromotionImpactSummary {
  const staleFileCount =
    typeof args.staleFileCount === "number" && Number.isFinite(args.staleFileCount)
      ? Math.max(0, Math.trunc(args.staleFileCount))
      : 0;
  const newlyStaleFileCount =
    typeof args.newlyStaleFileCount === "number" && Number.isFinite(args.newlyStaleFileCount)
      ? Math.max(0, Math.trunc(args.newlyStaleFileCount))
      : 0;
  return {
    stale_count: staleFileCount,
    stale_increase: newlyStaleFileCount,
    review_path: buildContentEnrichmentPromotionReviewPath(
      args.targetKind,
      args.targetName ?? null,
    ),
    target_kind: args.targetKind,
    target_name:
      typeof args.targetName === "string" && args.targetName.trim() ? args.targetName.trim() : null,
  };
}

export function buildContentEnrichmentPromotionRefreshPlan(
  targetKind: ContentEnrichmentFineTuneTargetKind,
  targetName: string | null | undefined,
): ContentEnrichmentPromotionRefreshPlan {
  const filters: AllFilesBatchFilters = { stale_enrichment: true };
  const normalizedTargetName =
    typeof targetName === "string" && targetName.trim() ? targetName.trim() : null;

  if (targetKind === "extraction") {
    if (normalizedTargetName) {
      filters.extraction_schema = normalizedTargetName;
    }
    return { filters };
  }

  return { filters };
}
