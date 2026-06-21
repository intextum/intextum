import { Badge } from "@/components/ui/badge";
import { buildDocumentExtractionHighlights } from "@/lib/content-enrichment";
import { cn } from "@/lib/utils";

interface DocumentExtractionHighlightsProps {
  extraction: unknown;
  className?: string;
  limit?: number;
}

export const DocumentExtractionHighlights = ({
  extraction,
  className,
  limit = 2,
}: DocumentExtractionHighlightsProps) => {
  const highlights = buildDocumentExtractionHighlights(extraction, limit);
  if (highlights.length === 0) {
    return null;
  }

  return (
    <div className={cn("mt-1 flex flex-wrap gap-1", className)}>
      {highlights.map((highlight) => (
        <Badge
          key={highlight.key}
          variant="outline"
          className="max-w-full gap-1 overflow-hidden border-transparent bg-muted/40 px-1.5 py-0 text-[10px] font-normal text-muted-foreground"
          title={`${highlight.label}: ${highlight.value}`}
        >
          <span className="truncate font-mono">{highlight.label}</span>
          <span className="truncate text-foreground/80">{highlight.value}</span>
        </Badge>
      ))}
    </div>
  );
};
