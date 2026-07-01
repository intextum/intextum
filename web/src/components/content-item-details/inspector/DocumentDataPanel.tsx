import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Info,
  Pencil,
  RefreshCw,
  RotateCcw,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Toggle } from "@/components/ui/toggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  contentEnrichmentCatalogApi,
  type ContentClassificationDismissReason,
  type ContentEnrichmentCatalogDocumentClass,
  type ContentItemInfo,
  type ContentReviewSubmitPayload,
} from "@/dataProvider";
import { useNotify, useTranslate } from "@/lib/app-context";
import {
  buildContentReviewSubmitPayload,
  getContentEnrichmentReviewStatus,
  getContentReviewState,
  getDocumentClassificationLabel,
  hasStaleContentEnrichment,
  isObjectRecord,
} from "@/lib/content-enrichment";
import { mergeExtractionFieldsMeta } from "@/lib/document-data-values";
import { queryKeys } from "@/lib/query-client";
import { reportClientError } from "@/lib/report-client-error";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./EvidenceChip";
import { DocumentDataFieldRow } from "./DocumentDataFieldRow";
import {
  allDocRefs,
  documentClassFromPayload,
  fieldBucket,
  formatConfidence,
  normalizeLookup,
  numericConfidence,
  rankedClassificationCandidates,
  schemaFieldsMeta,
  schemaInitialData,
  stringifyDraft,
} from "./document-data-panel-utils";

interface DocumentDataPanelProps {
  file: ContentItemInfo;
  savingEnrichment: boolean;
  onSubmitReview?: (payload: ContentReviewSubmitPayload) => Promise<unknown>;
  onVerifyClass?: (classificationLabel: string) => Promise<unknown>;
  onNavigateToEvidence?: (docRefs: string[], label: string) => void;
  onRerunEnrichment?: () => void;
  footerSlot?: HTMLElement | null;
}

type ReviewState = "reviewed" | "needs_review" | "stale" | "none";

const stateBadgeClass = (state: ReviewState): string => {
  switch (state) {
    case "reviewed":
      return "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800/40 dark:bg-emerald-950/30 dark:text-emerald-200";
    case "needs_review":
      return "border-amber-300/60 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-200";
    case "stale":
      return "border-orange-300/60 bg-orange-50 text-orange-900 dark:border-orange-700/60 dark:bg-orange-950/30 dark:text-orange-200";
    default:
      return "text-muted-foreground";
  }
};

const StatePill = ({ state, label }: { state: ReviewState; label: string }) => (
  <Badge
    variant="outline"
    className={cn("h-6 gap-1 rounded-full px-2 font-medium", stateBadgeClass(state))}
  >
    {state === "reviewed" ? <CheckCircle2 className="h-3 w-3" /> : null}
    {state === "needs_review" ? <AlertCircle className="h-3 w-3" /> : null}
    {state === "stale" ? <Clock className="h-3 w-3" /> : null}
    {label}
  </Badge>
);

const textValue = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value.trim() : null;

