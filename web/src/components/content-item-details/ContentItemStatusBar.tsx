import { useTranslate } from "@/lib/app-context";
import { AlertTriangle, Calendar, CheckCircle2, Clock, HardDrive } from "lucide-react";
import { type ContentItemInfo } from "@/dataProvider";
import { formatDate } from "@/lib/content-utils";
import { itemFlowPresentation, stageLabel } from "@/lib/status-presentations";
import { ContentItemStatusBadge } from "./ContentItemStatusBadge";

interface ContentItemStatusBarProps {
  file: ContentItemInfo;
  isProcessing: boolean;
  hasAttention: boolean;
}

export const ContentItemStatusBar = ({
  file,
  isProcessing,
  hasAttention,
}: ContentItemStatusBarProps) => {
  const translate = useTranslate();
  const flow = itemFlowPresentation(file);
  const flowDescription = file.processing_error || translate(flow.descriptionKey);
  const currentStage = isProcessing ? stageLabel(file.processing_stage, translate) : null;

  return (
    <footer className="z-10 flex h-9 min-w-0 shrink-0 items-center gap-x-4 overflow-hidden border-t bg-background px-4 text-[11px] text-muted-foreground">
      <ContentItemStatusBadge status={file.status} />
      {currentStage ? (
        <span className="inline-flex shrink-0 items-center gap-1.5">
          <Clock className="h-3 w-3 animate-pulse" />
          {currentStage}
        </span>
      ) : null}
      <span className="hidden shrink-0 items-center rounded-md border px-1.5 py-0.5 text-[10px] sm:inline-flex">
        {translate(`custom.content.details.kind_${file.kind}`, {
          defaultValue: file.extension ?? file.kind ?? "-",
        })}
      </span>
      <span className="inline-flex shrink-0 items-center gap-1.5">
        <HardDrive className="h-3 w-3" />
        {file.size_human}
      </span>
      <span className="hidden shrink-0 items-center gap-1.5 sm:inline-flex">
        <Calendar className="h-3 w-3" />
        {formatDate(file.modified_at)}
      </span>
      {file.processed_at && !isProcessing && (
        <span className="hidden shrink-0 items-center gap-1.5 md:inline-flex">
          <Clock className="h-3 w-3" />
          {translate("custom.content.details.processed_at")}: {formatDate(file.processed_at)}
        </span>
      )}
      {!isProcessing && file.status === "FAILED" ? (
        <span className="inline-flex min-w-0 items-center gap-1.5 text-destructive">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span className="truncate">{flowDescription}</span>
        </span>
      ) : null}

      <span className="ml-auto flex min-w-0 shrink-0 items-center gap-2">
        {hasAttention ? (
          <span
            className="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-amber-300/70 bg-amber-50 px-2 py-0.5 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-100"
            title={flowDescription}
          >
            <AlertTriangle className="h-3 w-3" />
            <span className="truncate">{translate(flow.labelKey)}</span>
          </span>
        ) : (
          <span className="hidden items-center gap-1.5 text-emerald-700 dark:text-emerald-400 sm:inline-flex">
            <CheckCircle2 className="h-3 w-3" />
            {translate("custom.content.details.no_attention_needed")}
          </span>
        )}
      </span>
    </footer>
  );
};
