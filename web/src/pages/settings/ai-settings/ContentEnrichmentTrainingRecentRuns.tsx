import { useState } from "react";

import { Button } from "@/components/ui/button";
import type {
  ContentEnrichmentFineTuneJobEntry,
  ContentEnrichmentModelRegistryEntry,
} from "@/dataProvider";

import {
  ContentEnrichmentTrainingJobList,
  ContentEnrichmentTrainingModelList,
} from "./ContentEnrichmentTrainingLists";

type Translate = (key: string, options?: unknown) => string;

const COLLAPSED_LIMIT = 3;

interface ContentEnrichmentTrainingRecentRunsProps {
  translate: Translate;
  jobs: ContentEnrichmentFineTuneJobEntry[];
  models: ContentEnrichmentModelRegistryEntry[];
  retryingJobId: string | null;
  cancelingJobId: string | null;
  deletingJobId: string | null;
  promotingModelId: string | null;
  archivingModelId: string | null;
  onRetryTrainingJob: (jobId: string) => void;
  onCancelTrainingJob: (jobId: string) => void;
  onDeleteTrainingJob: (jobId: string) => void;
  onPromoteTrainingModel: (modelId: string) => void;
  onArchiveTrainingModel: (modelId: string) => void;
}

export function ContentEnrichmentTrainingRecentRuns({
  translate,
  jobs,
  models,
  retryingJobId,
  cancelingJobId,
  deletingJobId,
  promotingModelId,
  archivingModelId,
  onRetryTrainingJob,
  onCancelTrainingJob,
  onDeleteTrainingJob,
  onPromoteTrainingModel,
  onArchiveTrainingModel,
}: ContentEnrichmentTrainingRecentRunsProps) {
  const [expanded, setExpanded] = useState(false);
  const visibleJobs = expanded ? jobs : jobs.slice(0, COLLAPSED_LIMIT);
  const visibleModels = expanded ? models : models.slice(0, COLLAPSED_LIMIT);
  const hiddenCount =
    Math.max(0, jobs.length - visibleJobs.length) +
    Math.max(0, models.length - visibleModels.length);

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {translate("custom.pages.settings.ai.content_enrichment_training.recent_jobs_title")}
        </p>
        <ContentEnrichmentTrainingJobList
          jobs={visibleJobs}
          translate={translate}
          retryingJobId={retryingJobId}
          cancelingJobId={cancelingJobId}
          deletingJobId={deletingJobId}
          onRetryTrainingJob={onRetryTrainingJob}
          onCancelTrainingJob={onCancelTrainingJob}
          onDeleteTrainingJob={onDeleteTrainingJob}
        />
      </div>
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {translate("custom.pages.settings.ai.content_enrichment_training.recent_models_title")}
        </p>
        <ContentEnrichmentTrainingModelList
          models={visibleModels}
          translate={translate}
          promotingModelId={promotingModelId}
          archivingModelId={archivingModelId}
          onPromoteTrainingModel={onPromoteTrainingModel}
          onArchiveTrainingModel={onArchiveTrainingModel}
        />
      </div>
      {hiddenCount > 0 || expanded ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded
            ? translate("custom.pages.settings.ai.content_enrichment_training.recent_show_less")
            : translate("custom.pages.settings.ai.content_enrichment_training.recent_show_more", {
                count: hiddenCount,
              })}
        </Button>
      ) : null}
    </div>
  );
}
