import type { UserEvent } from "@/dataProvider";
import { describeUserEvent, type UserEventNotificationDescriptor } from "@/lib/user-events";

const NOTIFICATION_CENTER_EVENT = "app:notification-center-changed";
const MAX_STORED_NOTIFICATIONS = 50;

export type StoredNotification = {
  id: string;
  event: UserEvent;
  descriptor: UserEventNotificationDescriptor | null;
  read: boolean;
  received_at: string;
};

const storageKey = (identityId: string) => `notification-center:v1:${identityId}`;

const notificationId = (event: UserEvent) =>
  event.event_id ||
  [event.kind, event.resource_type, event.resource_id, event.created_at].filter(Boolean).join(":");

export function readStoredNotifications(identityId: string): StoredNotification[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(storageKey(identityId));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter(
          (item): item is StoredNotification =>
            item &&
            typeof item === "object" &&
            typeof item.id === "string" &&
            typeof item.received_at === "string" &&
            typeof item.read === "boolean" &&
            "event" in item,
        )
      : [];
  } catch {
    return [];
  }
}

function writeStoredNotifications(identityId: string, notifications: StoredNotification[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(
    storageKey(identityId),
    JSON.stringify(notifications.slice(0, MAX_STORED_NOTIFICATIONS)),
  );
  window.dispatchEvent(new Event(NOTIFICATION_CENTER_EVENT));
}

export function recordStoredNotification(identityId: string, event: UserEvent) {
  const id = notificationId(event);
  if (!id) {
    return;
  }
  const current = readStoredNotifications(identityId);
  if (current.some((item) => item.id === id)) {
    return;
  }
  writeStoredNotifications(identityId, [
    {
      id,
      event,
      descriptor: describeUserEvent(event),
      read: false,
      received_at: new Date().toISOString(),
    },
    ...current,
  ]);
}

export function markStoredNotificationsRead(identityId: string) {
  const current = readStoredNotifications(identityId);
  if (current.every((item) => item.read)) {
    return;
  }
  writeStoredNotifications(
    identityId,
    current.map((item) => ({ ...item, read: true })),
  );
}

export function clearStoredNotifications(identityId: string) {
  writeStoredNotifications(identityId, []);
}

export function subscribeStoredNotifications(listener: () => void) {
  window.addEventListener(NOTIFICATION_CENTER_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(NOTIFICATION_CENTER_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
