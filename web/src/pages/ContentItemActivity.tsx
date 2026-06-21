import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useSearchParams } from "react-router";
import { Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ContentAuditActivity } from "@/components/content-item-details/ContentAuditActivity";
import { ContentItemBreadcrumb } from "@/components/content-item-details/ContentItemBreadcrumb";
import {
  auditGroupLabels,
  auditStatusLabels,
  normalizeAuditLabelKey,
} from "@/components/content-item-details/content-audit-labels";
import { PageShell } from "@/components/page/PageShell";
import { contentApi } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { getContentItemDisplayName } from "@/lib/content-utils";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { queryKeys } from "@/lib/query-client";

const AUDIT_PAGE_SIZE = 50;
const ALL_VALUE = "__all";

const parseOffset = (value: string | null) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
};

export const ContentItemActivityPage = () => {
  const { id = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const translate = useTranslate();

  const groupFilter = searchParams.get("group") ?? "";
  const statusFilter = searchParams.get("status") ?? "";
  const offset = parseOffset(searchParams.get("offset"));
  const filtersActive = Boolean(groupFilter || statusFilter);
  const auditParams = useMemo(
    () => ({
      limit: AUDIT_PAGE_SIZE,
      offset,
    }),
    [offset],
  );
  const fileQuery = useQuery({
    queryKey: queryKeys.content.detailsById(id),
    enabled: Boolean(id),
    queryFn: () => contentApi.getDetailsById(id),
  });
  const file = fileQuery.data ?? null;
  const fileError =
    !id && !fileQuery.isLoading
      ? translate("custom.file_not_found")
      : fileQuery.error
        ? fileQuery.error instanceof Error
          ? fileQuery.error.message
          : String(fileQuery.error)
        : null;
  const auditQuery = useQuery({
    queryKey: file
      ? queryKeys.content.audit(file.path, auditParams)
      : queryKeys.content.audit("", auditParams),
    enabled: Boolean(file),
    queryFn: () => contentApi.listAudit(file?.path ?? "", auditParams),
  });
  const { refetch: refetchAudit } = auditQuery;
  const auditData = auditQuery.data ?? null;
  const auditError = auditQuery.error
    ? auditQuery.error instanceof Error
      ? auditQuery.error.message
      : String(auditQuery.error)
    : null;

  useDocumentTitle(
    file
      ? `${getContentItemDisplayName(file)} - ${translate("custom.content.audit.title")}`
      : translate("custom.content.audit.title"),
  );

  const updateSearch = useCallback(
    (updates: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(updates).forEach(([key, value]) => {
        if (!value) {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      });
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  const pageEvents = useMemo(() => auditData?.events ?? [], [auditData?.events]);
  const filteredEvents = useMemo(
    () =>
      pageEvents.filter(
        (event) =>
          (!groupFilter || event.event_group === groupFilter) &&
          (!statusFilter || event.status === statusFilter),
      ),
    [groupFilter, pageEvents, statusFilter],
  );
  const groupOptions = useMemo(
    () =>
      Array.from(
        new Set([groupFilter, ...pageEvents.map((event) => event.event_group)].filter(Boolean)),
      ).sort(),
    [groupFilter, pageEvents],
  );
  const statusOptions = useMemo(
    () =>
      Array.from(
        new Set([statusFilter, ...pageEvents.map((event) => event.status)].filter(Boolean)),
      ).sort(),
    [pageEvents, statusFilter],
  );

  const groupLabel = (group: string) => {
    const labelKey = normalizeAuditLabelKey(group);
    return translate(`custom.content.audit.group.${labelKey}`, {
      _: auditGroupLabels[labelKey] ?? group,
    });
  };
  const statusLabel = (status: string) => {
    const labelKey = normalizeAuditLabelKey(status);
    return translate(`custom.content.audit.status.${labelKey}`, {
      _: auditStatusLabels[labelKey] ?? status,
    });
  };
  const canPageBackward = offset > 0;
  const canPageForward = Boolean(auditData && offset + auditData.events.length < auditData.total);

  return (
    <PageShell contentClassName="flex max-w-none flex-col gap-4 p-4 md:p-6">
      <ContentItemBreadcrumb file={file} tailLabel={translate("custom.content.audit.title")} />

      {fileQuery.isLoading ? (
        <div className="flex min-h-[16rem] items-center justify-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>{translate("custom.content.details.loading")}</span>
        </div>
      ) : fileError || !file ? (
        <Alert variant="destructive">
          <AlertDescription>{fileError ?? translate("custom.file_not_found")}</AlertDescription>
        </Alert>
      ) : (
        <>
          <Card className="shadow-sm">
            <CardContent className="flex flex-col gap-3 p-3 sm:flex-row sm:items-end">
              <div className="grid flex-1 gap-1.5">
                <Label htmlFor="activity-group-filter">
                  {translate("custom.content.audit.group_filter")}
                </Label>
                <Select
                  value={groupFilter || ALL_VALUE}
                  onValueChange={(value) =>
                    updateSearch({
                      group: value === ALL_VALUE ? null : value,
                      offset: null,
                    })
                  }
                >
                  <SelectTrigger id="activity-group-filter">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_VALUE}>
                      {translate("custom.content.audit.all_groups")}
                    </SelectItem>
                    {groupOptions.map((group) => (
                      <SelectItem key={group} value={group}>
                        {groupLabel(group)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid flex-1 gap-1.5">
                <Label htmlFor="activity-status-filter">
                  {translate("custom.content.audit.status_filter")}
                </Label>
                <Select
                  value={statusFilter || ALL_VALUE}
                  onValueChange={(value) =>
                    updateSearch({
                      status: value === ALL_VALUE ? null : value,
                      offset: null,
                    })
                  }
                >
                  <SelectTrigger id="activity-status-filter">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_VALUE}>
                      {translate("custom.content.audit.all_statuses")}
                    </SelectItem>
                    {statusOptions.map((status) => (
                      <SelectItem key={status} value={status}>
                        {statusLabel(status)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                type="button"
                variant="outline"
                className="sm:w-auto"
                disabled={!filtersActive}
                onClick={() => updateSearch({ group: null, status: null, offset: null })}
              >
                {translate("custom.content.audit.clear_filters")}
              </Button>
            </CardContent>
          </Card>

          <ContentAuditActivity
            data={auditData}
            loading={auditQuery.isLoading || (!auditData && !auditError)}
            error={auditError}
            events={filteredEvents}
            emptyMessage={
              filtersActive && pageEvents.length > 0
                ? translate("custom.content.audit.no_filtered_events")
                : undefined
            }
            onRetry={() => void refetchAudit()}
          />

          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!canPageBackward || auditQuery.isLoading}
              onClick={() =>
                updateSearch({ offset: String(Math.max(0, offset - AUDIT_PAGE_SIZE)) })
              }
            >
              {translate("custom.content.audit.previous_page")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!canPageForward || auditQuery.isLoading}
              onClick={() => updateSearch({ offset: String(offset + AUDIT_PAGE_SIZE) })}
            >
              {translate("custom.content.audit.next_page")}
            </Button>
          </div>
        </>
      )}
    </PageShell>
  );
};
