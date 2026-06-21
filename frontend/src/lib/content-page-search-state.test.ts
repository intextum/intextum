import assert from "node:assert/strict";
import test from "node:test";

import type { ContentItemInfo } from "@/dataProvider";

import { startContentPageSelectedFileLoad } from "./content-page-search-state.ts";

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

function createDeferred<T>() {
  let resolvePromise: ((value: T) => void) | undefined;
  let rejectPromise: ((reason?: unknown) => void) | undefined;

  const promise = new Promise<T>((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });

  return {
    promise,
    resolve: (value: T) => {
      if (!resolvePromise) {
        throw new Error("missing resolve");
      }
      resolvePromise(value);
    },
    reject: (reason?: unknown) => {
      if (!rejectPromise) {
        throw new Error("missing reject");
      }
      rejectPromise(reason);
    },
  };
}

async function flushAsyncWork() {
  await Promise.resolve();
}

test("startContentPageSelectedFileLoad hydrates a selected file when details resolve", async () => {
  const deferred = createDeferred<ContentItemInfo>();
  const selectedFiles: ContentItemInfo[] = [];
  let missingCount = 0;

  const cleanup = startContentPageSelectedFileLoad({
    selectedFilePath: "inbox/current.pdf",
    currentSelectedFilePath: null,
    getDetails: () => deferred.promise,
    onSelectFile: (file) => {
      selectedFiles.push(file);
    },
    onMissingFile: () => {
      missingCount += 1;
    },
  });

  assert.equal(typeof cleanup, "function");

  deferred.resolve(createFile("inbox/current.pdf"));
  await deferred.promise;
  await flushAsyncWork();

  assert.deepEqual(
    selectedFiles.map((file) => file.path),
    ["inbox/current.pdf"],
  );
  assert.equal(missingCount, 0);
});

test("startContentPageSelectedFileLoad reports a missing file on lookup failure", async () => {
  const deferred = createDeferred<ContentItemInfo>();
  const selectedFiles: ContentItemInfo[] = [];
  let missingCount = 0;

  startContentPageSelectedFileLoad({
    selectedFilePath: "inbox/missing.pdf",
    currentSelectedFilePath: null,
    getDetails: () => deferred.promise,
    onSelectFile: (file) => {
      selectedFiles.push(file);
    },
    onMissingFile: () => {
      missingCount += 1;
    },
  });

  deferred.reject(new Error("missing"));
  await deferred.promise.catch(() => undefined);
  await flushAsyncWork();

  assert.deepEqual(selectedFiles, []);
  assert.equal(missingCount, 1);
});

test("startContentPageSelectedFileLoad ignores stale async results after cleanup", async () => {
  const deferred = createDeferred<ContentItemInfo>();
  const selectedFiles: ContentItemInfo[] = [];
  let missingCount = 0;

  const cleanup = startContentPageSelectedFileLoad({
    selectedFilePath: "inbox/current.pdf",
    currentSelectedFilePath: null,
    getDetails: () => deferred.promise,
    onSelectFile: (file) => {
      selectedFiles.push(file);
    },
    onMissingFile: () => {
      missingCount += 1;
    },
  });

  cleanup?.();
  deferred.resolve(createFile("inbox/current.pdf"));
  await deferred.promise;
  await flushAsyncWork();

  assert.deepEqual(selectedFiles, []);
  assert.equal(missingCount, 0);
});

test("startContentPageSelectedFileLoad skips work when the selected file is already loaded", () => {
  let detailLookups = 0;

  const cleanup = startContentPageSelectedFileLoad({
    selectedFilePath: "inbox/current.pdf",
    currentSelectedFilePath: "inbox/current.pdf",
    getDetails: async () => {
      detailLookups += 1;
      return createFile("inbox/current.pdf");
    },
    onSelectFile: () => undefined,
    onMissingFile: () => undefined,
  });

  assert.equal(cleanup, undefined);
  assert.equal(detailLookups, 0);
});
