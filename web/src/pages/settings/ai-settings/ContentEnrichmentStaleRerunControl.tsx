import { Button } from "@/components/ui/button";

type Translate = (key: string, options?: unknown) => string;

interface ContentEnrichmentStaleRerunControlProps {
  translate: Translate;
  staleCount: number;
  rerunningStaleEnrichment: boolean;
  onRerunStaleEnrichment: (staleCount: number) => void;
}

export function ContentEnrichmentStaleRerunControl({
  translate,
  staleCount,
  rerunningStaleEnrichment,
  onRerunStaleEnrichment,
}: ContentEnrichmentStaleRerunControlProps) {
  return (
    <Button
      size="sm"
      onClick={() => onRerunStaleEnrichment(staleCount)}
      disabled={rerunningStaleEnrichment}
    >
      {rerunningStaleEnrichment
        ? translate("custom.pages.settings.ai.content_enrichment_editor.stale_queue_rerunning")
        : translate("custom.pages.settings.ai.content_enrichment_editor.stale_queue_rerun")}
    </Button>
  );
}
