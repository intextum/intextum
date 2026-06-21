import { Activity, AlertCircle, CheckCircle2, Clock, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslate } from "@/lib/app-context";
import { formatDate } from "@/lib/content-utils";
import type { ContentAuditEventInfo, ContentAuditEventListResponse } from "@/dataProvider";
import {
  auditGroupLabels,
  auditStatusLabels,
  normalizeAuditLabelKey,
} from "./content-audit-labels";

const auditStatusVariant = (
  status: string,
): "default" | "secondary" | "destructive" | "outline" => {
  const normalizedStatus = normalizeAuditLabelKey(status);
  if (normalizedStatus === "failed") return "destructive";
  if (normalizedStatus === "completed") return "default";
  if (normalizedStatus === "cancelled" || normalizedStatus === "revoked") return "outline";
  return "secondary";
};

const auditMetadataLabels: Record<string, string> = {
  changed_fields: "Changed fields",
  classification_label: "Class",
  connector_name: "Connector",
  connector_uuid: "Connector ID",
  content_kind: "Kind",
  destination_path: "Destination",
  display_name: "Name",
  error: "Error",
  fields: "Fields",
  processing_status: "Processing status",
  relative_path: "Path",
  rule_name: "Rule",
  size_bytes: "Size",
  task_id: "Task",
  target_connector_uuid: "Target connector",
};

const humanizeAuditKey = (key: string): string =>
  auditMetadataLabels[key] ??
  key.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());

const compactAuditValue = (value: unknown, depth = 0): string => {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "-";
    }
    if (value.every((item) => typeof item !== "object" || item === null)) {
      return value.map((item) => compactAuditValue(item, depth + 1)).join(", ");
    }
    return `${value.length} items`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value).filter(
      ([, entryValue]) => entryValue !== null && entryValue !== undefined && entryValue !== "",
    );
    if (entries.length === 0) {
      return "-";
    }
    if (depth > 0) {
      return `${entries.length} fields`;
    }
    const preview = entries
      .slice(0, 3)
      .map(([key, entryValue]) => `${humanizeAuditKey(key)}: ${compactAuditValue(entryValue, 1)}`);
    return entries.length > 3 ? `${preview.join("; ")} +${entries.length - 3}` : preview.join("; ");
  }
  return String(value);
};

const AuditEventIcon = ({ event }: { event: ContentAuditEventInfo }) => {
  const normalizedStatus = normalizeAuditLabelKey(event.status);
  if (normalizedStatus === "failed") return <XCircle className="h-4 w-4 text-destructive" />;
  if (normalizedStatus === "completed") {
    return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
  }
  if (normalizedStatus === "processing" || normalizedStatus === "queued") {
    return <Clock className="h-4 w-4 text-blue-600" />;
  }
  if (event.event_group === "review" || event.event_group === "enrichment") {
    return <AlertCircle className="h-4 w-4 text-amber-600" />;
  }
  return <Activity className="h-4 w-4 text-muted-foreground" />;
};

const formatAuditMetadata = (metadata: Record<string, unknown>) =>
  Object.entries(metadata)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .slice(0, 6)
    .map(([key, value]) => [humanizeAuditKey(key), compactAuditValue(value)] as const);

interface ContentAuditActivityProps {
  data: ContentAuditEventListResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  events?: ContentAuditEventInfo[];
  emptyMessage?: string;
}

export const ContentAuditActivity = ({
  data,
  loading,
  error,
  onRetry,
  events: filteredEvents,
  emptyMessage,
}: ContentAuditActivityProps) => {
  const translate = useTranslate();
  const events = filteredEvents ?? data?.events ?? [];
  const auditStatusLabel = (status: string) => {
    const labelKey = normalizeAuditLabelKey(status);
    return translate(`custom.content.audit.status.${labelKey}`, {
      _: auditStatusLabels[labelKey] ?? status,
    });
  };
  const auditGroupLabel = (group: string) => {
    const labelKey = normalizeAuditLabelKey(group);
    return translate(`custom.content.audit.group.${labelKey}`, {
      _: auditGroupLabels[labelKey] ?? group,
    });
  };

  if (loading && events.length === 0) {
    return (
      <div className="space-y-3 p-4">
        {[0, 1, 2].map((item) => (
          <div key={item} className="h-20 animate-pulse rounded-lg border bg-muted/30" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <div className="font-medium text-destructive">
            {translate("custom.content.audit.load_failed")}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{error}</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            {translate("custom.content.audit.retry")}
          </Button>
        </div>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="p-4">
        <div className="rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
          {emptyMessage ?? translate("custom.content.audit.empty")}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-4">
      {events.map((event) => {
        const metadata = formatAuditMetadata(event.metadata ?? {});
        return (
          <div key={event.id} className="rounded-lg border bg-background p-3 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                <AuditEventIcon event={event} />
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="min-w-0 flex-1 truncate font-medium">{event.summary}</div>
                  <Badge variant={auditStatusVariant(event.status)}>
                    {auditStatusLabel(event.status)}
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>{formatDate(event.created_at)}</span>
                  {event.actor_name || event.actor_sub ? (
                    <span>{event.actor_name ?? event.actor_sub}</span>
                  ) : null}
                  <span>{auditGroupLabel(event.event_group)}</span>
                </div>
                {metadata.length > 0 ? (
                  <div className="grid gap-1 rounded-md bg-muted/30 p-2 text-xs">
                    {metadata.map(([key, value]) => (
                      <div key={key} className="grid grid-cols-[7rem_1fr] gap-2">
                        <span className="truncate text-muted-foreground">{key}</span>
                        <span className="min-w-0 break-words">{value}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
      {data && data.total > (data.offset ?? 0) + (data.events?.length ?? 0) ? (
        <div className="text-center text-xs text-muted-foreground">
          {translate("custom.content.audit.showing_count", {
            count: (data.offset ?? 0) + (data.events?.length ?? 0),
            total: data.total,
          })}
        </div>
      ) : null}
    </div>
  );
};
