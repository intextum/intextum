import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNotify, useTranslate } from "@/lib/app-context";
import { useConfirm } from "@/lib/confirm-context";
import { Bot, ScanSearch, Sparkles } from "lucide-react";
import { EmptyState } from "@/components/page/EmptyState";
import { LoadingState } from "@/components/page/LoadingState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  aiSettingsApi,
  contentEnrichmentCatalogApi,
  contentEnrichmentTrainingApi,
  contentApi,
  type AiSettingEntry,
  type ContentEnrichmentTrainingOverviewResponse,
  type AiSettingsResponse,
} from "@/dataProvider";
import {
  serializeDocumentClassDrafts,
  validateContentEnrichmentDrafts,
} from "@/lib/content-enrichment-admin";
import type { DocumentClassDraft } from "@/lib/content-enrichment-admin";
import {
  buildContentEnrichmentPromotionRefreshPlan,
  type ContentEnrichmentPromotionImpactSummary,
  summarizeContentEnrichmentPromotionImpact,
} from "@/lib/content-enrichment-training";
import { buildEnrichmentOnlyProcessingConfig } from "@/lib/content-processing";
import { invalidateContentQueries, queryKeys } from "@/lib/query-client";
import {
  ContentEnrichmentSection,
  type ContentEnrichmentSectionFocus,
} from "./ai-settings/ContentEnrichmentSection";
import {
  AiSettingField,
  ContentEnrichmentDocumentClassEditor,
  type DocumentClassEditorRouteMode,
} from "./ai-settings/ContentEnrichmentEditors";
import { AiSettingsSectionCard } from "./ai-settings/AiSettingsSectionCard";
import { useContentEnrichmentDrafts } from "./ai-settings/useContentEnrichmentDrafts";

const CHAT_KEYS = [
  "chat_model",
  "chat_system_prompt",
  "chat_tool_prompt",
  "chat_search_limit",
  "chat_document_max_chars",
] as const;
const IMAGE_KEYS = [
  "picture_description_model",
  "picture_description_prompt",
  "picture_description_max_tokens",
  "picture_description_enable_thinking",
] as const;
const CONTENT_ENRICHMENT_KEYS = [
  "document_classification_enabled",
  "document_classification_provider",
  "document_classification_model",
  "document_extraction_enabled",
  "document_extraction_model",
  "document_extraction_llm_model",
  "document_extraction_llm_max_output_tokens",
  "document_extraction_llm_enable_thinking",
  "document_extraction_chat_max_retries",
  "document_extraction_chat_evidence_required",
  "document_extraction_chat_full_text_threshold_chars",
  "document_extraction_max_chars",
] as const;

type SectionKey = "chat" | "image_description" | "content_enrichment";
type FormValue = string | boolean;

type AiSettingsPanelProps = {
  section?: SectionKey;
  focus?: ContentEnrichmentSectionFocus;
  documentClassRouteMode?: DocumentClassEditorRouteMode;
  selectedDocumentClassId?: string;
  onOpenDocumentClass?: (id: string) => void;
  onCreateDocumentClass?: () => void;
  onCloseDocumentClassDetail?: (options?: { replace?: boolean }) => void;
  onDocumentClassRouteLabelChange?: (label: string | null) => void;
};

function itemTranslation(
  translate: (key: string, options?: unknown) => string,
  key: string,
  part: "label" | "description",
  fallback: string,
) {
  const translated = translate(`custom.pages.settings.ai.fields.${key}.${part}`);
  return translated === `custom.pages.settings.ai.fields.${key}.${part}` ? fallback : translated;
}

