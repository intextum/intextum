import type {
  AiSettingEntry,
  ContentEnrichmentFineTuneJobStatus,
  ContentEnrichmentFineTuneTargetKind,
  ContentEnrichmentModelRegistryEntry,
  ContentEnrichmentModelRegistryStatus,
} from "@/dataProvider";
import { resolveContentEnrichmentCurrentModel } from "@/lib/content-enrichment-training";

export function contentEnrichmentTrainingStatusLabel(
  status: ContentEnrichmentFineTuneJobStatus | ContentEnrichmentModelRegistryStatus,
  translate: (key: string, options?: unknown) => string,
) {
  switch (status) {
    case "queued":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_queued");
    case "running":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_running");
    case "completed":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_completed");
    case "failed":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_failed");
    case "training":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_training");
    case "ready":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_ready");
    case "archived":
      return translate("custom.pages.settings.ai.content_enrichment_training.status_archived");
  }
}

export function contentEnrichmentTrainingStatusVariant(
  status: ContentEnrichmentFineTuneJobStatus | ContentEnrichmentModelRegistryStatus,
): "default" | "secondary" | "outline" {
  switch (status) {
    case "completed":
    case "ready":
      return "default";
    case "failed":
    case "archived":
      return "outline";
    default:
      return "secondary";
  }
}

export function contentEnrichmentTrainingTargetLabel(
  targetKind: ContentEnrichmentFineTuneTargetKind,
  targetName: string | null | undefined,
  translate: (key: string, options?: unknown) => string,
) {
  if (targetKind === "classification") {
    return translate("custom.pages.settings.ai.content_enrichment_training.target_classification");
  }
  return targetName || targetKind;
}

export function contentEnrichmentCurrentModelLabel(
  modelValue: string,
  registryModels: ContentEnrichmentModelRegistryEntry[] | null | undefined,
  translate: (key: string, options?: unknown) => string,
) {
  const normalizedModel = modelValue.trim() || " - ";
  const resolved = resolveContentEnrichmentCurrentModel(modelValue, registryModels);
  if (resolved?.kind === "registry") {
    return translate(
      "custom.pages.settings.ai.content_enrichment_training.current_registry_model",
      {
        modelId: resolved.registry_model_id,
        baseModel: resolved.registry_model.base_model,
      },
    );
  }
  return translate("custom.pages.settings.ai.content_enrichment_training.current_model", {
    model: normalizedModel,
  });
}

export function buildContentEnrichmentItemMap(sectionItems: AiSettingEntry[]) {
  return new Map(sectionItems.map((item) => [item.key, item] as const));
}
