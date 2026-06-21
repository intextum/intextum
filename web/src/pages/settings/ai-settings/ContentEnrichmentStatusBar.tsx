import type { ReactNode } from "react";
import { Link } from "react-router";
import { CheckCircle2, FileWarning } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  summarizeContentEnrichmentQueue,
  summarizeContentEnrichmentRerun,
} from "@/lib/content-enrichment-admin";

import { ContentEnrichmentStaleRerunControl } from "./ContentEnrichmentStaleRerunControl";

type Translate = (key: string, options?: unknown) => string;

interface ContentEnrichmentStatusBarProps {
  translate: Translate;
  staleEnrichmentCount: number | null;
  loadingStaleEnrichmentCount: boolean;
  rerunningStaleEnrichment: boolean;
  lastStaleRerunResult: { queued: number; matched: number; errors: number } | null;
  onRerunStaleEnrichment: (staleCount: number) => void;
}

interface StatusRowProps {
  tone: "warning" | "success";
  icon: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

function StatusRow({ tone, icon, title, description, actions }: StatusRowProps) {
  const dotClass = tone === "warning" ? "text-amber-600" : "text-emerald-600";
  return (
    <div className="flex flex-wrap items-center gap-3 px-3 py-2">
      <span className={dotClass}>{icon}</span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{title}</span>
        {description ? <span className="text-xs text-muted-foreground">{description}</span> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function ContentEnrichmentStatusBar({
  translate,
  staleEnrichmentCount,
  loadingStaleEnrichmentCount,
  rerunningStaleEnrichment,
  lastStaleRerunResult,
  onRerunStaleEnrichment,
}: ContentEnrichmentStatusBarProps) {
  const enrichmentQueueSummary =
    staleEnrichmentCount !== null ? summarizeContentEnrichmentQueue(staleEnrichmentCount) : null;
  const rerunSummary = lastStaleRerunResult
    ? summarizeContentEnrichmentRerun(lastStaleRerunResult)
    : null;

  if (!loadingStaleEnrichmentCount && enrichmentQueueSummary === null && !rerunSummary) {
    return null;
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {loadingStaleEnrichmentCount ? (
        <div className="flex items-center gap-3 px-3 py-2">
          <Skeleton className="h-4 w-4 rounded-full" />
          <Skeleton className="h-4 w-48" />
          <Skeleton className="ml-auto h-8 w-32" />
        </div>
      ) : enrichmentQueueSummary?.hasStaleFiles ? (
        <StatusRow
          tone="warning"
          icon={<FileWarning className="h-4 w-4" />}
          title={translate("custom.pages.settings.ai.content_enrichment_editor.stale_queue_title", {
            count: enrichmentQueueSummary.staleCount,
          })}
          description={translate(
            "custom.pages.settings.ai.content_enrichment_editor.stale_queue_description",
          )}
          actions={
            <>
              <ContentEnrichmentStaleRerunControl
                translate={translate}
                staleCount={enrichmentQueueSummary.staleCount}
                rerunningStaleEnrichment={rerunningStaleEnrichment}
                onRerunStaleEnrichment={onRerunStaleEnrichment}
              />
              <Button asChild size="sm" variant="ghost">
                <Link to="/content?view=all&stale_enrichment=true">
                  {translate("custom.pages.settings.ai.content_enrichment_editor.stale_queue_open")}
                </Link>
              </Button>
            </>
          }
        />
      ) : enrichmentQueueSummary ? (
        <StatusRow
          tone="success"
          icon={<CheckCircle2 className="h-4 w-4" />}
          title={translate(
            "custom.pages.settings.ai.content_enrichment_editor.stale_queue_empty_title",
          )}
        />
      ) : null}

      {rerunSummary ? (
        <div className="border-t bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          <div className="flex flex-wrap items-center gap-3">
            <span>
              {translate("custom.pages.settings.ai.content_enrichment_editor.stale_queue_result", {
                queued: rerunSummary.queuedCount,
                matched: rerunSummary.matchedCount,
                errors: rerunSummary.errorCount,
              })}
            </span>
            <Button asChild size="sm" variant="ghost" className="h-7 text-xs">
              <Link to="/content?view=all&status=QUEUED">
                {translate(
                  "custom.pages.settings.ai.content_enrichment_editor.stale_queue_open_processing",
                )}
              </Link>
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
