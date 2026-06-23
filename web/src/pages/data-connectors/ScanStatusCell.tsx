import { AlertCircle, CheckCircle2, Loader2, Minus } from "lucide-react";

import { useTranslate } from "@/lib/app-context";
import type { DataConnectorEntry } from "@/api/admin";

const tp = "custom.pages.data_connectors.scan";

export function ScanStatusCell({ source }: { source: DataConnectorEntry }) {
  const translate = useTranslate();
  const counts = translate(`${tp}.counts`, {
    dirs: source.scan_dirs.toLocaleString(),
    queued: source.scan_files_queued.toLocaleString(),
    unchanged: source.scan_files_unchanged.toLocaleString(),
  });

  switch (source.scan_state) {
    case "scanning":
      return (
        <div className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1.5 text-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            {translate(`${tp}.scanning`)}
          </span>
          <span className="text-xs text-muted-foreground">{counts}</span>
        </div>
      );
    case "done":
      return (
        <div className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1.5 text-sm">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            {translate(`${tp}.done`)}
          </span>
          <span className="text-xs text-muted-foreground">{counts}</span>
        </div>
      );
    case "failed":
      return (
        <span className="flex items-center gap-1.5 text-sm text-destructive">
          <AlertCircle className="h-3.5 w-3.5" />
          {translate(`${tp}.failed`)}
        </span>
      );
    default:
      return (
        <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Minus className="h-3.5 w-3.5" />
          {translate(`${tp}.idle`)}
        </span>
      );
  }
}
