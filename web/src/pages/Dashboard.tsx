/**
 * Dashboard landing page.
 */
import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslate, useGetIdentity, useNotify } from "@/lib/app-context";
import {
  ArrowRight,
  FileText,
  History,
  LayoutDashboard,
  MessageSquarePlus,
  Search,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/content-explorer/StatsCards";
import { RecentFilesTable } from "@/components/dashboard/RecentFilesTable";
import { ContentItemDetailsDialog } from "@/components/ContentItemDetailsDialog";
import { EmptyState } from "@/components/page/EmptyState";
import { LoadingState } from "@/components/page/LoadingState";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import { contentApi, type ContentItemInfo } from "@/dataProvider";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { queryKeys } from "@/lib/query-client";
import { Link } from "react-router";

export const DashboardPage = () => {
  const translate = useTranslate();
  useDocumentTitle(translate("custom.pages.dashboard.title"));
  const { identity } = useGetIdentity();
  const notify = useNotify();
  const recentFilesQuery = useQuery({
    queryKey: queryKeys.content.recent(5),
    queryFn: () => contentApi.getRecent(5),
  });
  const { refetch: refetchRecentFiles } = recentFilesQuery;
  const recentFiles = recentFilesQuery.data ?? [];

  // Preview state
  const [selectedFile, setSelectedFile] = useState<ContentItemInfo | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const handleFileClick = (file: ContentItemInfo) => {
    setSelectedFile(file);
    setDetailsOpen(true);
  };

  const handleProcess = useCallback(
    async (path: string, processingConfig?: Record<string, unknown>) => {
      try {
        const result = await contentApi.triggerProcess(path, processingConfig);
        notify(translate("custom.processing_started", { id: result.task_id }), {
          type: "success",
        });
        await refetchRecentFiles();
        return true;
      } catch {
        notify(translate("custom.failed_to_start_processing"), { type: "error" });
        return false;
      }
    },
    [notify, refetchRecentFiles, translate],
  );

  return (
    <PageShell contentClassName="space-y-8">
      <PageHeader
        icon={LayoutDashboard}
        title={translate("custom.pages.dashboard.title")}
        description={translate("custom.pages.dashboard.welcome", {
          name: identity?.fullName || "",
        })}
      />

      <section className="grid gap-3 sm:grid-cols-3">
        <Button asChild className="h-auto justify-start gap-3 px-4 py-3">
          <Link to="/content?upload=true">
            <Upload className="h-4 w-4" />
            <span>{translate("custom.pages.dashboard.quick_upload")}</span>
          </Link>
        </Button>
        <Button asChild variant="outline" className="h-auto justify-start gap-3 px-4 py-3">
          <Link to="/search">
            <Search className="h-4 w-4" />
            <span>{translate("custom.pages.dashboard.quick_search")}</span>
          </Link>
        </Button>
        <Button asChild variant="outline" className="h-auto justify-start gap-3 px-4 py-3">
          <Link to="/chat">
            <MessageSquarePlus className="h-4 w-4" />
            <span>{translate("custom.pages.dashboard.quick_chat")}</span>
          </Link>
        </Button>
      </section>

      <section className="space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          <History className="h-4 w-4 text-muted-foreground" />
          {translate("custom.pages.dashboard.system_overview")}
        </div>
        <StatsCards global />
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            <FileText className="h-4 w-4 text-muted-foreground" />
            {translate("custom.pages.dashboard.recently_indexed")}
          </div>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/content" className="flex items-center gap-1">
              {translate("custom.pages.dashboard.view_all_files")}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>

        <div className="grid gap-4">
          {recentFilesQuery.isLoading ? (
            <LoadingState rows={3} />
          ) : recentFiles.length === 0 ? (
            <EmptyState
              icon={FileText}
              title={translate("custom.pages.dashboard.no_recent_files")}
              description={translate("custom.pages.dashboard.no_recent_files_hint")}
              actions={
                <Button asChild>
                  <Link to="/content">{translate("custom.pages.dashboard.view_all_files")}</Link>
                </Button>
              }
            />
          ) : (
            <RecentFilesTable files={recentFiles} onFileClick={handleFileClick} />
          )}
        </div>
      </section>

      <ContentItemDetailsDialog
        file={selectedFile}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        onProcess={handleProcess}
      />
    </PageShell>
  );
};
