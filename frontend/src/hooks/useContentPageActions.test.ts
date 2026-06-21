import assert from "node:assert/strict";
import test from "node:test";

import { createElement, createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { contentApi } from "../dataProvider.ts";
import { ConfirmContext, type ConfirmFn } from "../lib/confirm-context.ts";

import { useContentPageActions } from "./useContentPageActions.ts";

type NotificationEntry = {
  message: unknown;
  type?: string;
};

function createNotificationRecorder() {
  const notifications: NotificationEntry[] = [];
  return {
    notifications,
    notify: (message: unknown, options?: { type?: string }) => {
      notifications.push({ message, type: options?.type });
    },
  };
}

function translate(key: string, options?: Record<string, unknown>) {
  return `${key}:${JSON.stringify(options ?? {})}`;
}

async function withPatchedContentApi(
  stubs: Partial<typeof contentApi>,
  run: () => Promise<void> | void,
) {
  const patchedApi = contentApi as unknown as Record<string, unknown>;
  const originalEntries = Object.keys(stubs).map((key) => [key, patchedApi[key]] as const);

  Object.assign(patchedApi, stubs as Record<string, unknown>);
  try {
    await run();
  } finally {
    for (const [key, value] of originalEntries) {
      patchedApi[key] = value;
    }
  }
}

async function withWindowConfirm(
  confirm: (message?: string) => boolean,
  run: () => Promise<void> | void,
) {
  const previousConfirm = currentConfirm;
  currentConfirm = async ({ description }) => confirm(description);
  try {
    await run();
  } finally {
    currentConfirm = previousConfirm;
  }
}

let currentConfirm: ConfirmFn = async () => true;

function renderUseContentPageActions(
  overrides: Partial<Parameters<typeof useContentPageActions>[0]> = {},
) {
  const recorder = createNotificationRecorder();
  let clearedSelectionCount = 0;
  let refreshCount = 0;
  const hookValueRef = createRef<ReturnType<typeof useContentPageActions>>();

  function HookProbe() {
    // eslint-disable-next-line react-hooks/immutability
    hookValueRef.current = useContentPageActions({
      notify: recorder.notify,
      translate,
      selectedFilePath: null,
      onRefresh: () => {
        refreshCount += 1;
      },
      onClearSelectedFile: () => {
        clearedSelectionCount += 1;
      },
      ...overrides,
    });
    return null;
  }

  function Harness() {
    return createElement(
      ConfirmContext.Provider,
      { value: currentConfirm },
      createElement(HookProbe),
    );
  }

  renderToStaticMarkup(createElement(Harness));
  const actions = hookValueRef.current ?? null;
  if (!actions) {
    throw new Error("hook should render");
  }

  return {
    actions,
    notifications: recorder.notifications,
    getRefreshCount: () => refreshCount,
    getClearedSelectionCount: () => clearedSelectionCount,
  };
}

test("useContentPageActions emits a success notification for process start", async () => {
  await withPatchedContentApi(
    {
      triggerProcess: async () => ({
        message: "started",
        task_id: "task-123",
      }),
    },
    async () => {
      const harness = renderUseContentPageActions();

      await harness.actions.handleProcess("inbox/current.pdf");

      assert.deepEqual(harness.notifications, [
        {
          message: 'custom.processing_started:{"id":"task-123"}',
          type: "success",
        },
      ]);
      assert.equal(harness.getRefreshCount(), 1);
    },
  );
});

test("useContentPageActions suppresses notifications when folder processing is cancelled", async () => {
  let batchCalled = false;

  await withPatchedContentApi(
    {
      triggerBatchProcess: async () => {
        batchCalled = true;
        return { message: "started", queued: 2, errors: 0 };
      },
    },
    async () => {
      await withWindowConfirm(
        () => false,
        async () => {
          const harness = renderUseContentPageActions();

          await harness.actions.handleProcessFolder("inbox");

          assert.equal(batchCalled, false);
          assert.deepEqual(harness.notifications, []);
          assert.equal(harness.getRefreshCount(), 0);
        },
      );
    },
  );
});

test("useContentPageActions processes selected paths with optional config", async () => {
  const calls: unknown[] = [];

  await withPatchedContentApi(
    {
      triggerBatchProcess: async (...args: unknown[]) => {
        calls.push(args);
        return { message: "started", queued: 2, errors: 0 };
      },
    },
    async () => {
      const harness = renderUseContentPageActions();

      await harness.actions.handleProcessSelected(["inbox/a.pdf", "inbox/b.pdf"], {
        do_ocr: false,
        document_enrichment: true,
      });

      assert.deepEqual(calls, [
        [
          {
            paths: ["inbox/a.pdf", "inbox/b.pdf"],
            processingConfig: {
              do_ocr: false,
              document_enrichment: true,
            },
          },
        ],
      ]);
      assert.deepEqual(harness.notifications, [
        {
          message: 'custom.batch_processing_started:{"count":2}',
          type: "success",
        },
      ]);
      assert.equal(harness.getRefreshCount(), 1);
    },
  );
});