function toFormValues(items: AiSettingEntry[]): Record<string, FormValue> {
  return Object.fromEntries(
    items.map((item) => {
      if (item.input_type === "boolean") {
        return [item.key, Boolean(item.value)];
      }
      if (item.input_type === "json") {
        return [item.key, JSON.stringify(item.value, null, 2)];
      }
      return [item.key, String(item.value)];
    }),
  );
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

export function AiSettingsPanel({
  section,
  focus,
  documentClassRouteMode,
  selectedDocumentClassId,
  onOpenDocumentClass,
  onCreateDocumentClass,
  onCloseDocumentClassDetail,
  onDocumentClassRouteLabelChange,
}: AiSettingsPanelProps) {
  const translate = useTranslate();
  const notify = useNotify();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<AiSettingEntry[]>([]);
  const [formValues, setFormValues] = useState<Record<string, FormValue>>({});
  const [trainingOverview, setTrainingOverview] =
    useState<ContentEnrichmentTrainingOverviewResponse | null>(null);
  const [creatingTrainingJobKey, setCreatingTrainingJobKey] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [cancelingJobId, setCancelingJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [promotingModelId, setPromotingModelId] = useState<string | null>(null);
  const [archivingModelId, setArchivingModelId] = useState<string | null>(null);
  const [lastPromotionImpact, setLastPromotionImpact] =
    useState<ContentEnrichmentPromotionImpactSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [staleEnrichmentCount, setStaleEnrichmentCount] = useState<number | null>(null);
  const [loadingStaleEnrichmentCount, setLoadingStaleEnrichmentCount] = useState(false);
  const [rerunningStaleEnrichment, setRerunningStaleEnrichment] = useState(false);
  const [lastStaleRerunResult, setLastStaleRerunResult] = useState<{
    queued: number;
    matched: number;
    errors: number;
  } | null>(null);
  const [savingSection, setSavingSection] = useState<SectionKey | null>(null);
  const [resettingSection, setResettingSection] = useState<SectionKey | null>(null);
  const [resettingField, setResettingField] = useState<string | null>(null);
  const [savingDocumentClasses, setSavingDocumentClasses] = useState(false);
  const loadedOnceRef = useRef(false);
  const { documentClassesDraft, applyCatalogDrafts } = useContentEnrichmentDrafts();

  const applyResponse = useCallback((response: AiSettingsResponse) => {
    setItems(response.items);
    setFormValues(toFormValues(response.items));
    setLoadError(null);
  }, []);

  const applyContentEnrichmentCatalog = useCallback(
    (catalog: { document_classes?: unknown }) => {
      applyCatalogDrafts(catalog);
    },
    [applyCatalogDrafts],
  );

  const applyTrainingOverview = useCallback(
    (overview: ContentEnrichmentTrainingOverviewResponse) => {
      setTrainingOverview(overview);
    },
    [],
  );

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [response, catalog, overview] = await Promise.all([
        aiSettingsApi.get(),
        contentEnrichmentCatalogApi.get(),
        contentEnrichmentTrainingApi.getOverview(),
      ]);
      applyResponse(response);
      applyContentEnrichmentCatalog(catalog);
      queryClient.setQueryData(queryKeys.settings.contentEnrichmentCatalog, catalog);
      applyTrainingOverview(overview);
    } catch (error) {
      const message = errorMessage(error, translate("custom.pages.settings.ai.load_failed"));
      setLoadError(message);
      notify(message, { type: "error" });
    } finally {
      setLoading(false);
    }
  }, [
    applyContentEnrichmentCatalog,
    applyResponse,
    applyTrainingOverview,
    notify,
    queryClient,
    translate,
  ]);

  const loadTrainingOverview = useCallback(async () => {
    applyTrainingOverview(await contentEnrichmentTrainingApi.getOverview());
  }, [applyTrainingOverview]);

  const loadStaleEnrichmentCount = useCallback(async (): Promise<number | null> => {
    setLoadingStaleEnrichmentCount(true);
    try {
      const stats = await contentApi.getGlobalStats();
      setStaleEnrichmentCount(stats.stale_enrichment_count);
      return stats.stale_enrichment_count;
    } catch {
      setStaleEnrichmentCount(null);
      return null;
    } finally {
      setLoadingStaleEnrichmentCount(false);
    }
  }, []);

  const hasActiveTrainingJob = trainingOverview?.jobs.some(
    (job) => job.status === "queued" || job.status === "running",
  );
  const trainingOverviewPollQuery = useQuery({
    queryKey: [...queryKeys.settings.ai, "content-enrichment-training-overview"],
    queryFn: contentEnrichmentTrainingApi.getOverview,
    enabled: (!section || section === "content_enrichment") && Boolean(hasActiveTrainingJob),
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (trainingOverviewPollQuery.data) {
      applyTrainingOverview(trainingOverviewPollQuery.data);
    }
  }, [applyTrainingOverview, trainingOverviewPollQuery.data]);

  useEffect(() => {
    if (loadedOnceRef.current) {
      return;
    }
    loadedOnceRef.current = true;
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (section && section !== "content_enrichment") {
      return;
    }
    void loadStaleEnrichmentCount();
  }, [loadStaleEnrichmentCount, section]);

  const itemsByKey = useMemo(() => new Map(items.map((item) => [item.key, item])), [items]);
  const orderedItemsForSection = useCallback(
    (section: SectionKey) => {
      const keys =
        section === "chat"
          ? CHAT_KEYS
          : section === "image_description"
            ? IMAGE_KEYS
            : CONTENT_ENRICHMENT_KEYS;
      return keys
        .map((key) => itemsByKey.get(key))
        .filter((item): item is AiSettingEntry => !!item);
    },
    [itemsByKey],
  );

  const handleFieldChange = (key: string, value: FormValue) => {
    setFormValues((current) => ({
      ...current,
      [key]: value,
    }));
  };

  const buildSectionPayload = (section: SectionKey) => {
    const payload: Record<
      string,
      string | number | boolean | Array<Record<string, unknown>> | Record<string, unknown>
    > = {};
    for (const item of orderedItemsForSection(section)) {
      const rawValue = formValues[item.key];
      if (item.input_type === "boolean") {
        payload[item.key] = Boolean(rawValue);
        continue;
      }
      if (item.input_type === "json") {
        const jsonValue = typeof rawValue === "string" ? rawValue.trim() : "";
        payload[item.key] = jsonValue ? JSON.parse(jsonValue) : {};
        continue;
      }
      const stringValue = typeof rawValue === "string" ? rawValue : "";
      if (item.input_type === "number") {
        const parsed = Number.parseInt(stringValue, 10);
        if (!Number.isFinite(parsed)) {
          throw new Error("invalid_number");
        }
        payload[item.key] = parsed;
        continue;
      }
      payload[item.key] = stringValue;
    }
    return payload;
  };

  const handleSaveSection = async (section: SectionKey) => {
    setSavingSection(section);
    try {
      const payload = buildSectionPayload(section);
      const response = await aiSettingsApi.update(payload);
      applyResponse(response);
      if (section === "content_enrichment") {
        await loadStaleEnrichmentCount();
      }
      notify(translate("custom.pages.settings.ai.save_success"), { type: "success" });
    } catch (error) {
      if (error instanceof Error && error.message === "invalid_number") {
        notify(translate("custom.pages.settings.ai.invalid_number"), { type: "error" });
      } else if (
        error instanceof Error &&
        [
          "class_name_required",
          "class_name_duplicate",
          "schema_name_required",
          "schema_name_duplicate",
          "field_name_required",
          "field_name_duplicate",
          "field_description_required",
        ].includes(error.message)
      ) {
        notify(
          translate(
            `custom.pages.settings.ai.content_enrichment_editor.validation.${error.message}` as const,
          ),
          { type: "error" },
        );
      } else if (error instanceof Error && error.message === "invalid_json") {
        notify(translate("custom.pages.settings.ai.invalid_json"), { type: "error" });
      } else {
        notify(translate("custom.pages.settings.ai.save_failed"), { type: "error" });
      }
    } finally {
      setSavingSection(null);
    }
  };

  const handleResetSection = async (section: SectionKey) => {
    setResettingSection(section);
    try {
      const keys = orderedItemsForSection(section).map((item) => item.key);
      const response = await aiSettingsApi.resetMany(keys);
      applyResponse(response);
      if (section === "content_enrichment") {
        await loadStaleEnrichmentCount();
      }
      notify(translate("custom.pages.settings.ai.reset_success"), { type: "info" });
    } catch {
      notify(translate("custom.pages.settings.ai.reset_failed"), { type: "error" });
    } finally {
      setResettingSection(null);
    }
  };

  const notifyContentEnrichmentValidationError = (error: string) => {
    notify(
      translate(`custom.pages.settings.ai.content_enrichment_editor.validation.${error}` as const),
      { type: "error" },
    );
  };

  const handleSaveDocumentClasses = async (nextClasses: DocumentClassDraft[]) => {
    const validationError = validateContentEnrichmentDrafts(nextClasses);
    if (validationError) {
      notifyContentEnrichmentValidationError(validationError);
      throw new Error(validationError);
    }

    setSavingDocumentClasses(true);
    try {
      const catalog = await contentEnrichmentCatalogApi.replace({
        document_classes: serializeDocumentClassDrafts(nextClasses),
      });
      applyContentEnrichmentCatalog(catalog);
      queryClient.setQueryData(queryKeys.settings.contentEnrichmentCatalog, catalog);
      await loadStaleEnrichmentCount();
      notify(translate("custom.pages.settings.ai.content_enrichment_editor.catalog_save_success"), {
        type: "success",
      });
    } catch (error) {
      if (
        error instanceof Error &&
        [
          "class_name_required",
          "class_name_duplicate",
          "schema_name_required",
          "schema_name_duplicate",
          "field_name_required",
          "field_name_duplicate",
          "field_description_required",
        ].includes(error.message)
      ) {
        throw error;
      }
      notify(translate("custom.pages.settings.ai.content_enrichment_editor.catalog_save_failed"), {
        type: "error",
      });
      throw error;
    } finally {
      setSavingDocumentClasses(false);
    }
  };

  const handleResetField = async (key: string) => {
    setResettingField(key);
    try {
      applyResponse(await aiSettingsApi.reset(key));
      notify(translate("custom.pages.settings.ai.reset_success"), { type: "info" });
    } catch {
      notify(translate("custom.pages.settings.ai.reset_failed"), { type: "error" });
    } finally {
      setResettingField(null);
    }
  };

  const handleRerunStaleEnrichment = async (
    staleCount: number,
    filters: { stale_enrichment: true; extraction_schema?: string } = { stale_enrichment: true },
  ) => {
    if (
      !(await confirm({
        description: translate("custom.content.actions.confirm_process_stale", {
          count: staleCount,
        }),
      }))
    ) {
      return;
    }
    setRerunningStaleEnrichment(true);
    try {
      const result = await contentApi.triggerFilteredBatchProcess(
        filters,
        buildEnrichmentOnlyProcessingConfig(),
      );
      setLastStaleRerunResult({
        queued: result.queued,
        matched: result.matched,
        errors: result.errors,
      });
      if (result.queued > 0) {
        notify(translate("custom.batch_processing_started", { count: result.queued }), {
          type: "success",
        });
        void invalidateContentQueries();
      } else {
        notify(translate("custom.failed_to_start_processing"), { type: "warning" });
      }
      await loadStaleEnrichmentCount();
    } catch {
      notify(translate("custom.failed_to_start_processing"), { type: "error" });
    } finally {
      setRerunningStaleEnrichment(false);
    }
  };

  const handleRerunPromotionImpact = async (impact: ContentEnrichmentPromotionImpactSummary) => {
    const plan = buildContentEnrichmentPromotionRefreshPlan(impact.target_kind, impact.target_name);
    await handleRerunStaleEnrichment(impact.stale_count, {
      stale_enrichment: true,
      ...(plan.filters.extraction_schema
        ? { extraction_schema: plan.filters.extraction_schema }
        : {}),
    });
  };

  const handleCreateTrainingJob = async (targetKind: "classification") => {
    setCreatingTrainingJobKey(targetKind);
    try {
      await contentEnrichmentTrainingApi.createJob({
        target_kind: targetKind,
        training_method: "lora",
      });
      await loadTrainingOverview();
      notify(translate("custom.pages.settings.ai.content_enrichment_training.create_success"), {
        type: "success",
      });
    } catch (error) {
      notify(
        errorMessage(
          error,
          translate("custom.pages.settings.ai.content_enrichment_training.create_failed"),
        ),
        { type: "error" },
      );
    } finally {
      setCreatingTrainingJobKey(null);
    }
  };

  const handlePromoteTrainingModel = async (modelId: string) => {
    setPromotingModelId(modelId);
    try {
      const promotion = await contentEnrichmentTrainingApi.promoteModel(modelId);
      const [response, overview] = await Promise.all([
        aiSettingsApi.get(),
        contentEnrichmentTrainingApi.getOverview(),
      ]);
      applyResponse(response);
      applyTrainingOverview(overview);
      await loadStaleEnrichmentCount();
      const impact = summarizeContentEnrichmentPromotionImpact({
        staleFileCount: promotion.stale_file_count,
        newlyStaleFileCount: promotion.newly_stale_file_count,
        targetKind: promotion.target_kind,
        targetName: promotion.target_name,
      });
      setLastPromotionImpact(impact);
      notify(
        translate("custom.pages.settings.ai.content_enrichment_training.promote_success", {
          count: impact.stale_count,
        }),
        { type: "success" },
      );
    } catch (error) {
      notify(
        errorMessage(
          error,
          translate("custom.pages.settings.ai.content_enrichment_training.promote_failed"),
        ),
        { type: "error" },
      );
    } finally {
      setPromotingModelId(null);
    }
  };

  const handleRetryTrainingJob = async (jobId: string) => {
    setRetryingJobId(jobId);
    try {
      await contentEnrichmentTrainingApi.retryJob(jobId);
      await loadTrainingOverview();
      notify(translate("custom.pages.settings.ai.content_enrichment_training.retry_success"), {
        type: "success",
      });
    } catch (error) {
      notify(
        errorMessage(
          error,
          translate("custom.pages.settings.ai.content_enrichment_training.retry_failed"),
        ),
        { type: "error" },
      );
    } finally {
      setRetryingJobId(null);
    }
  };

  const handleCancelTrainingJob = async (jobId: string) => {
    setCancelingJobId(jobId);
    try {
      await contentEnrichmentTrainingApi.cancelJob(jobId);
      await loadTrainingOverview();
      notify(translate("custom.pages.settings.ai.content_enrichment_training.cancel_success"), {
        type: "success",
      });
    } catch (error) {
      notify(
        errorMessage(
          error,
          translate("custom.pages.settings.ai.content_enrichment_training.cancel_failed"),
        ),
        { type: "error" },
      );
    } finally {
      setCancelingJobId(null);
    }
  };

  const handleDeleteTrainingJob = async (jobId: string) => {
    setDeletingJobId(jobId);
    try {
      await contentEnrichmentTrainingApi.deleteJob(jobId);
      await loadTrainingOverview();
      notify(translate("custom.pages.settings.ai.content_enrichment_training.delete_success"), {
        type: "success",
      });
    } catch (error) {
      notify(
        errorMessage(
          error,
          translate("custom.pages.settings.ai.content_enrichment_training.delete_failed"),
        ),
        { type: "error" },
      );
    } finally {
      setDeletingJobId(null);
    }
  };

  const handleArchiveTrainingModel = async (modelId: string) => {
    setArchivingModelId(modelId);
    try {
      await contentEnrichmentTrainingApi.archiveModel(modelId);
      await loadTrainingOverview();
      notify(translate("custom.pages.settings.ai.content_enrichment_training.archive_success"), {
        type: "success",
      });
    } catch (error) {
      notify(
        errorMessage(
          error,
          translate("custom.pages.settings.ai.content_enrichment_training.archive_failed"),
        ),
        { type: "error" },
      );
    } finally {
      setArchivingModelId(null);
    }
  };

  const renderDocumentClassEditor = (item: AiSettingEntry) => (
    <ContentEnrichmentDocumentClassEditor
      item={item}
      translate={translate}
      itemTranslation={itemTranslation}
      resettingField={resettingField}
      onResetField={(key) => {
        void handleResetField(key);
      }}
      documentClassesDraft={documentClassesDraft}
      savingDocumentClasses={savingDocumentClasses}
      onSaveDocumentClasses={handleSaveDocumentClasses}
      routeMode={documentClassRouteMode}
      selectedClassId={selectedDocumentClassId}
      onOpenDocumentClass={onOpenDocumentClass}
      onCreateDocumentClass={onCreateDocumentClass}
      onCloseDocumentClassDetail={onCloseDocumentClassDetail}
      onDocumentClassRouteLabelChange={onDocumentClassRouteLabelChange}
    />
  );

  const renderField = (item: AiSettingEntry, options?: { framed?: boolean }) => (
    <AiSettingField
      item={item}
      value={formValues[item.key]}
      framed={options?.framed}
      translate={translate}
      itemTranslation={itemTranslation}
      resettingField={resettingField}
      onResetField={(key) => {
        void handleResetField(key);
      }}
      onFieldChange={handleFieldChange}
    />
  );

  const isSectionDirty = useCallback(
    (section: SectionKey) => {
      const sectionItems = orderedItemsForSection(section);
      const savedValues = toFormValues(sectionItems);
      const currentValues = Object.fromEntries(
        sectionItems.map((item) => [item.key, formValues[item.key]]),
      );
      const hasFieldChanges = JSON.stringify(currentValues) !== JSON.stringify(savedValues);

      if (section !== "content_enrichment") {
        return hasFieldChanges;
      }
      return hasFieldChanges;
    },
    [formValues, orderedItemsForSection],
  );

  const renderSection = (
    section: SectionKey,
    sectionItems: AiSettingEntry[],
    title: string,
    description: string,
    icon: "chat" | "image" | "content_enrichment",
  ) => {
    const isSaving = savingSection === section;
    const isResetting = resettingSection === section;
    const isDirty = isSectionDirty(section);
    const hideContentEnrichmentChrome =
      section === "content_enrichment" && (focus === "classes" || focus === "training");
    const iconNode =
      icon === "chat" ? (
        <Bot className="h-5 w-5 text-primary" />
      ) : icon === "content_enrichment" ? (
        <Sparkles className="h-5 w-5 text-primary" />
      ) : (
        <ScanSearch className="h-5 w-5 text-primary" />
      );

    return (
      <AiSettingsSectionCard
        title={title}
        description={description}
        icon={iconNode}
        isDirty={isDirty}
        isSaving={isSaving}
        isResetting={isResetting}
        saveLabel={translate("custom.pages.settings.ai.actions.save")}
        savingLabel={translate("custom.pages.settings.ai.actions.saving")}
        resetLabel={translate("custom.pages.settings.ai.actions.reset_section")}
        resettingLabel={translate("custom.pages.settings.ai.actions.resetting")}
        onSave={() => {
          void handleSaveSection(section);
        }}
        onReset={() => {
          void handleResetSection(section);
        }}
        showHeader={!hideContentEnrichmentChrome}
        showActions={!hideContentEnrichmentChrome}
      >
        {section === "content_enrichment" ? (
          <ContentEnrichmentSection
            focus={focus}
            sectionItems={sectionItems}
            translate={translate}
            formValues={formValues}
            documentClassesDraft={documentClassesDraft}
            trainingOverview={trainingOverview}
            creatingTrainingJobKey={creatingTrainingJobKey}
            retryingJobId={retryingJobId}
            cancelingJobId={cancelingJobId}
            deletingJobId={deletingJobId}
            promotingModelId={promotingModelId}
            archivingModelId={archivingModelId}
            lastPromotionImpact={lastPromotionImpact}
            staleEnrichmentCount={staleEnrichmentCount}
            loadingStaleEnrichmentCount={loadingStaleEnrichmentCount}
            rerunningStaleEnrichment={rerunningStaleEnrichment}
            lastStaleRerunResult={lastStaleRerunResult}
            processingSettingsDirty={isSectionDirty("content_enrichment")}
            renderField={renderField}
            renderDocumentClassEditor={renderDocumentClassEditor}
            onCreateTrainingJob={(targetKind) => {
              void handleCreateTrainingJob(targetKind);
            }}
            onPromoteTrainingModel={(modelId) => {
              void handlePromoteTrainingModel(modelId);
            }}
            onRetryTrainingJob={(jobId) => {
              void handleRetryTrainingJob(jobId);
            }}
            onCancelTrainingJob={(jobId) => {
              void handleCancelTrainingJob(jobId);
            }}
            onDeleteTrainingJob={(jobId) => {
              void handleDeleteTrainingJob(jobId);
            }}
            onArchiveTrainingModel={(modelId) => {
              void handleArchiveTrainingModel(modelId);
            }}
            onRerunPromotionImpact={(impact) => {
              void handleRerunPromotionImpact(impact);
            }}
            onRerunStaleEnrichment={(staleCount) => {
              void handleRerunStaleEnrichment(staleCount);
            }}
          />
        ) : (
          <div className="space-y-2">
            {sectionItems.map((item) => renderField(item, { framed: false }))}
          </div>
        )}
      </AiSettingsSectionCard>
    );
  };

  const chatItems = orderedItemsForSection("chat");
  const imageDescriptionItems = orderedItemsForSection("image_description");
  const contentEnrichmentItems = orderedItemsForSection("content_enrichment");
  const sections = [
    ...(chatItems.length > 0
      ? [
          {
            key: "chat" as const,
            title: translate("custom.pages.settings.ai.chat.title"),
            description: translate("custom.pages.settings.ai.chat.description"),
            icon: "chat" as const,
            items: chatItems,
          },
        ]
      : []),
    ...(imageDescriptionItems.length > 0
      ? [
          {
            key: "image_description" as const,
            title: translate("custom.pages.settings.ai.image_description.title"),
            description: translate("custom.pages.settings.ai.image_description.description"),
            icon: "image" as const,
            items: imageDescriptionItems,
          },
        ]
      : []),
    ...(contentEnrichmentItems.length > 0
      ? [
          {
            key: "content_enrichment" as const,
            title: translate("custom.pages.settings.ai.content_enrichment.title"),
            description: translate("custom.pages.settings.ai.content_enrichment.description"),
            icon: "content_enrichment" as const,
            items: contentEnrichmentItems,
          },
        ]
      : []),
  ];
  const visibleSections = section ? sections.filter((item) => item.key === section) : sections;

  if (loading) {
    return <LoadingState rows={3} />;
  }

  if (loadError && items.length === 0) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{translate("custom.pages.settings.ai.error_title")}</AlertTitle>
        <AlertDescription className="space-y-4">
          <p>{loadError}</p>
          <Button
            variant="outline"
            onClick={() => {
              void loadSettings();
            }}
          >
            {translate("custom.refresh")}
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (items.length === 0 || visibleSections.length === 0) {
    return (
      <EmptyState
        icon={Bot}
        title={translate("custom.pages.settings.ai.empty_title")}
        description={translate("custom.pages.settings.ai.empty_description")}
      />
    );
  }

  if (visibleSections.length === 1) {
    const [activeSection] = visibleSections;
    return renderSection(
      activeSection.key,
      activeSection.items,
      activeSection.title,
      activeSection.description,
      activeSection.icon,
    );
  }

  return (
    <div className="space-y-6">
      {visibleSections.map((activeSection) => (
        <div key={activeSection.key}>
          {renderSection(
            activeSection.key,
            activeSection.items,
            activeSection.title,
            activeSection.description,
            activeSection.icon,
          )}
        </div>
      ))}
    </div>
  );
}
