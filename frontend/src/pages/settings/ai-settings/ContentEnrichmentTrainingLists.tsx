import { RotateCcw, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  ContentEnrichmentFineTuneJobEntry,
  ContentEnrichmentModelRegistryEntry,
} from "@/dataProvider";
import {
  formatContentEnrichmentMetricNumber,
  formatContentEnrichmentMetricPercent,
  summarizeContentEnrichmentTrainingMetrics,
} from "@/lib/content-enrichment-training";
import {
  contentEnrichmentTrainingStatusLabel,
  contentEnrichmentTrainingStatusVariant,
  contentEnrichmentTrainingTargetLabel,
} from "./content-enrichment";

type Translate = (key: string, options?: unknown) => string;

function formatTimestamp(value: string, fallback = " - ") {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return fallback;
  }
  return new Date(timestamp).toLocaleString();
}

function compactMetricSummary(model: ContentEnrichmentModelRegistryEntry, translate: Translate) {
  const metrics = summarizeContentEnrichmentTrainingMetrics(model.metrics);
  const summary = [
    metrics.best_metric !== null
      ? translate("custom.pages.settings.ai.content_enrichment_training.metric_best_metric", {
          value: formatContentEnrichmentMetricNumber(metrics.best_metric),
        })
      : null,
    metrics.validation_accuracy !== null
      ? translate(
          "custom.pages.settings.ai.content_enrichment_training.metric_validation_accuracy",
          {
            value: formatContentEnrichmentMetricPercent(metrics.validation_accuracy),
          },
        )
      : null,
    metrics.eval_loss !== null
      ? translate("custom.pages.settings.ai.content_enrichment_training.metric_eval_loss", {
          value: formatContentEnrichmentMetricNumber(metrics.eval_loss),
        })
      : null,
  ].filter((item): item is string => Boolean(item));

  return {
    metrics,
    summary,
  };
}

