import { useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle2, CircleAlert, Info, Trash2, TriangleAlert } from "lucide-react";
import { Link } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useGetIdentity, useTranslate } from "@/lib/app-context";
import {
  clearStoredNotifications,
  markStoredNotificationsRead,
  readStoredNotifications,
  subscribeStoredNotifications,
  type StoredNotification,
} from "@/lib/notification-center";
import { cn } from "@/lib/utils";

const iconForType = (type?: string | null) => {
  switch (type) {
    case "success":
      return CheckCircle2;
    case "warning":
      return TriangleAlert;
    case "error":
      return CircleAlert;
    default:
      return Info;
  }
};

const actionHref = (notification: StoredNotification): string | null => {
  const { event } = notification;
  const filePath = event.metadata.file_path;
  if (typeof filePath === "string" && filePath.trim()) {
    return `/content?file=${encodeURIComponent(filePath)}`;
  }
  const conversationId = event.metadata.conversation_id;
  if (typeof conversationId === "string" && conversationId.trim()) {
    return `/chat/${conversationId}`;
  }
  if (event.kind.startsWith("chat.") && event.resource_id) {
    return `/chat/${event.resource_id}`;
  }
  if (event.kind.startsWith("research.")) {
    return "/chat";
  }
  if (event.kind.startsWith("file.")) {
    return "/content";
  }
  return null;
};

const useNotifications = (identityId: string | null) => {
  const [notifications, setNotifications] = useState<StoredNotification[]>(() =>
    identityId ? readStoredNotifications(identityId) : [],
  );

  useEffect(() => {
    if (!identityId) {
      const clearTimer = window.setTimeout(() => setNotifications([]), 0);
      return () => window.clearTimeout(clearTimer);
    }
    const refresh = () => {
      setNotifications(readStoredNotifications(identityId));
    };
    const refreshTimer = window.setTimeout(refresh, 0);
    const unsubscribe = subscribeStoredNotifications(refresh);
    return () => {
      window.clearTimeout(refreshTimer);
      unsubscribe();
    };
  }, [identityId]);

  return notifications;
};

export function NotificationCenter() {
  const translate = useTranslate();
  const { identity } = useGetIdentity();
  const identityId = identity?.id ? String(identity.id) : null;
  const notifications = useNotifications(identityId);
  const unreadCount = useMemo(
    () => notifications.filter((notification) => !notification.read).length,
    [notifications],
  );
  const [open, setOpen] = useState(false);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen && identityId) {
      markStoredNotificationsRead(identityId);
    }
  };

  const handleClear = () => {
    if (identityId) {
      clearStoredNotifications(identityId);
    }
  };

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="relative h-8 w-8 shrink-0"
          aria-label={translate("custom.notification_center.open")}
          title={translate("custom.notification_center.open")}
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          ) : null}
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full p-0 sm:max-w-md">
        <SheetHeader className="border-b pr-12">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SheetTitle>{translate("custom.notification_center.title")}</SheetTitle>
              <SheetDescription>
                {translate("custom.notification_center.description")}
              </SheetDescription>
            </div>
            {notifications.length > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={handleClear}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {translate("custom.notification_center.clear")}
              </Button>
            ) : null}
          </div>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {notifications.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
              <Bell className="h-6 w-6" />
              {translate("custom.notification_center.empty")}
            </div>
          ) : (
            <div className="divide-y">
              {notifications.map((notification) => {
                const descriptor = notification.descriptor;
                const Icon = iconForType(descriptor?.type);
                const href = actionHref(notification);
                const text = descriptor
                  ? translate(descriptor.messageKey, descriptor.messageArgs)
                  : notification.event.kind;
                const createdAt = new Date(
                  notification.event.created_at || notification.received_at,
                );
                const content = (
                  <div className="flex gap-3 p-4 text-left transition-colors hover:bg-muted/60">
                    <Icon
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        descriptor?.type === "success" && "text-emerald-600",
                        descriptor?.type === "warning" && "text-amber-600",
                        descriptor?.type === "error" && "text-destructive",
                      )}
                    />
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-start gap-2">
                        <p className="min-w-0 flex-1 text-sm font-medium leading-snug">{text}</p>
                        {!notification.read ? (
                          <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                            {translate("custom.notification_center.unread")}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="text-xs text-muted-foreground">{createdAt.toLocaleString()}</p>
                    </div>
                  </div>
                );
                return href ? (
                  <Link key={notification.id} to={href} onClick={() => setOpen(false)}>
                    {content}
                  </Link>
                ) : (
                  <div key={notification.id}>{content}</div>
                );
              })}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
