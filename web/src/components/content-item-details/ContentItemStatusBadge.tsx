import { useTranslate } from "@/lib/app-context";
import { Badge } from "@/components/ui/badge";
import { type ContentItemInfo } from "@/dataProvider";
import { contentStatusPresentation, type StatusSeverity } from "@/lib/status-presentations";

interface ContentItemStatusBadgeProps {
  status: ContentItemInfo["status"];
}

export const ContentItemStatusBadge = ({ status }: ContentItemStatusBadgeProps) => {
  const translate = useTranslate();
  const presentation = contentStatusPresentation(status);

  if (!status) return null;

  return (
    <Badge
      variant={presentation.badgeVariant}
      className="h-5 gap-1.5 border-transparent bg-muted/50 px-1.5 font-normal"
    >
      <span
        className={`flex h-2 w-2 rounded-full ${statusDotClass(
          presentation.severity,
          status === "PROCESSING" || status === "RETRYING",
        )}`}
      />
      {translate(presentation.labelKey)}
    </Badge>
  );
};

function statusDotClass(severity: StatusSeverity, animated: boolean): string {
  const color =
    severity === "success"
      ? "bg-emerald-500"
      : severity === "error"
        ? "bg-red-500"
        : severity === "warning"
          ? "bg-amber-400"
          : severity === "info"
            ? "bg-primary"
            : "bg-slate-300";
  return animated ? `${color} animate-pulse` : color;
}
