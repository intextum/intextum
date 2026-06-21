import { useState, type ReactNode } from "react";
import { ChevronDown, ScanSearch, Sparkles, Tags } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { AiSettingEntry, ContentEnrichmentTrainingOverviewResponse } from "@/dataProvider";
import type { DocumentClassDraft } from "@/lib/content-enrichment-admin";
import type { ContentEnrichmentPromotionImpactSummary } from "@/lib/content-enrichment-training";

import { buildContentEnrichmentItemMap } from "./content-enrichment";
import { ContentEnrichmentStatusBar } from "./ContentEnrichmentStatusBar";
import { ContentEnrichmentTrainingPipeline } from "./ContentEnrichmentTrainingPipeline";

type FormValue = string | boolean;

export type ContentEnrichmentSectionFocus = "settings" | "classes" | "training" | undefined;

type ContentEnrichmentSectionProps = {
  sectionItems: AiSettingEntry[];
  translate: (key: string, options?: unknown) => string;
  formValues: Record<string, FormValue>;
  documentClassesDraft: DocumentClassDraft[];
  trainingOverview: ContentEnrichmentTrainingOverviewResponse | null;
  creatingTrainingJobKey: string | null;
  retryingJobId: string | null;
  cancelingJobId: string | null;
  deletingJobId: string | null;
  promotingModelId: string | null;
  archivingModelId: string | null;
  lastPromotionImpact: ContentEnrichmentPromotionImpactSummary | null;
  staleEnrichmentCount: number | null;
  loadingStaleEnrichmentCount: boolean;
  rerunningStaleEnrichment: boolean;
  lastStaleRerunResult: { queued: number; matched: number; errors: number } | null;
  processingSettingsDirty: boolean;
  renderField: (item: AiSettingEntry, options?: { framed?: boolean }) => ReactNode;
  renderDocumentClassEditor: (item: AiSettingEntry) => ReactNode;
  onCreateTrainingJob: (targetKind: "classification") => void;
  onPromoteTrainingModel: (modelId: string) => void;
  onRetryTrainingJob: (jobId: string) => void;
  onCancelTrainingJob: (jobId: string) => void;
  onDeleteTrainingJob: (jobId: string) => void;
  onArchiveTrainingModel: (modelId: string) => void;
  onRerunPromotionImpact: (impact: ContentEnrichmentPromotionImpactSummary) => void;
  onRerunStaleEnrichment: (staleCount: number) => void;
  focus?: ContentEnrichmentSectionFocus;
};

