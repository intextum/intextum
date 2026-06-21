import { Link } from "react-router";
import { useMemo } from "react";
import { CheckCircle2, FileWarning, Loader2, Play, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type {
  ContentEnrichmentFineTuneJobEntry,
  ContentEnrichmentModelRegistryEntry,
} from "@/dataProvider";
import type { ContentEnrichmentPromotionImpactSummary } from "@/lib/content-enrichment-training";

import {
  contentEnrichmentCurrentModelLabel,
  contentEnrichmentTrainingStatusLabel,
  contentEnrichmentTrainingStatusVariant,
} from "./content-enrichment";
import { ContentEnrichmentTrainingRecentRuns } from "./ContentEnrichmentTrainingRecentRuns";

type Translate = (key: string, options?: unknown) => string;

interface ContentEnrichmentTrainingPipelineProps {
  translate: Translate;
  targetKind: "classification";
  baseModel: string;
  availableTargetCount: number;
  currentReviewedExampleCount?: number;
  models: ContentEnrichmentModelRegistryEntry[];
  jobs: ContentEnrichmentFineTuneJobEntry[];
  creatingTrainingJobKey: string | null;
  retryingJobId: string | null;
  cancelingJobId: string | null;
  deletingJobId: string | null;
  promotingModelId: string | null;
  archivingModelId: string | null;
  rerunningStaleEnrichment: boolean;
  lastPromotionImpact: ContentEnrichmentPromotionImpactSummary | null;
  onCreateTrainingJob: (targetKind: "classification") => void;
  onRetryTrainingJob: (jobId: string) => void;
  onCancelTrainingJob: (jobId: string) => void;
  onDeleteTrainingJob: (jobId: string) => void;
  onPromoteTrainingModel: (modelId: string) => void;
  onArchiveTrainingModel: (modelId: string) => void;
  onRerunPromotionImpact: (impact: ContentEnrichmentPromotionImpactSummary) => void;
}

function StageTile({
  index,
  title,
  children,
  highlight,
}: {
  index: number;
  title: string;
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex min-h-[120px] flex-col gap-2 rounded-md border bg-background px-3 py-2 ${
        highlight ? "border-primary/60 bg-primary/5" : ""
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
          {index}
        </span>
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 text-sm">{children}</div>
    </div>
  );
}

export function ContentEnrichmentTrainingPipeline({
  translate,
  targetKind,
  baseModel,
  availableTargetCount,
  currentReviewedExampleCount,
  models,
  jobs,
  creatingTrainingJobKey,
  retryingJobId,
  cancelingJobId,
  deletingJobId,
  promotingModelId,
  archivingModelId,
  rerunningStaleEnrichment,
  lastPromotionImpact,
  onCreateTrainingJob,
  onRetryTrainingJob,
  onCancelTrainingJob,
  onDeleteTrainingJob,
  onPromoteTrainingModel,
  onArchiveTrainingModel,
  onRerunPromotionImpact,
}: ContentEnrichmentTrainingPipelineProps) {
  const kindJobs = useMemo(
    () => jobs.filter((job) => job.target_kind === targetKind),
    [jobs, targetKind],
  );
  const kindModels = useMemo(
    () => models.filter((model) => model.target_kind === targetKind),
    [models, targetKind],
  );

  const liveJob = kindJobs.find((job) => job.status === "queued" || job.status === "running");
  const lastCompletedJob = kindJobs.find(
    (job) => job.status === "completed" || job.status === "failed",
  );
  const activeModel = kindModels.find((model) => model.is_active);
  const latestReadyModel = kindModels.find((model) => model.status === "ready" && !model.is_active);

  const totalReviewedExamples =
    currentReviewedExampleCount ??
    activeModel?.reviewed_example_count ??
    latestReadyModel?.reviewed_example_count ??
    lastCompletedJob?.dataset_summary.reviewed_example_count ??
    0;

  const isCreating = creatingTrainingJobKey === targetKind;
  const noTargetsAvailable = availableTargetCount === 0;
  const trainDisabled = creatingTrainingJobKey !== null || noTargetsAvailable;
  const disabledTooltipKey = noTargetsAvailable ? "train_disabled_no_classes" : null;

  const promotionForThisKind =
    lastPromotionImpact?.target_kind === targetKind ? lastPromotionImpact : null;

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-base font-medium">
            {translate(
              "custom.pages.settings.ai.content_enrichment_training.classification_card_title",
            )}
          </h4>
          <Badge variant="outline" className="text-[10px]">
            {translate("custom.pages.settings.ai.content_enrichment_training.method_badge")}
          </Badge>
          {activeModel ? (
            <Badge variant="secondary" className="text-[10px]">
              {translate(
                "custom.pages.settings.ai.content_enrichment_training.pipeline_active_model",
              )}
            </Badge>
          ) : null}
        </div>
        <p className="text-sm text-muted-foreground">
          {translate(
            "custom.pages.settings.ai.content_enrichment_training.classification_card_description",
          )}
        </p>
      </div>
      <Separator />
      <div className="space-y-4">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          <StageTile
            index={1}
            title={translate("custom.pages.settings.ai.content_enrichment_training.stage_examples")}
          >
            <p className="text-2xl font-semibold">{totalReviewedExamples}</p>
            <p className="text-xs text-muted-foreground">
              {translate(
                "custom.pages.settings.ai.content_enrichment_training.stage_examples_hint",
              )}
            </p>
          </StageTile>

          <StageTile
            index={2}
            title={translate("custom.pages.settings.ai.content_enrichment_training.stage_train")}
            highlight={Boolean(liveJob) || isCreating}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className={trainDisabled ? "inline-block cursor-not-allowed" : "inline-block"}
                >
                  <Button
                    type="button"
                    size="sm"
                    className="gap-2"
                    onClick={() => onCreateTrainingJob(targetKind)}
                    disabled={trainDisabled}
                  >
                    {isCreating || liveJob ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                    {isCreating
                      ? translate("custom.pages.settings.ai.content_enrichment_training.creating")
                      : translate(
                          "custom.pages.settings.ai.content_enrichment_training.train_classification",
                        )}
                  </Button>
                </span>
              </TooltipTrigger>
              {disabledTooltipKey ? (
                <TooltipContent>
                  {translate(
                    `custom.pages.settings.ai.content_enrichment_training.${disabledTooltipKey}` as const,
                  )}
                </TooltipContent>
              ) : null}
            </Tooltip>
            {liveJob ? (
              <p className="text-[11px] text-muted-foreground">
                {contentEnrichmentTrainingStatusLabel(liveJob.status, translate)}
              </p>
            ) : null}
          </StageTile>

          <StageTile
            index={3}
            title={translate("custom.pages.settings.ai.content_enrichment_training.stage_review")}
          >
            {latestReadyModel ? (
              <>
                <div className="flex flex-wrap items-center gap-1">
                  <Sparkles className="h-3.5 w-3.5 text-emerald-600" />
                  <span className="text-sm font-medium">
                    {translate(
                      "custom.pages.settings.ai.content_enrichment_training.stage_review_ready",
                    )}
                  </span>
                  <Badge
                    variant={contentEnrichmentTrainingStatusVariant(latestReadyModel.status)}
                    className="text-[10px]"
                  >
                    {contentEnrichmentTrainingStatusLabel(latestReadyModel.status, translate)}
                  </Badge>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => onPromoteTrainingModel(latestReadyModel.id)}
                  disabled={
                    promotingModelId !== null ||
                    archivingModelId !== null ||
                    latestReadyModel.is_active
                  }
                >
                  {promotingModelId === latestReadyModel.id
                    ? translate("custom.pages.settings.ai.content_enrichment_training.promoting")
                    : translate(
                        "custom.pages.settings.ai.content_enrichment_training.promote_button",
                      )}
                </Button>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                {translate(
                  "custom.pages.settings.ai.content_enrichment_training.stage_review_empty",
                )}
              </p>
            )}
          </StageTile>

          <StageTile
            index={4}
            title={translate("custom.pages.settings.ai.content_enrichment_training.stage_promote")}
          >
            {activeModel ? (
              <>
                <div className="flex flex-wrap items-center gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  <span className="text-sm font-medium">
                    {contentEnrichmentCurrentModelLabel(baseModel, models, translate)}
                  </span>
                </div>
                {promotionForThisKind ? (
                  <div className="space-y-1">
                    <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <FileWarning className="h-3 w-3 text-amber-600" />
                      {translate(
                        "custom.pages.settings.ai.content_enrichment_training.promotion_stale_description",
                        { count: promotionForThisKind.stale_count },
                      )}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="default"
                        onClick={() => onRerunPromotionImpact(promotionForThisKind)}
                        disabled={rerunningStaleEnrichment}
                      >
                        {translate(
                          "custom.pages.settings.ai.content_enrichment_training.queue_stale_classification",
                        )}
                      </Button>
                      <Button asChild size="sm" variant="ghost">
                        <Link to={promotionForThisKind.review_path}>
                          {translate(
                            "custom.pages.settings.ai.content_enrichment_training.open_stale_queue",
                          )}
                        </Link>
                      </Button>
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                {translate(
                  "custom.pages.settings.ai.content_enrichment_training.stage_promote_empty",
                )}
              </p>
            )}
          </StageTile>
        </div>

        <ContentEnrichmentTrainingRecentRuns
          translate={translate}
          jobs={kindJobs}
          models={kindModels}
          retryingJobId={retryingJobId}
          cancelingJobId={cancelingJobId}
          deletingJobId={deletingJobId}
          promotingModelId={promotingModelId}
          archivingModelId={archivingModelId}
          onRetryTrainingJob={onRetryTrainingJob}
          onCancelTrainingJob={onCancelTrainingJob}
          onDeleteTrainingJob={onDeleteTrainingJob}
          onPromoteTrainingModel={onPromoteTrainingModel}
          onArchiveTrainingModel={onArchiveTrainingModel}
        />
      </div>
    </section>
  );
}
