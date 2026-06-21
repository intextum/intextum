import { AlertTriangle } from "lucide-react";
import { useTranslate } from "@/lib/app-context";

import { Badge } from "@/components/ui/badge";
import { type ContentEnrichmentLifecycleInfo } from "@/dataProvider";
import {
  getDocumentClassificationLabel,
  hasStaleContentEnrichment,
  isUserCorrectedClassification,
} from "@/lib/content-enrichment";
import { cn } from "@/lib/utils";

interface DocumentClassBadgeProps {
  classification: unknown;
  classificationLifecycle?: ContentEnrichmentLifecycleInfo | null;
  extractionLifecycle?: ContentEnrichmentLifecycleInfo | null;
  className?: string;
}

export const DocumentClassBadge = ({
  classification,
  classificationLifecycle,
  extractionLifecycle,
  className,
}: DocumentClassBadgeProps) => {
  const translate = useTranslate();
  const label = getDocumentClassificationLabel(classification);
  const isStale = hasStaleContentEnrichment(classificationLifecycle, extractionLifecycle);
  const badgeLabel =
    label || (isStale ? translate("custom.content.details.stale_refresh_short") : null);
  if (!badgeLabel) {
    return null;
  }

  const isCorrection = isUserCorrectedClassification(classification);

  return (
    <Badge
      variant={isStale ? "outline" : isCorrection ? "default" : "secondary"}
      className={cn(
        "max-w-full truncate text-[10px] font-medium",
        isStale
          ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/70 dark:bg-amber-950/30 dark:text-amber-100"
          : isCorrection
            ? "border-transparent"
            : "border-transparent bg-muted/60 text-muted-foreground",
        className,
      )}
      title={
        isStale && label
          ? `${label} · ${translate("custom.content.details.stale_refresh_short")}`
          : badgeLabel
      }
    >
      {isStale && <AlertTriangle className="mr-1 h-3 w-3 shrink-0" />}
      {badgeLabel}
    </Badge>
  );
};
