import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useGetIdentity, useNotify } from "@/lib/app-context";
import {
  invalidateContentQueries,
  invalidateConversationQueries,
  queryKeys,
} from "@/lib/query-client";
import {
  notificationPreferencesApi,
  type NotificationPreferences,
  type UserEvent,
} from "@/dataProvider";
import { readSseStream } from "@/lib/sse-stream";
import {
  defaultNotificationPreferences,
  describeUserEvent,
  refreshTargetsForUserEvent,
  shouldNotifyForUserEvent,
  userEventStorageKey,
} from "@/lib/user-events";
import { recordStoredNotification } from "@/lib/notification-center";

const RECONNECT_DELAY_MS = 2000;

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

const readLastEventId = (identityId: string): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(userEventStorageKey(identityId));
  } catch {
    return null;
  }
};

const writeLastEventId = (identityId: string, eventId: string): void => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(userEventStorageKey(identityId), eventId);
  } catch {
    // Ignore storage failures.
  }
};

const errorStatus = (error: unknown): number | undefined =>
  typeof error === "object" && error !== null && "status" in error
    ? ((error as { status?: unknown }).status as number | undefined)
    : undefined;

export const UserEventBridge = () => {
  const notify = useNotify();
  const { identity, isPending } = useGetIdentity();
  const preferencesQuery = useQuery({
    queryKey: queryKeys.settings.notificationPreferences,
    queryFn: notificationPreferencesApi.get,
  });
  const preferences = preferencesQuery.data ?? defaultNotificationPreferences();
  const preferencesRef = useRef<NotificationPreferences>(preferences);

  useEffect(() => {
    preferencesRef.current = preferences;
  }, [preferences]);

  useEffect(() => {
    if (isPending || !identity?.id) {
      return;
    }

    let cancelled = false;
    const abortController = new AbortController();

    const run = async () => {
      while (!cancelled) {
        try {
          const after = readLastEventId(String(identity.id));
          const query = after ? `?after=${encodeURIComponent(after)}` : "";
          const response = await fetch(`/api/events/stream${query}`, {
            credentials: "include",
            signal: abortController.signal,
          });

          if (!response.ok || !response.body) {
            const error = new Error(`Failed to read user events (${response.status})`) as Error & {
              status?: number;
            };
            error.status = response.status;
            throw error;
          }

          await readSseStream(response.body, (frame) => {
            if (
              frame.event !== "user-event" ||
              typeof frame.data !== "object" ||
              frame.data === null
            ) {
              return;
            }
            const event = frame.data as UserEvent;
            const eventId =
              frame.id || (typeof event.event_id === "string" ? event.event_id : undefined);
            if (eventId) {
              writeLastEventId(String(identity.id), eventId);
            }
            recordStoredNotification(String(identity.id), event);

            for (const target of refreshTargetsForUserEvent(event)) {
              if (target === "conversations" || target === "research") {
                void invalidateConversationQueries();
              }
              if (target === "content") {
                void invalidateContentQueries();
              }
            }

            if (!shouldNotifyForUserEvent(preferencesRef.current, event)) {
              return;
            }

            const description = describeUserEvent(event);
            if (!description) {
              return;
            }

            notify(description.messageKey, {
              type: description.type,
              messageArgs: description.messageArgs,
            });
          });
        } catch (error) {
          if (abortController.signal.aborted || cancelled) {
            return;
          }
          const status = errorStatus(error);
          if (status === 401 || status === 403 || status === 503) {
            return;
          }
        }

        if (!cancelled) {
          await sleep(RECONNECT_DELAY_MS);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
      abortController.abort();
    };
  }, [identity?.id, isPending, notify]);

  return null;
};
