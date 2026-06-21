import type { NotificationPreferences, UserEvent } from "../dataProvider.ts";

export type NotificationKind = "success" | "error" | "info" | "warning";

export interface UserEventNotificationDescriptor {
  messageKey: string;
  messageArgs?: Record<string, unknown>;
  type: NotificationKind;
}

export const defaultNotificationPreferences = (): NotificationPreferences => ({
  chat: {
    completed: true,
    failed: true,
    cancelled: false,
  },
  content_processing: {
    completed: false,
    failed: true,
  },
  research: {
    completed: true,
    failed: true,
    cancelled: false,
  },
});

export const userEventStorageKey = (identityId: string): string =>
  `user-events:last-id:${identityId}`;

export type UserEventRefreshTarget = "content" | "conversations" | "research";

export const shouldNotifyForUserEvent = (
  preferences: NotificationPreferences,
  event: UserEvent,
): boolean => {
  switch (event.kind) {
    case "chat.run.completed":
      return preferences.chat.completed;
    case "chat.run.failed":
      return preferences.chat.failed;
    case "chat.run.cancelled":
      return preferences.chat.cancelled;
    case "file.process.completed":
      return preferences.content_processing.completed;
    case "file.process.failed":
      return preferences.content_processing.failed;
    case "research.run.completed":
      return preferences.research.completed;
    case "research.run.failed":
      return preferences.research.failed;
    case "research.run.cancelled":
      return preferences.research.cancelled;
    default:
      return true;
  }
};

export const refreshTargetsForUserEvent = (event: UserEvent): UserEventRefreshTarget[] => {
  switch (event.kind) {
    case "chat.run.completed":
    case "chat.run.failed":
    case "chat.run.cancelled":
      return ["conversations"];
    case "file.process.completed":
    case "file.process.failed":
      return ["content"];
    case "research.run.completed":
    case "research.run.failed":
    case "research.run.cancelled":
      return ["research"];
    default:
      return [];
  }
};

const filePathArg = (event: UserEvent): Record<string, unknown> => {
  const filePath = event.metadata.file_path;
  return typeof filePath === "string" && filePath ? { file_path: filePath } : {};
};

export const describeUserEvent = (event: UserEvent): UserEventNotificationDescriptor | null => {
  switch (event.kind) {
    case "chat.run.completed":
      return {
        messageKey: "custom.pages.notifications.chat.completed",
        type: "success",
      };
    case "chat.run.failed":
      return {
        messageKey: "custom.pages.notifications.chat.failed",
        type: "error",
      };
    case "chat.run.cancelled":
      return {
        messageKey: "custom.pages.notifications.chat.cancelled",
        type: "info",
      };
    case "file.process.completed":
      return {
        messageKey: "custom.pages.notifications.content_processing.completed",
        messageArgs: filePathArg(event),
        type: "success",
      };
    case "file.process.failed":
      return {
        messageKey: "custom.pages.notifications.content_processing.failed",
        messageArgs: filePathArg(event),
        type: "error",
      };
    case "research.run.completed":
      return {
        messageKey: "custom.pages.notifications.research.completed",
        type: "success",
      };
    case "research.run.failed":
      return {
        messageKey: "custom.pages.notifications.research.failed",
        type: "error",
      };
    case "research.run.cancelled":
      return {
        messageKey: "custom.pages.notifications.research.cancelled",
        type: "info",
      };
    default:
      return null;
  }
};