export const DocumentDataPanel = ({
  file,
  savingEnrichment,
  onSubmitReview,
  onVerifyClass,
  onNavigateToEvidence,
  onRerunEnrichment,
  footerSlot,
}: DocumentDataPanelProps) => {
  const translate = useTranslate();
  const notify = useNotify();
  const classification = file.document_classification;
  const extraction = file.document_extraction;
  const systemClassification = classification?.system;
  const systemExtraction = extraction?.system;
  const supportsReview = file.capabilities?.supports_review ?? false;
  // Review edits target app-owned enrichment metadata, not the source file, so
  // an immutable source (read-only connector) must not disable them.
  const canEdit = Boolean(onSubmitReview && supportsReview);
  const canVerifyClass = Boolean(onVerifyClass && supportsReview);
  const stale = hasStaleContentEnrichment(
    file.document_enrichment?.classification_lifecycle,
    file.document_enrichment?.extraction_lifecycle,
  );
  const reviewState = getContentReviewState(file);
  const reviewStatus = getContentEnrichmentReviewStatus(classification, extraction);
  const baseClassificationLabel = getDocumentClassificationLabel(classification);
  const systemExtractionClass = documentClassFromPayload(systemExtraction);
  const extractionClassMismatch = Boolean(
    baseClassificationLabel &&
    systemExtractionClass &&
    normalizeLookup(baseClassificationLabel) !== normalizeLookup(systemExtractionClass),
  );
  const baseExtractionData =
    !extractionClassMismatch && isObjectRecord(extraction?.data)
      ? (extraction.data as Record<string, unknown>)
      : null;
  const fieldsMeta =
    !extractionClassMismatch && isObjectRecord(extraction?.fields) ? extraction.fields : null;
  const summary =
    !extractionClassMismatch && isObjectRecord(extraction?.summary) ? extraction.summary : null;
  const aiData = isObjectRecord(systemExtraction?.data) ? systemExtraction.data : null;
  const aiLabel = getDocumentClassificationLabel(systemClassification);
  const hasCorrectedExtraction = extraction?.review_status === "corrected";
  const aiExtractionDiffers = Boolean(
    aiData &&
    (!baseExtractionData ||
      stringifyDraft(null, aiData) !== stringifyDraft(null, baseExtractionData)),
  );
  const evidenceDocRefs = allDocRefs(classification?.evidence);
  const classificationConfidence =
    numericConfidence(classification?.confidence) ??
    numericConfidence(classification?.score) ??
    numericConfidence(classification?.probability);
  const fieldsWithoutEvidence: string[] = useMemo(
    () =>
      Array.isArray(summary?.fields_without_evidence)
        ? (summary.fields_without_evidence as unknown[]).filter(
            (item): item is string => typeof item === "string",
          )
        : [],
    [summary],
  );
  const baseDraftKey = useMemo(
    () => stringifyDraft(baseClassificationLabel, baseExtractionData),
    [baseClassificationLabel, baseExtractionData],
  );
  const [draftState, setDraftState] = useState<{
    baseKey: string;
    classificationLabel: string | null;
    extractionData: Record<string, unknown> | null;
  }>(() => ({
    baseKey: baseDraftKey,
    classificationLabel: baseClassificationLabel,
    extractionData: baseExtractionData,
  }));
  const activeDraft =
    draftState.baseKey === baseDraftKey
      ? draftState
      : {
          baseKey: baseDraftKey,
          classificationLabel: baseClassificationLabel,
          extractionData: baseExtractionData,
        };
  const classificationDraft = activeDraft.classificationLabel;
  const extractionDraft = activeDraft.extractionData;
  const [pickerOpen, setPickerOpen] = useState(false);
  const [showOnlyAttention, setShowOnlyAttention] = useState(false);
  const [resetClassPopoverOpen, setResetClassPopoverOpen] = useState(false);
  const catalogQuery = useQuery({
    queryKey: queryKeys.settings.contentEnrichmentCatalog,
    queryFn: contentEnrichmentCatalogApi.get,
    enabled:
      canEdit || canVerifyClass || Boolean(baseClassificationLabel || extraction?.schema_name),
  });
  const catalogClasses: ContentEnrichmentCatalogDocumentClass[] = useMemo(
    () => catalogQuery.data?.document_classes ?? [],
    [catalogQuery.data?.document_classes],
  );
  const catalogLoading = catalogQuery.isLoading || catalogQuery.isFetching;
  const classificationCandidates = rankedClassificationCandidates(
    systemClassification ?? classification,
  );
  const processingConfig = file.last_processing_config;
  const forcedDocumentClassLabel = isObjectRecord(processingConfig)
    ? textValue(processingConfig.forced_document_class_label)
    : null;
  const forcedExtractionPending = Boolean(
    (file.status === "QUEUED" || file.status === "PROCESSING" || file.status === "RETRYING") &&
    isObjectRecord(processingConfig) &&
    (processingConfig.forced_document_class_id || processingConfig.forced_document_class_label),
  );
  const canResetExtractionToAi = Boolean(
    canEdit &&
    hasCorrectedExtraction &&
    aiData &&
    aiExtractionDiffers &&
    !stale &&
    !forcedExtractionPending &&
    !extractionClassMismatch,
  );

  const currentDraftKey = useMemo(
    () => stringifyDraft(classificationDraft, extractionDraft),
    [classificationDraft, extractionDraft],
  );
  const dirty = baseDraftKey !== currentDraftKey;
  const selectedSchema = useMemo(() => {
    const normalizedClass = normalizeLookup(classificationDraft);
    const normalizedSchema = normalizeLookup(extraction?.schema_name);
    if (normalizedClass) {
      const schema =
        catalogClasses.find(
          (entry) =>
            normalizeLookup(entry.name) === normalizedClass ||
            normalizeLookup(entry.id) === normalizedClass,
        )?.extraction_schema ?? null;
      if (schema) return schema;
    }
    if (!normalizedSchema) return null;
    return (
      catalogClasses.find(
        (entry) => normalizeLookup(entry.extraction_schema?.name) === normalizedSchema,
      )?.extraction_schema ?? null
    );
  }, [catalogClasses, classificationDraft, extraction?.schema_name]);
  const fallbackExtractionData = useMemo(() => schemaInitialData(selectedSchema), [selectedSchema]);
  const fallbackFieldsMeta = useMemo(() => schemaFieldsMeta(selectedSchema), [selectedSchema]);
  const displayExtractionData = useMemo(() => {
    if (forcedExtractionPending || extractionClassMismatch) return null;
    const current = extractionDraft ?? baseExtractionData;
    if (!fallbackExtractionData) return current;
    return {
      ...fallbackExtractionData,
      ...(current ?? {}),
    };
  }, [
    baseExtractionData,
    extractionClassMismatch,
    extractionDraft,
    fallbackExtractionData,
    forcedExtractionPending,
  ]);
  const displayFieldsMeta = useMemo(() => {
    return mergeExtractionFieldsMeta(fallbackFieldsMeta, fieldsMeta);
  }, [fallbackFieldsMeta, fieldsMeta]);
  const payload = buildContentReviewSubmitPayload({
    classificationLabel: classificationDraft,
    extractionData: extractionDraft ?? displayExtractionData,
    includeClassification: Boolean(classificationDraft),
    includeExtraction: Boolean(baseExtractionData || extractionDraft || displayExtractionData),
  });
  const entries = useMemo(
    () => (displayExtractionData ? Object.entries(displayExtractionData) : []),
    [displayExtractionData],
  );
  const hasClassificationSurface = Boolean(supportsReview || baseClassificationLabel);
  const hasExtractionSurface = Boolean(
    baseExtractionData || selectedSchema || forcedExtractionPending,
  );
  const hasReviewableData = Boolean(hasClassificationSurface || hasExtractionSurface);
  const displayedReviewState: ReviewState =
    reviewState === "none" && hasReviewableData ? "needs_review" : (reviewState as ReviewState);
  const canConfirm = Boolean(
    payload &&
    !stale &&
    !forcedExtractionPending &&
    !extractionClassMismatch &&
    (dirty || displayedReviewState === "needs_review"),
  );
  const confirmLabel = dirty
    ? translate("custom.content.details.confirm_changes")
    : translate("custom.content.details.confirm_ai_result");
  const forcedExtractionClassLabel =
    forcedDocumentClassLabel ?? classificationDraft ?? baseClassificationLabel ?? "";

  const stateLabel =
    displayedReviewState === "reviewed"
      ? reviewStatus === "corrected"
        ? translate("custom.content.details.review_corrected")
        : translate("custom.content.details.review_confirmed")
      : displayedReviewState === "needs_review"
        ? translate("custom.content.details.needs_review")
        : displayedReviewState === "stale"
          ? translate("custom.content.details.stale_refresh_short")
          : translate("custom.content.details.no_reviewable_data");

  const setClassificationDraft = (classificationLabel: string | null) => {
    setDraftState((current) => ({
      baseKey: baseDraftKey,
      classificationLabel,
      extractionData:
        current.baseKey === baseDraftKey ? current.extractionData : baseExtractionData,
    }));
  };

  const setExtractionDraft = (extractionData: Record<string, unknown> | null) => {
    setDraftState((current) => ({
      baseKey: baseDraftKey,
      classificationLabel:
        current.baseKey === baseDraftKey ? current.classificationLabel : baseClassificationLabel,
      extractionData,
    }));
  };

  const verifyClass = async (classificationLabel: string) => {
    if (!onVerifyClass || !classificationLabel.trim()) return;
    const normalizedLabel = classificationLabel.trim();
    setPickerOpen(false);
    setDraftState({
      baseKey: baseDraftKey,
      classificationLabel: normalizedLabel,
      extractionData: null,
    });
    try {
      await onVerifyClass(normalizedLabel);
      notify("custom.content.details.class_change_saved", { type: "info" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:verify-class" });
      notify("custom.content.details.class_change_failed", { type: "error" });
    }
  };

  const updateExtractionField = (key: string, value: unknown) => {
    setDraftState((current) => ({
      baseKey: baseDraftKey,
      classificationLabel:
        current.baseKey === baseDraftKey ? current.classificationLabel : baseClassificationLabel,
      extractionData: {
        ...((current.baseKey === baseDraftKey ? current.extractionData : baseExtractionData) ??
          fallbackExtractionData ??
          {}),
        [key]: value,
      },
    }));
  };

  const discardChanges = () => {
    setClassificationDraft(baseClassificationLabel);
    setExtractionDraft(baseExtractionData);
  };

  const resetExtractionToAi = async () => {
    if (!onSubmitReview || !aiData || stale) return;
    try {
      await onSubmitReview({ extraction_data: aiData });
      notify("custom.content.details.extraction_reset_to_ai_saved", { type: "success" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:reset-extraction" });
      notify("custom.content.details.review_save_failed", { type: "error" });
    }
  };

  const confirmContent = async () => {
    if (!onSubmitReview || !payload || stale) return;
    try {
      await onSubmitReview(payload);
      notify("custom.content.details.review_saved", { type: "success" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:confirm-review" });
      notify("custom.content.details.review_save_failed", { type: "error" });
    }
  };

  const dismissContent = async (reason: ContentClassificationDismissReason) => {
    if (!onSubmitReview) return;
    try {
      await onSubmitReview({
        classification_dismissed: true,
        classification_dismiss_reason: reason,
      });
      notify("custom.content.content_list.review_session_dismiss_success", { type: "success" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:dismiss-review" });
      notify("custom.content.content_list.review_session_dismiss_failed", { type: "error" });
    }
  };

  const dismissExtraction = async (reason: "not_extractable" | "schema_mismatch") => {
    if (!onSubmitReview) return;
    try {
      await onSubmitReview({
        extraction_dismissed: true,
        extraction_dismiss_reason: reason,
      });
      notify("custom.content.content_list.review_session_dismiss_success", { type: "success" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:dismiss-extraction" });
      notify("custom.content.content_list.review_session_dismiss_failed", { type: "error" });
    }
  };

  const resetClassification = async () => {
    if (!onSubmitReview) return;
    try {
      await onSubmitReview({ classification_reset: true });
      notify("custom.content.details.classification_reset_saved", {
        type: "success",
        messageArgs: { defaultValue: "Classification reset" },
      });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:reset-classification" });
      notify("custom.content.details.review_save_failed", { type: "error" });
    }
  };

  const resetExtraction = async () => {
    if (!onSubmitReview) return;
    try {
      await onSubmitReview({ extraction_reset: true });
      notify("custom.content.details.extraction_reset_saved", {
        type: "success",
        messageArgs: { defaultValue: "Extraction data reset" },
      });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "document-data:reset-extraction-clear" });
      notify("custom.content.details.review_save_failed", { type: "error" });
    }
  };

  const buckets = useMemo(() => {
    const attention: typeof entries = [];
    const attentionKeys = new Set<string>();
    for (const [key, value] of entries) {
      const meta = isObjectRecord(displayFieldsMeta?.[key])
        ? (displayFieldsMeta[key] as Record<string, unknown>)
        : undefined;
      const fieldNeedsReview =
        fieldsWithoutEvidence.includes(key) || (isObjectRecord(meta) && meta.needs_review === true);
      if (fieldBucket(value, meta, fieldNeedsReview) === "attention") {
        attention.push([key, value]);
        attentionKeys.add(key);
      }
    }
    return { attention, attentionKeys };
  }, [entries, displayFieldsMeta, fieldsWithoutEvidence]);

  const visibleEntries =
    showOnlyAttention && buckets.attention.length > 0 ? buckets.attention : entries;

  const renderField = (key: string, value: unknown) => {
    const meta = isObjectRecord(displayFieldsMeta?.[key])
      ? (displayFieldsMeta[key] as Record<string, unknown>)
      : undefined;
    const fieldNeedsReview =
      fieldsWithoutEvidence.includes(key) || (isObjectRecord(meta) && meta.needs_review === true);
    const aiValue = aiData ? aiData[key] : undefined;
    const bucket = fieldBucket(value, meta, fieldNeedsReview);
    return (
      <DocumentDataFieldRow
        key={key}
        fieldKey={key}
        rawValue={value}
        aiValue={aiValue}
        meta={meta}
        needsReview={fieldNeedsReview}
        bucket={bucket}
        disabled={!canEdit}
        saving={savingEnrichment}
        onSave={updateExtractionField}
        onNavigateToEvidence={onNavigateToEvidence}
      />
    );
  };

  const showResetExtractionAction = canEdit && canResetExtractionToAi;
  const canResetClassification =
    canEdit && Boolean(baseClassificationLabel || classification?.review_status);
  const canResetExtraction = canEdit && Boolean(baseExtractionData || extraction?.review_status);
  const hasResetActions = canResetClassification || canResetExtraction;

  const showStatePillInFooter = hasReviewableData && displayedReviewState === "needs_review";

  const classificationMatchesAi =
    Boolean(aiLabel) && normalizeLookup(classificationDraft) === normalizeLookup(aiLabel);

  const footerNode =
    hasReviewableData && (canEdit || showStatePillInFooter) ? (
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        {showStatePillInFooter ? (
          <StatePill state={displayedReviewState} label={stateLabel} />
        ) : null}
        {dirty ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={discardChanges}
            disabled={savingEnrichment}
          >
            <RotateCcw className="h-3 w-3" />
            {translate("custom.content.details.discard_changes", {
              defaultValue: "Discard changes",
            })}
          </Button>
        ) : null}
        {showResetExtractionAction ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={() => void resetExtractionToAi()}
            disabled={savingEnrichment}
          >
            <RotateCcw className="h-3 w-3" />
            {translate("custom.content.details.reset_to_ai_extraction")}
          </Button>
        ) : null}
        {canConfirm ? (
          <Button
            type="button"
            size="sm"
            className="h-7 gap-1.5 px-2 text-xs"
            onClick={() => void confirmContent()}
            disabled={savingEnrichment}
          >
            <CheckCircle2 className="h-3 w-3" />
            {confirmLabel}
          </Button>
        ) : null}
        {canEdit ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 px-2 text-xs"
                disabled={savingEnrichment}
              >
                <XCircle className="h-3 w-3" />
                {translate("custom.content.content_list.review_session_dismiss")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => void dismissContent("not_a_document")}>
                {translate("custom.content.content_list.review_session_dismiss_not_a_document")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void dismissContent("no_fitting_class")}>
                {translate("custom.content.content_list.review_session_dismiss_no_fitting_class")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void dismissExtraction("not_extractable")}>
                {translate("custom.content.content_list.review_session_dismiss_not_extractable")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void dismissExtraction("schema_mismatch")}>
                {translate("custom.content.content_list.review_session_dismiss_schema_mismatch")}
              </DropdownMenuItem>
              {hasResetActions ? <DropdownMenuSeparator /> : null}
              {canResetClassification ? (
                <DropdownMenuItem onSelect={() => void resetClassification()}>
                  {translate("custom.content.details.reset_classification", {
                    defaultValue: "Reset classification to unclassified",
                  })}
                </DropdownMenuItem>
              ) : null}
              {canResetExtraction ? (
                <DropdownMenuItem onSelect={() => void resetExtraction()}>
                  {translate("custom.content.details.reset_extraction", {
                    defaultValue: "Clear extraction data",
                  })}
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    ) : null;

  return (
    <div className="@container/docdata space-y-3">
      {stale ? (
        <Alert className="border-amber-300/70 bg-amber-50 text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100 [&>svg]:text-amber-700 dark:[&>svg]:text-amber-300">
          <Clock className="h-4 w-4" />
          <AlertDescription className="flex flex-col items-start gap-2">
            <span>{translate("custom.content.details.stale_refresh_hint")}</span>
            {onRerunEnrichment ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 shrink-0 self-start border-amber-300/70 bg-amber-100/60 text-amber-900 hover:bg-amber-100 dark:border-amber-700/60 dark:bg-amber-900/30 dark:text-amber-100 dark:hover:bg-amber-900/50"
                onClick={onRerunEnrichment}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                {translate("custom.content.actions.rerun_enrichment")}
              </Button>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {!hasReviewableData ? (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            {translate("custom.content.details.no_reviewable_data", {
              defaultValue: "No classification or extraction data is available.",
            })}
          </AlertDescription>
        </Alert>
      ) : null}

      <div
        className={cn(
          "grid grid-cols-1 items-start gap-3",
          hasClassificationSurface && hasExtractionSurface && "@[480px]/docdata:grid-cols-2",
        )}
      >
        {hasClassificationSurface ? (
          <Card id="inspector-classification" className="shadow-none">
            <CardHeader className="space-y-0 px-3 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1 space-y-1">
                  <CardDescription className="text-[10px] font-medium uppercase tracking-wide">
                    {translate("custom.content.details.document_classification")}
                  </CardDescription>
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <CardTitle className="truncate text-base">
                      {classificationDraft || (
                        <span className="text-sm font-normal text-muted-foreground">
                          {translate("custom.content.details.no_document_classification")}
                        </span>
                      )}
                    </CardTitle>
                    {classificationConfidence !== null ? (
                      <span className="text-xs font-normal text-muted-foreground">
                        {formatConfidence(classificationConfidence)}
                      </span>
                    ) : null}
                    {classificationMatchesAi ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Sparkles className="h-3.5 w-3.5 shrink-0 text-blue-600 dark:text-blue-300" />
                        </TooltipTrigger>
                        <TooltipContent>
                          {translate("custom.content.details.classification_matches_ai", {
                            defaultValue: "Matches AI classification",
                          })}
                        </TooltipContent>
                      </Tooltip>
                    ) : aiLabel && baseClassificationLabel && canVerifyClass ? (
                      <Popover open={resetClassPopoverOpen} onOpenChange={setResetClassPopoverOpen}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <PopoverTrigger asChild>
                              <button
                                type="button"
                                className="inline-flex h-5 items-center gap-1 rounded border border-blue-200 bg-blue-50 px-1.5 text-[10px] font-medium uppercase text-blue-900 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-800/40 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50"
                                disabled={savingEnrichment || forcedExtractionPending}
                                aria-label={translate("custom.content.details.reset_to_ai_class")}
                              >
                                <Sparkles className="h-2.5 w-2.5" />
                                {translate("custom.content.details.ai_value", {
                                  defaultValue: "AI",
                                })}
                              </button>
                            </PopoverTrigger>
                          </TooltipTrigger>
                          <TooltipContent>
                            {translate("custom.content.details.ai_suggested", {
                              defaultValue: "AI suggested",
                            })}
                            : {aiLabel}
                          </TooltipContent>
                        </Tooltip>
                        <PopoverContent align="start" className="w-72 space-y-3 p-3">
                          <div>
                            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                              {translate("custom.content.details.ai_suggested", {
                                defaultValue: "AI suggested",
                              })}
                            </div>
                            <div className="mt-0.5 truncate text-sm font-semibold">{aiLabel}</div>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {translate("custom.content.details.reset_class_confirm_description")}
                          </p>
                          <div className="flex justify-end gap-2">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              onClick={() => setResetClassPopoverOpen(false)}
                              disabled={savingEnrichment}
                            >
                              {translate("custom.content.processing_config.cancel")}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              onClick={() => {
                                setResetClassPopoverOpen(false);
                                void verifyClass(aiLabel);
                              }}
                              disabled={savingEnrichment || forcedExtractionPending}
                            >
                              <RotateCcw className="mr-1.5 h-3 w-3" />
                              {translate("custom.content.details.reset_to_ai_class")}
                            </Button>
                          </div>
                        </PopoverContent>
                      </Popover>
                    ) : null}
                    {classification?.needs_review === true ? (
                      <Badge
                        variant="outline"
                        className="h-5 gap-1 px-1.5 text-[10px] font-medium text-amber-900 border-amber-300/60 bg-amber-50 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-200"
                      >
                        <AlertCircle className="h-2.5 w-2.5" />
                        {translate("custom.content.details.review_unreviewed")}
                      </Badge>
                    ) : null}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <EvidenceChip
                    docRefs={evidenceDocRefs}
                    label={translate("custom.content.details.document_classification")}
                    onNavigate={onNavigateToEvidence}
                  />
                  {canVerifyClass ? (
                    <Popover
                      open={pickerOpen}
                      onOpenChange={(open) => {
                        setPickerOpen(open);
                        if (open && catalogQuery.isError) void catalogQuery.refetch();
                      }}
                    >
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <PopoverTrigger asChild>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              disabled={savingEnrichment}
                              aria-label={translate("custom.content.details.edit_override")}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                          </PopoverTrigger>
                        </TooltipTrigger>
                        <TooltipContent>
                          {translate("custom.content.details.edit_override")}
                        </TooltipContent>
                      </Tooltip>
                      <PopoverContent align="end" className="w-80 p-0">
                        {classificationCandidates.length > 0 ? (
                          <>
                            <div className="p-2">
                              <div className="mb-1 px-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                                {translate("custom.content.details.other_candidates")}
                              </div>
                              <div className="flex flex-col gap-0.5">
                                {classificationCandidates.slice(0, 5).map((candidate) => {
                                  const isAi = aiLabel === candidate.label;
                                  const isCurrent = candidate.label === classificationDraft;
                                  return (
                                    <button
                                      key={candidate.label}
                                      type="button"
                                      className={cn(
                                        "flex items-center justify-between gap-2 rounded px-2 py-1 text-left text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
                                        isCurrent && "bg-accent",
                                      )}
                                      onClick={() => void verifyClass(candidate.label)}
                                      disabled={savingEnrichment || isCurrent}
                                    >
                                      <span className="flex min-w-0 items-center gap-1.5">
                                        {isAi ? (
                                          <Sparkles className="h-3 w-3 shrink-0 text-blue-600 dark:text-blue-300" />
                                        ) : null}
                                        <span className="truncate font-medium">
                                          {candidate.label}
                                        </span>
                                      </span>
                                      {candidate.confidence !== null ? (
                                        <span className="shrink-0 text-[10px] text-muted-foreground">
                                          {formatConfidence(candidate.confidence)}
                                        </span>
                                      ) : null}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                            <Separator />
                          </>
                        ) : null}
                        <Command>
                          <CommandInput
                            placeholder={translate("custom.content.details.class_picker_search")}
                          />
                          <CommandList>
                            {catalogQuery.isError ? (
                              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                                {translate("custom.content.details.class_picker_load_failed")}
                              </div>
                            ) : catalogLoading ? (
                              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                                {translate("custom.content.details.class_picker_loading")}
                              </div>
                            ) : (
                              <>
                                <CommandEmpty>
                                  {translate("custom.content.details.class_picker_empty")}
                                </CommandEmpty>
                                <CommandGroup>
                                  {catalogClasses.map((catalogClass) => (
                                    <CommandItem
                                      key={catalogClass.id}
                                      value={[catalogClass.name, ...catalogClass.aliases].join(" ")}
                                      onSelect={() => {
                                        void verifyClass(catalogClass.name);
                                      }}
                                      disabled={
                                        savingEnrichment ||
                                        catalogClass.name === classificationDraft
                                      }
                                    >
                                      <div className="min-w-0 flex-1">
                                        <div className="truncate text-sm font-medium">
                                          {catalogClass.name}
                                        </div>
                                        {catalogClass.description ? (
                                          <div className="truncate text-xs text-muted-foreground">
                                            {catalogClass.description}
                                          </div>
                                        ) : null}
                                      </div>
                                    </CommandItem>
                                  ))}
                                </CommandGroup>
                              </>
                            )}
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  ) : null}
                </div>
              </div>
            </CardHeader>
          </Card>
        ) : null}

        {hasExtractionSurface ? (
          <div className="space-y-1.5">
            {forcedExtractionPending ? (
              <Alert className="border-blue-200 bg-blue-50 text-blue-950 dark:border-blue-800/50 dark:bg-blue-950/30 dark:text-blue-100 [&>svg]:text-blue-600 dark:[&>svg]:text-blue-300">
                <Sparkles className="h-4 w-4" />
                <AlertDescription>
                  {translate("custom.content.details.extracting_for_verified_class", {
                    class: forcedExtractionClassLabel,
                  })}
                </AlertDescription>
              </Alert>
            ) : extractionClassMismatch ? (
              <Alert className="border-amber-300/70 bg-amber-50 text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100 [&>svg]:text-amber-700 dark:[&>svg]:text-amber-300">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {translate("custom.content.details.extraction_class_mismatch")}
                </AlertDescription>
              </Alert>
            ) : entries.length === 0 ? (
              <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription>
                  {classificationDraft
                    ? translate("custom.content.details.no_document_extraction")
                    : translate("custom.content.details.choose_classification_for_extraction")}
                </AlertDescription>
              </Alert>
            ) : (
              <>
                {buckets.attention.length > 0 ? (
                  <div className="flex items-center justify-end">
                    <Toggle
                      size="sm"
                      variant="outline"
                      pressed={showOnlyAttention}
                      onPressedChange={setShowOnlyAttention}
                      className={cn(
                        "h-6 gap-1 px-2 text-[10px] font-medium",
                        showOnlyAttention &&
                          "border-amber-300/60 bg-amber-50 text-amber-900 hover:bg-amber-100 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-200",
                      )}
                    >
                      <AlertCircle className="h-3 w-3" />
                      {showOnlyAttention
                        ? translate("custom.content.details.show_all_fields", {
                            defaultValue: "Show all fields",
                          })
                        : translate("custom.content.details.show_only_attention", {
                            count: buckets.attention.length,
                          })}
                    </Toggle>
                  </div>
                ) : null}
                <div className="divide-y divide-border/40 overflow-hidden rounded-md border">
                  {visibleEntries.map(([key, value]) => renderField(key, value))}
                </div>
              </>
            )}
          </div>
        ) : null}
      </div>

      {footerSlot ? null : footerNode ? <div className="pt-1">{footerNode}</div> : null}
      {footerSlot && footerNode ? createPortal(footerNode, footerSlot) : null}
    </div>
  );
};
