import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultNotificationPreferences,
  describeUserEvent,
  refreshTargetsForUserEvent,
  shouldNotifyForUserEvent,
  userEventStorageKey,
} from "./user-events.ts";

test("notification defaults keep file completion muted but chat completion enabled", () => {
  const preferences = defaultNotificationPreferences();

  assert.equal(preferences.chat.completed, true);
  assert.equal(preferences.content_processing.completed, false);
  assert.equal(preferences.research.completed, true);
});

test("event preferences control toast presentation per event kind", () => {
  const preferences = defaultNotificationPreferences();

  assert.equal(
    shouldNotifyForUserEvent(preferences, {
      kind: "chat.run.completed",
      resource_type: "conversation",
      resource_id: "thread-1",
      status: "COMPLETED",
      metadata: {},
      created_at: "2026-04-23T12:00:00Z",
    }),
    true,
  );
  assert.equal(
    shouldNotifyForUserEvent(preferences, {
      kind: "file.process.completed",
      resource_type: "file",
      resource_id: "file-1",
      status: "COMPLETED",
      metadata: {},
      created_at: "2026-04-23T12:00:00Z",
    }),
    false,
  );
  assert.equal(
    shouldNotifyForUserEvent(preferences, {
      kind: "research.run.completed",
      resource_type: "research_report",
      resource_id: "report-1",
      status: "COMPLETED",
      metadata: {},
      created_at: "2026-04-23T12:00:00Z",
    }),
    true,
  );
});

test("refresh targets stay active even when the toast is muted", () => {
  assert.deepEqual(
    refreshTargetsForUserEvent({
      kind: "file.process.completed",
      resource_type: "file",
      resource_id: "file-1",
      status: "COMPLETED",
      metadata: { file_path: "documents/report.pdf" },
      created_at: "2026-04-23T12:00:00Z",
    }),
    ["content"],
  );
  assert.deepEqual(
    refreshTargetsForUserEvent({
      kind: "research.run.completed",
      resource_type: "research_report",
      resource_id: "report-1",
      status: "COMPLETED",
      metadata: {},
      created_at: "2026-04-23T12:00:00Z",
    }),
    ["research"],
  );
});

test("event descriptions provide translatable message keys and args", () => {
  assert.deepEqual(
    describeUserEvent({
      kind: "file.process.failed",
      resource_type: "file",
      resource_id: "file-1",
      status: "FAILED",
      metadata: { file_path: "documents/report.pdf" },
      created_at: "2026-04-23T12:00:00Z",
    }),
    {
      messageKey: "custom.pages.notifications.content_processing.failed",
      messageArgs: { file_path: "documents/report.pdf" },
      type: "error",
    },
  );
  assert.deepEqual(
    describeUserEvent({
      kind: "research.run.completed",
      resource_type: "research_report",
      resource_id: "report-1",
      status: "COMPLETED",
      metadata: {},
      created_at: "2026-04-23T12:00:00Z",
    }),
    {
      messageKey: "custom.pages.notifications.research.completed",
      type: "success",
    },
  );
});

test("user event storage keys are scoped by identity", () => {
  assert.equal(userEventStorageKey("sub-testuser"), "user-events:last-id:sub-testuser");
});