export function ContentEnrichmentSection({
  sectionItems,
  translate,
  formValues,
  documentClassesDraft,
  trainingOverview,
  creatingTrainingJobKey,
  retryingJobId,
  cancelingJobId,
  deletingJobId,
  promotingModelId,
  archivingModelId,
  lastPromotionImpact,
  staleEnrichmentCount,
  loadingStaleEnrichmentCount,
  rerunningStaleEnrichment,
  lastStaleRerunResult,
  processingSettingsDirty,
  renderField,
  renderDocumentClassEditor,
  onCreateTrainingJob,
  onPromoteTrainingModel,
  onRetryTrainingJob,
  onCancelTrainingJob,
  onDeleteTrainingJob,
  onArchiveTrainingModel,
  onRerunPromotionImpact,
  onRerunStaleEnrichment,
  focus,
}: ContentEnrichmentSectionProps) {
  const itemMap = buildContentEnrichmentItemMap(sectionItems);
  const classificationEnabledItem = itemMap.get("document_classification_enabled");
  const classificationModelItem = itemMap.get("document_classification_model");
  const extractionEnabledItem = itemMap.get("document_extraction_enabled");
  const extractionModelItem = itemMap.get("document_extraction_model");
  const extractionLlmModelItem = itemMap.get("document_extraction_llm_model");
  const extractionLlmTokenLimitItem = itemMap.get("document_extraction_llm_max_output_tokens");
  const extractionLlmEnableThinkingItem = itemMap.get("document_extraction_llm_enable_thinking");
  const extractionMaxCharsItem = itemMap.get("document_extraction_max_chars");
  const chatMaxRetriesItem = itemMap.get("document_extraction_chat_max_retries");
  const chatEvidenceRequiredItem = itemMap.get("document_extraction_chat_evidence_required");
  const chatFullTextThresholdItem = itemMap.get(
    "document_extraction_chat_full_text_threshold_chars",
  );
  const classificationEnabled = Boolean(formValues.document_classification_enabled);
  const extractionEnabled = Boolean(formValues.document_extraction_enabled);
  const classificationProcessingItems = [
    classificationEnabledItem,
    classificationEnabled ? classificationModelItem : null,
  ].filter((item): item is AiSettingEntry => Boolean(item));
  const extractionProcessingItems = [
    extractionEnabledItem,
    extractionEnabled ? extractionModelItem : null,
    extractionEnabled ? extractionLlmModelItem : null,
    extractionEnabled ? extractionLlmTokenLimitItem : null,
    extractionEnabled ? extractionLlmEnableThinkingItem : null,
    extractionEnabled ? chatMaxRetriesItem : null,
    extractionEnabled ? chatEvidenceRequiredItem : null,
    extractionEnabled ? chatFullTextThresholdItem : null,
    extractionEnabled ? extractionMaxCharsItem : null,
  ].filter((item): item is AiSettingEntry => Boolean(item));
  const classificationOverridden = classificationProcessingItems.some((item) => item.overridden);
  const extractionOverridden = extractionProcessingItems.some((item) => item.overridden);
  const hasProcessingSettings =
    classificationProcessingItems.length > 0 || extractionProcessingItems.length > 0;
  const [classificationGroupManuallyOpen, setClassificationGroupManuallyOpen] =
    useState(classificationOverridden);
  const [extractionGroupManuallyOpen, setExtractionGroupManuallyOpen] =
    useState(extractionOverridden);
  const classificationGroupOpen =
    (processingSettingsDirty && classificationOverridden) || classificationGroupManuallyOpen;
  const extractionGroupOpen =
    (processingSettingsDirty && extractionOverridden) || extractionGroupManuallyOpen;

  const renderProcessingGroup = (params: {
    items: AiSettingEntry[];
    titleKey: string;
    Icon: LucideIcon;
    open: boolean;
    setOpen: (open: boolean) => void;
    showDirtyBadge: boolean;
  }) => {
    if (params.items.length === 0) return null;
    return (
      <Collapsible open={params.open} onOpenChange={params.setOpen}>
        <div className="overflow-hidden rounded-lg border bg-card">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            >
              <span className="flex min-w-0 items-center gap-2">
                <params.Icon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">{translate(params.titleKey)}</span>
              </span>
              <span className="flex items-center gap-2">
                {params.showDirtyBadge ? (
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                    {translate(
                      "custom.pages.settings.ai.content_enrichment_editor.processing_settings_dirty",
                    )}
                  </span>
                ) : null}
                <ChevronDown
                  className={`h-4 w-4 text-muted-foreground transition-transform ${
                    params.open ? "rotate-180" : ""
                  }`}
                />
              </span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="divide-y border-t">
              {params.items.map((item) => (
                <div key={item.key} className="px-4">
                  {renderField(item, { framed: false })}
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    );
  };

  const processingSettingsBlock = hasProcessingSettings ? (
    <div className="space-y-3">
      {renderProcessingGroup({
        items: classificationProcessingItems,
        titleKey: "custom.pages.settings.ai.content_enrichment.classification_settings_title",
        Icon: Tags,
        open: classificationGroupOpen,
        setOpen: setClassificationGroupManuallyOpen,
        showDirtyBadge: processingSettingsDirty && classificationOverridden,
      })}
      {renderProcessingGroup({
        items: extractionProcessingItems,
        titleKey: "custom.pages.settings.ai.content_enrichment.extraction_settings_title",
        Icon: ScanSearch,
        open: extractionGroupOpen,
        setOpen: setExtractionGroupManuallyOpen,
        showDirtyBadge: processingSettingsDirty && extractionOverridden,
      })}
    </div>
  ) : null;

  const classificationBaseModel =
    typeof formValues.document_classification_model === "string"
      ? formValues.document_classification_model
      : "";
  const jobs = trainingOverview?.jobs ?? [];
  const models = trainingOverview?.models ?? [];
  const currentExamples = trainingOverview?.current_examples;

  const statusBlock = (
    <ContentEnrichmentStatusBar
      translate={translate}
      staleEnrichmentCount={staleEnrichmentCount}
      loadingStaleEnrichmentCount={loadingStaleEnrichmentCount}
      rerunningStaleEnrichment={rerunningStaleEnrichment}
      lastStaleRerunResult={lastStaleRerunResult}
      onRerunStaleEnrichment={onRerunStaleEnrichment}
    />
  );

  const documentClassEditorBlock = renderDocumentClassEditor({
    key: "document_classes",
    section: "content_enrichment",
    label: "Document Classes",
    description:
      "Admin-defined document classes. Each class can optionally define extraction fields.",
    input_type: "json",
    value: [],
    default_value: [],
    overridden: documentClassesDraft.length > 0,
  });
  const trainingBlock = (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-start gap-3 border-b px-4 py-3">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0 space-y-1">
          <h3 className="text-sm font-medium leading-none">
            {translate("custom.pages.settings.ai.content_enrichment_training.title")}
          </h3>
          <p className="text-xs text-muted-foreground">
            {translate("custom.pages.settings.ai.content_enrichment_training.description")}
          </p>
        </div>
      </div>

      <div className="px-4 py-4">
        <ContentEnrichmentTrainingPipeline
          translate={translate}
          targetKind="classification"
          baseModel={classificationBaseModel}
          availableTargetCount={documentClassesDraft.length}
          currentReviewedExampleCount={currentExamples?.classification}
          models={models}
          jobs={jobs}
          creatingTrainingJobKey={creatingTrainingJobKey}
          retryingJobId={retryingJobId}
          cancelingJobId={cancelingJobId}
          deletingJobId={deletingJobId}
          promotingModelId={promotingModelId}
          archivingModelId={archivingModelId}
          rerunningStaleEnrichment={rerunningStaleEnrichment}
          lastPromotionImpact={lastPromotionImpact}
          onCreateTrainingJob={onCreateTrainingJob}
          onRetryTrainingJob={onRetryTrainingJob}
          onCancelTrainingJob={onCancelTrainingJob}
          onDeleteTrainingJob={onDeleteTrainingJob}
          onPromoteTrainingModel={onPromoteTrainingModel}
          onArchiveTrainingModel={onArchiveTrainingModel}
          onRerunPromotionImpact={onRerunPromotionImpact}
        />
      </div>
    </div>
  );

  if (focus === "settings") {
    return <div className="space-y-6">{processingSettingsBlock}</div>;
  }

  if (focus === "classes") {
    return (
      <div className="space-y-6">
        {statusBlock}
        {documentClassEditorBlock}
      </div>
    );
  }

  if (focus === "training") {
    return <div className="space-y-6">{trainingBlock}</div>;
  }

  return (
    <div className="space-y-6">
      {processingSettingsBlock}
      {trainingBlock}
    </div>
  );
}
