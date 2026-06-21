import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageShell } from "@/components/page/PageShell";
import { ContentItemDetailsContent } from "@/components/content-item-details/ContentItemDetailsContent";
import { ContentItemBreadcrumb } from "@/components/content-item-details/ContentItemBreadcrumb";
import { BreadcrumbPortal } from "@/components/app/BreadcrumbPortal";
import { contentApi } from "@/dataProvider";
import { useNotify, useTranslate } from "@/lib/app-context";
import { getContentItemDisplayName } from "@/lib/content-utils";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { queryKeys } from "@/lib/query-client";
import { reportClientError } from "@/lib/report-client-error";
import type { ProcessingConfigPayload } from "@/hooks/useContentItemDetails";

export const ContentItemPage = () => {
  const { id = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const notify = useNotify();
  const translate = useTranslate();
  const queryClient = useQueryClient();
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const from = searchParams.get("from");
  const fileQuery = useQuery({
    queryKey: queryKeys.content.detailsById(id),
    enabled: Boolean(id),
    queryFn: () => contentApi.getDetailsById(id),
  });
  const { refetch: refetchFile } = fileQuery;
  const file = fileQuery.data ?? null;
  const error =
    !id && !fileQuery.isLoading
      ? translate("custom.file_not_found")
      : fileQuery.error
        ? fileQuery.error instanceof Error
          ? fileQuery.error.message
          : String(fileQuery.error)
        : null;

  useDocumentTitle(
    file
      ? getContentItemDisplayName(file)
      : translate("custom.content.details.full_view", { defaultValue: "Content details" }),
  );

  const returnTarget = useMemo(() => {
    if (from?.startsWith("/")) {
      return from;
    }
    return "/content";
  }, [from]);

  const handleProcess = useCallback(
    async (path: string, processingConfig?: ProcessingConfigPayload) => {
      try {
        const result = await contentApi.triggerProcess(path, processingConfig);
        notify(translate("custom.processing_started", { id: result.task_id }), { type: "success" });
        await refetchFile();
        return true;
      } catch (err) {
        notify(err instanceof Error ? err.message : String(err), { type: "error" });
        return false;
      }
    },
    [notify, refetchFile, translate],
  );

  const handleDelete = useCallback((_path: string) => {
    setDeleteConfirmOpen(true);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!file) return;
    setDeletePending(true);
    try {
      await contentApi.deleteFile(file.path);
      notify(translate("custom.content.delete.success"), { type: "success" });
      void queryClient.invalidateQueries({ queryKey: queryKeys.content.all });
      navigate(returnTarget);
    } catch (err) {
      reportClientError(err, undefined, { routeName: "content-item:delete" });
      notify(translate("custom.content.delete.failed"), { type: "error" });
      setDeleteConfirmOpen(false);
    } finally {
      setDeletePending(false);
    }
  }, [file, navigate, notify, queryClient, returnTarget, translate]);

  const handleOpenActivity = useCallback(() => {
    if (!file) return;
    navigate(`/content/item/${encodeURIComponent(file.id)}/activity`);
  }, [file, navigate]);

  return (
    <PageShell
      scroll={false}
      className="min-h-0 overflow-hidden"
      contentClassName="flex h-full max-w-none flex-col space-y-0 overflow-hidden p-0 md:p-0"
    >
      {fileQuery.isLoading ? (
        <div className="flex h-full items-center justify-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>{translate("custom.content.details.loading")}</span>
        </div>
      ) : error || !file ? (
        <>
          <BreadcrumbPortal>
            <div className="order-1 min-w-0 flex-1 overflow-hidden">
              <ContentItemBreadcrumb
                currentLabel={translate("custom.content.details.full_view", {
                  defaultValue: "Content details",
                })}
              />
            </div>
          </BreadcrumbPortal>
          <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
            <Alert variant="destructive">
              <AlertDescription>{error ?? translate("custom.file_not_found")}</AlertDescription>
            </Alert>
          </div>
        </>
      ) : (
        <>
          <BreadcrumbPortal>
            <div className="order-1 min-w-0 flex-1 overflow-hidden">
              <ContentItemBreadcrumb file={file} />
            </div>
          </BreadcrumbPortal>
          <div className="min-h-0 flex-1 overflow-hidden">
            <ContentItemDetailsContent
              key={file.id}
              initialFile={file}
              open
              hideIdentity
              onProcess={handleProcess}
              onDelete={handleDelete}
              onOpenActivity={handleOpenActivity}
            />
          </div>
        </>
      )}

      <Dialog
        open={deleteConfirmOpen}
        onOpenChange={(open) => {
          if (!deletePending) setDeleteConfirmOpen(open);
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {translate("custom.content.delete.confirm_title", { defaultValue: "Delete file" })}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.content.delete.confirm_message", {
                name: file ? getContentItemDisplayName(file) : "",
                defaultValue: "This cannot be undone.",
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteConfirmOpen(false)}
              disabled={deletePending}
            >
              {translate("ra.action.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => void handleDeleteConfirm()}
              disabled={deletePending}
            >
              {translate("custom.content.delete.confirm_action", { defaultValue: "Delete" })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};
