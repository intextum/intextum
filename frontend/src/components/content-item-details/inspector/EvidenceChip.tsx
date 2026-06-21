import { MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslate } from "@/lib/app-context";

interface EvidenceChipProps {
  docRefs: string[];
  label: string;
  onNavigate?: (docRefs: string[], label: string) => void;
}

export const EvidenceChip = ({ docRefs, label, onNavigate }: EvidenceChipProps) => {
  const translate = useTranslate();
  if (!onNavigate || docRefs.length === 0) return null;
  const evidenceLabel = translate("custom.content.details.open_evidence");
  const title =
    docRefs.length > 1
      ? `${evidenceLabel}: ${label} (${docRefs.length})`
      : `${evidenceLabel}: ${label}`;
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-6 w-6 text-muted-foreground hover:text-foreground"
      onClick={() => onNavigate(docRefs, label)}
      title={title}
      aria-label={title}
    >
      <MapPin className="h-3 w-3" />
      {docRefs.length > 1 ? (
        <span className="sr-only">
          {translate("custom.content.details.evidence_count", { count: docRefs.length })}
        </span>
      ) : null}
    </Button>
  );
};
