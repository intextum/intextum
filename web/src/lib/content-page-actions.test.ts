import assert from "node:assert/strict";
import test from "node:test";

import type { ContentItemInfo } from "@/dataProvider";

import {
  buildContentPageDeleteNotification,
  buildContentPageProcessStartedNotification,
  buildContentPageProcessingFailedNotification,
  buildContentPageQueuedBatchNotification,
  resolveContentPageNotification,
  runContentPageBatchMutation,
  runContentPageDelete,
  runContentPageSelectedFileMutation,
} from "./content-page-actions.ts";

function createFile(path: string): ContentItemInfo {
  return {
    id: path,
    name: path.split("/").pop() || path,
    display_name: path.split("/").pop() || path,
    path,
    kind: "file",
    type: "file",
    size_bytes: 0,
    size_human: "0 B",
    modified_at: "2026-04-26T00:00:00Z",
    is_hidden: false,
  };
}

const translate = (key: string, options?: Record<string, unknown>) =>
  `${key}:${JSON.stringify(options ?? {})}`;

test("notification helpers resolve process and generic error states", () => {
  assert.deepEqual(
    resolveContentPageNotification(
      translate,
      buildContentPageProcessStartedNotification("task-123"),
    ),
    {
      message: 'custom.processing_started:{"id":"task-123"}',
      options: { type: "success" },
    },
  );

  assert.deepEqual(
    resolveContentPageNotification(translate, buildContentPageProcessingFailedNotification()),
    {
      message: "custom.failed_to_start_processing:{}",
      options: { type: "error" },
    },
  );
});

test("notification helpers map queued batch outcomes to success and suppress cancelled notifications", () => {
  const success = buildContentPageQueuedBatchNotification({
    status: "success",
    result: { queued: 4 },
  });
  assert.deepEqual(resolveContentPageNotification(translate, success!), {
    message: 'custom.batch_processing_started:{"count":4}',
    options: { type: "success" },
  });

  const error = buildContentPageQueuedBatchNotification({ status: "error" });
  assert.deepEqual(resolveContentPageNotification(translate, error!), {
    message: "custom.failed_to_start_processing:{}",
    options: { type: "error" },
  });

  assert.equal(
    buildContentPageQueuedBatchNotification({
      status: "cancelled",
    }),
    null,
  );
});

test("notification helpers expose warning and file-level error descriptors", () => {
  assert.deepEqual(
    resolveContentPageNotification(translate, buildContentPageDeleteNotification("success")),
    {
      message: "custom.content.delete.success:{}",
      options: { type: "success" },
    },
  );

  assert.deepEqual(
    resolveContentPageNotification(translate, buildContentPageDeleteNotification("error")),
    {
      message: "custom.content.delete.failed:{}",
      options: { type: "error" },
    },
  );
});

test("runContentPageBatchMutation refreshes on success", async () => {
  let refreshCount = 0;

  const outcome = await runContentPageBatchMutation({
    execute: async () => ({ queued: 3 }),
    onRefresh: () => {
      refreshCount += 1;
    },
  });

  assert.deepEqual(outcome, {
    status: "success",
    result: { queued: 3 },
  });
  assert.equal(refreshCount, 1);
});

test("runContentPageBatchMutation stops on cancel and skips refresh", async () => {
  let executed = false;
  let refreshed = false;

  const outcome = await runContentPageBatchMutation({
    confirm: () => false,
    execute: async () => {
      executed = true;
      return { queued: 1 };
    },
    onRefresh: () => {
      refreshed = true;
    },
  });

  assert.deepEqual(outcome, { status: "cancelled" });
  assert.equal(executed, false);
  assert.equal(refreshed, false);
});

test("runContentPageBatchMutation reports errors without refreshing", async () => {
  let refreshed = false;

  const outcome = await runContentPageBatchMutation({
    execute: async () => {
      throw new Error("boom");
    },
    onRefresh: () => {
      refreshed = true;
    },
  });

  assert.deepEqual(outcome, { status: "error" });
  assert.equal(refreshed, false);
});

test("runContentPageSelectedFileMutation updates the selected file and refreshes", async () => {
  const activeFile = createFile("inbox/original.pdf");
  const updatedFile = createFile("inbox/original.pdf");
  const updated: ContentItemInfo[] = [];
  let refreshCount = 0;

  const result = await runContentPageSelectedFileMutation({
    activeSelectedFile: activeFile,
    mutate: async (path) => {
      assert.equal(path, activeFile.path);
      return updatedFile;
    },
    onUpdateSelectedFile: (file) => {
      updated.push(file);
    },
    onRefresh: () => {
      refreshCount += 1;
    },
  });

  assert.equal(result, updatedFile);
  assert.deepEqual(updated, [updatedFile]);
  assert.equal(refreshCount, 1);
});

test("runContentPageSelectedFileMutation returns null when no active file is selected", async () => {
  let refreshed = false;

  const result = await runContentPageSelectedFileMutation({
    activeSelectedFile: null,
    mutate: async () => createFile("unused.pdf"),
    onUpdateSelectedFile: () => undefined,
    onRefresh: () => {
      refreshed = true;
    },
  });

  assert.equal(result, null);
  assert.equal(refreshed, false);
});

test("runContentPageSelectedFileMutation returns null on mutation failure", async () => {
  let refreshed = false;

  const result = await runContentPageSelectedFileMutation({
    activeSelectedFile: createFile("inbox/original.pdf"),
    mutate: async () => {
      throw new Error("boom");
    },
    onUpdateSelectedFile: () => undefined,
    onRefresh: () => {
      refreshed = true;
    },
  });

  assert.equal(result, null);
  assert.equal(refreshed, false);
});

test("runContentPageDelete refreshes and clears the selected file when deleting it", async () => {
  let refreshCount = 0;
  let clearCount = 0;
  const deleted: string[] = [];

  await runContentPageDelete({
    path: "inbox/file.pdf",
    selectedFilePath: "inbox/file.pdf",
    deleteFile: async (path) => {
      deleted.push(path);
    },
    onRefresh: () => {
      refreshCount += 1;
    },
    onClearSelectedFile: () => {
      clearCount += 1;
    },
  });

  assert.deepEqual(deleted, ["inbox/file.pdf"]);
  assert.equal(refreshCount, 1);
  assert.equal(clearCount, 1);
});

test("runContentPageDelete keeps the current selection when another file is deleted", async () => {
  let clearCount = 0;

  await runContentPageDelete({
    path: "inbox/other.pdf",
    selectedFilePath: "inbox/file.pdf",
    deleteFile: async () => undefined,
    onRefresh: () => undefined,
    onClearSelectedFile: () => {
      clearCount += 1;
    },
  });

  assert.equal(clearCount, 0);
});