export function ContentEnrichmentTrainingJobList({
  jobs,
  translate,
  retryingJobId,
  cancelingJobId,
  deletingJobId,
  onRetryTrainingJob,
  onCancelTrainingJob,
  onDeleteTrainingJob,
}: {
  jobs: ContentEnrichmentFineTuneJobEntry[];
  translate: Translate;
  retryingJobId: string | null;
  cancelingJobId: string | null;
  deletingJobId: string | null;
  onRetryTrainingJob: (jobId: string) => void;
  onCancelTrainingJob: (jobId: string) => void;
  onDeleteTrainingJob: (jobId: string) => void;
}) {
  if (!jobs.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {translate("custom.pages.settings.ai.content_enrichment_training.empty_jobs")}
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_target")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_status")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_data")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_requested")}
          </TableHead>
          <TableHead className="text-right">
            {translate("custom.pages.settings.ai.content_enrichment_training.table_actions")}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.id}>
            <TableCell className="align-top">
              <div className="min-w-0 space-y-1">
                <div className="font-medium">
                  {contentEnrichmentTrainingTargetLabel(
                    job.target_kind,
                    job.target_name,
                    translate,
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {translate("custom.pages.settings.ai.content_enrichment_training.base_model", {
                    model: job.base_model,
                  })}
                </div>
                {job.error_message ? (
                  <div className="text-xs text-destructive">{job.error_message}</div>
                ) : null}
              </div>
            </TableCell>
            <TableCell className="align-top">
              <div className="flex flex-wrap gap-2">
                <Badge variant={contentEnrichmentTrainingStatusVariant(job.status)}>
                  {contentEnrichmentTrainingStatusLabel(job.status, translate)}
                </Badge>
                <Badge variant="outline">{job.training_method.toUpperCase()}</Badge>
              </div>
            </TableCell>
            <TableCell className="align-top text-sm text-muted-foreground">
              {translate("custom.pages.settings.ai.content_enrichment_training.reviewed_examples", {
                count: job.dataset_summary.reviewed_example_count,
              })}
            </TableCell>
            <TableCell className="align-top text-sm text-muted-foreground">
              <div>{formatTimestamp(job.created_at)}</div>
              {job.requested_by ? <div className="text-xs">{job.requested_by}</div> : null}
            </TableCell>
            <TableCell className="align-top">
              <div className="flex justify-end gap-2">
                {job.status === "failed" ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onRetryTrainingJob(job.id)}
                    disabled={
                      retryingJobId !== null || cancelingJobId !== null || deletingJobId !== null
                    }
                  >
                    <RotateCcw className="mr-1 h-4 w-4" />
                    {retryingJobId === job.id
                      ? translate("custom.pages.settings.ai.content_enrichment_training.retrying")
                      : translate(
                          "custom.pages.settings.ai.content_enrichment_training.retry_button",
                        )}
                  </Button>
                ) : null}
                {job.status === "queued" || job.status === "running" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onCancelTrainingJob(job.id)}
                    disabled={cancelingJobId !== null || retryingJobId !== null}
                  >
                    <X className="mr-1 h-4 w-4" />
                    {cancelingJobId === job.id
                      ? translate("custom.pages.settings.ai.content_enrichment_training.cancelling")
                      : translate(
                          "custom.pages.settings.ai.content_enrichment_training.cancel_button",
                        )}
                  </Button>
                ) : null}
                {job.status === "failed" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onDeleteTrainingJob(job.id)}
                    disabled={
                      deletingJobId !== null || retryingJobId !== null || cancelingJobId !== null
                    }
                  >
                    <Trash2 className="mr-1 h-4 w-4" />
                    {deletingJobId === job.id
                      ? translate("custom.pages.settings.ai.content_enrichment_training.deleting")
                      : translate(
                          "custom.pages.settings.ai.content_enrichment_training.delete_button",
                        )}
                  </Button>
                ) : null}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ContentEnrichmentTrainingModelList({
  models,
  translate,
  promotingModelId,
  archivingModelId,
  onPromoteTrainingModel,
  onArchiveTrainingModel,
}: {
  models: ContentEnrichmentModelRegistryEntry[];
  translate: Translate;
  promotingModelId: string | null;
  archivingModelId: string | null;
  onPromoteTrainingModel: (modelId: string) => void;
  onArchiveTrainingModel: (modelId: string) => void;
}) {
  if (!models.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {translate("custom.pages.settings.ai.content_enrichment_training.empty_models")}
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_target")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_status")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_data")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_metrics")}
          </TableHead>
          <TableHead>
            {translate("custom.pages.settings.ai.content_enrichment_training.table_created")}
          </TableHead>
          <TableHead className="text-right">
            {translate("custom.pages.settings.ai.content_enrichment_training.table_actions")}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {models.map((model) => {
          const { metrics, summary } = compactMetricSummary(model, translate);

          return (
            <TableRow key={model.id}>
              <TableCell className="align-top">
                <div className="min-w-0 space-y-1">
                  <div className="font-medium">
                    {contentEnrichmentTrainingTargetLabel(
                      model.target_kind,
                      model.target_name,
                      translate,
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {translate("custom.pages.settings.ai.content_enrichment_training.base_model", {
                      model: model.base_model,
                    })}
                  </div>
                </div>
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-wrap gap-2">
                  <Badge variant={contentEnrichmentTrainingStatusVariant(model.status)}>
                    {contentEnrichmentTrainingStatusLabel(model.status, translate)}
                  </Badge>
                  <Badge variant="outline">{model.training_method.toUpperCase()}</Badge>
                  {model.is_active ? (
                    <Badge variant="secondary">
                      {translate(
                        "custom.pages.settings.ai.content_enrichment_training.active_badge",
                      )}
                    </Badge>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="align-top text-sm text-muted-foreground">
                {translate(
                  "custom.pages.settings.ai.content_enrichment_training.reviewed_examples",
                  {
                    count: model.reviewed_example_count,
                  },
                )}
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-wrap gap-2">
                  {summary.map((item) => (
                    <Badge key={item} variant="secondary" className="text-[11px]">
                      {item}
                    </Badge>
                  ))}
                </div>
                {metrics.validation_status === "failed" && metrics.validation_error ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {translate(
                      "custom.pages.settings.ai.content_enrichment_training.validation_failed",
                      {
                        error: metrics.validation_error,
                      },
                    )}
                  </p>
                ) : null}
              </TableCell>
              <TableCell className="align-top text-sm text-muted-foreground">
                {formatTimestamp(model.created_at)}
              </TableCell>
              <TableCell className="align-top">
                <div className="flex justify-end gap-2">
                  {model.status === "ready" && !model.is_active ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onPromoteTrainingModel(model.id)}
                      disabled={promotingModelId !== null || archivingModelId !== null}
                    >
                      {promotingModelId === model.id
                        ? translate(
                            "custom.pages.settings.ai.content_enrichment_training.promoting",
                          )
                        : translate(
                            "custom.pages.settings.ai.content_enrichment_training.promote_button",
                          )}
                    </Button>
                  ) : null}
                  {!model.is_active && (model.status === "ready" || model.status === "failed") ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => onArchiveTrainingModel(model.id)}
                      disabled={archivingModelId !== null || promotingModelId !== null}
                    >
                      <Trash2 className="mr-1 h-4 w-4" />
                      {archivingModelId === model.id
                        ? translate(
                            "custom.pages.settings.ai.content_enrichment_training.archiving",
                          )
                        : translate(
                            "custom.pages.settings.ai.content_enrichment_training.archive_button",
                          )}
                    </Button>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
