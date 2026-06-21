import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useNotify, useTranslate } from "@/lib/app-context";
import { conversationsApi } from "@/dataProvider";
import { invalidateConversationQueries, queryKeys } from "@/lib/query-client";
import { History, MessageSquareWarning, Trash2 } from "lucide-react";

const DEFAULT_CONFIRM_TEXT = "DELETE";
const DEFAULT_DELETE_OLDER_DAYS = "30";

export function ChatDataSettingsPanel() {
  const translate = useTranslate();
  const notify = useNotify();
  const navigate = useNavigate();
  const translatedConfirmText = String(translate("custom.pages.settings.chat_data.confirm_text"));
  const confirmTextValue =
    translatedConfirmText === "custom.pages.settings.chat_data.confirm_text"
      ? DEFAULT_CONFIRM_TEXT
      : translatedConfirmText;

  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false);
  const [deleteOlderDialogOpen, setDeleteOlderDialogOpen] = useState(false);
  const [confirmDeleteAllText, setConfirmDeleteAllText] = useState("");
  const [confirmDeleteOlderText, setConfirmDeleteOlderText] = useState("");
  const [olderThanDays, setOlderThanDays] = useState(DEFAULT_DELETE_OLDER_DAYS);
  const [deletingAll, setDeletingAll] = useState(false);
  const [deletingOlder, setDeletingOlder] = useState(false);
  const conversationCountQuery = useQuery({
    queryKey: queryKeys.conversations.list(1, 0),
    queryFn: () => conversationsApi.list(1, 0),
  });
  const { refetch: refetchConversationCount } = conversationCountQuery;
  const conversationCount = conversationCountQuery.data?.total ?? 0;
  const loadingCount = conversationCountQuery.isLoading;

  useEffect(() => {
    if (conversationCountQuery.error) {
      notify(translate("custom.pages.settings.chat_data.failed_to_load_count"), { type: "error" });
    }
  }, [conversationCountQuery.error, notify, translate]);

  const openDeleteAllDialog = () => {
    setConfirmDeleteAllText("");
    setDeleteAllDialogOpen(true);
  };

  const handleDeleteAll = async () => {
    if (confirmDeleteAllText !== confirmTextValue) {
      return;
    }

    setDeletingAll(true);
    try {
      const result = await conversationsApi.deleteAll();
      setDeleteAllDialogOpen(false);
      void invalidateConversationQueries();
      void refetchConversationCount();
      navigate("/chat", { replace: true });
      notify(
        translate("custom.pages.settings.chat_data.delete_all_success", {
          count: result.deleted_count,
        }),
        { type: "info" },
      );
    } catch {
      notify(translate("custom.pages.settings.chat_data.delete_all_failed"), { type: "error" });
    } finally {
      setDeletingAll(false);
    }
  };

  const openDeleteOlderDialog = () => {
    setConfirmDeleteOlderText("");
    setDeleteOlderDialogOpen(true);
  };

  const handleDeleteOlder = async () => {
    if (confirmDeleteOlderText !== confirmTextValue) {
      return;
    }

    const days = Number.parseInt(olderThanDays, 10);
    if (!Number.isFinite(days) || days < 1) {
      notify(translate("custom.pages.settings.chat_data.invalid_days"), { type: "error" });
      return;
    }

    setDeletingOlder(true);
    try {
      const cutoff = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
      const result = await conversationsApi.deleteOlder(cutoff);
      setDeleteOlderDialogOpen(false);
      void invalidateConversationQueries();
      void refetchConversationCount();
      if (result.deleted_count > 0) {
        navigate("/chat", { replace: true });
      }
      notify(
        translate("custom.pages.settings.chat_data.delete_older_success", {
          count: result.deleted_count,
          days,
        }),
        { type: "info" },
      );
    } catch {
      notify(translate("custom.pages.settings.chat_data.delete_older_failed"), { type: "error" });
    } finally {
      setDeletingOlder(false);
    }
  };

  const hasConversations = conversationCount > 0;
  const countLabel = loadingCount
    ? translate("custom.pages.settings.chat_data.loading_count")
    : translate("custom.pages.settings.chat_data.total_chats", { count: conversationCount });

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <MessageSquareWarning className="h-5 w-5 text-muted-foreground" />
            <h3 className="text-lg font-medium">
              {translate("custom.pages.settings.chat_data.title")}
            </h3>
          </div>
          <p className="text-sm text-muted-foreground">
            {translate("custom.pages.settings.chat_data.description")}
          </p>
        </div>
        <Separator />
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="rounded-lg border bg-muted/30 p-4">
              <p className="text-sm font-medium">
                {translate("custom.pages.settings.chat_data.summary_title")}
              </p>
              <p className="mt-2 text-2xl font-semibold tracking-tight">{conversationCount}</p>
              <p className="mt-1 text-sm text-muted-foreground">{countLabel}</p>
            </div>

            <div className="rounded-lg border border-destructive/25 bg-destructive/5 p-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="destructive">
                    {translate("custom.pages.settings.chat_data.danger_badge")}
                  </Badge>
                  <p className="text-sm font-medium">
                    {translate("custom.pages.settings.chat_data.danger_title")}
                  </p>
                </div>
                <p className="text-sm text-muted-foreground">
                  {translate("custom.pages.settings.chat_data.danger_description")}
                </p>
              </div>
              <Separator className="my-4" />
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <Button
                  variant="outline"
                  onClick={openDeleteOlderDialog}
                  disabled={loadingCount || !hasConversations || deletingAll || deletingOlder}
                >
                  <History className="mr-2 h-4 w-4" />
                  {translate("custom.pages.settings.chat_data.delete_older_button")}
                </Button>
                <Button
                  variant="destructive"
                  onClick={openDeleteAllDialog}
                  disabled={loadingCount || !hasConversations || deletingAll || deletingOlder}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {translate("custom.pages.settings.chat_data.delete_all_button")}
                </Button>
              </div>
            </div>
          </div>

          {!hasConversations && !loadingCount ? (
            <Alert>
              <AlertTitle>{translate("custom.pages.settings.chat_data.empty_title")}</AlertTitle>
              <AlertDescription>
                {translate("custom.pages.settings.chat_data.empty_description")}
              </AlertDescription>
            </Alert>
          ) : null}
        </div>
      </section>

      <Dialog open={deleteOlderDialogOpen} onOpenChange={setDeleteOlderDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.settings.chat_data.delete_older_title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.settings.chat_data.delete_older_prompt", {
                count: conversationCount,
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="delete-older-days-input">
              {translate("custom.pages.settings.chat_data.days_label")}
            </Label>
            <Input
              id="delete-older-days-input"
              type="number"
              min={1}
              value={olderThanDays}
              onChange={(event) => setOlderThanDays(event.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="delete-older-confirm-input">
              {translate("custom.pages.settings.chat_data.confirm_label", {
                text: confirmTextValue,
              })}
            </Label>
            <Input
              id="delete-older-confirm-input"
              value={confirmDeleteOlderText}
              onChange={(event) => setConfirmDeleteOlderText(event.target.value)}
              autoComplete="off"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteOlderDialogOpen(false)}
              disabled={deletingOlder}
            >
              {translate("custom.pages.settings.chat_data.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteOlder}
              disabled={confirmDeleteOlderText !== confirmTextValue || deletingOlder}
            >
              {deletingOlder
                ? translate("custom.pages.settings.chat_data.deleting_older")
                : translate("custom.pages.settings.chat_data.confirm_delete_older")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteAllDialogOpen} onOpenChange={setDeleteAllDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.settings.chat_data.delete_all_title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.settings.chat_data.delete_all_prompt", {
                count: conversationCount,
                text: confirmTextValue,
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="delete-all-confirm-input">
              {translate("custom.pages.settings.chat_data.confirm_label", {
                text: confirmTextValue,
              })}
            </Label>
            <Input
              id="delete-all-confirm-input"
              value={confirmDeleteAllText}
              onChange={(event) => setConfirmDeleteAllText(event.target.value)}
              autoComplete="off"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteAllDialogOpen(false)}
              disabled={deletingAll}
            >
              {translate("custom.pages.settings.chat_data.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteAll}
              disabled={confirmDeleteAllText !== confirmTextValue || deletingAll}
            >
              {deletingAll
                ? translate("custom.pages.settings.chat_data.deleting")
                : translate("custom.pages.settings.chat_data.confirm_delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
