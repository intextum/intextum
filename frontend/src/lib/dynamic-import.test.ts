import assert from "node:assert/strict";
import test from "node:test";

import { retryDynamicImport } from "./dynamic-import.ts";

test("retryDynamicImport retries transient dynamic import fetch failures", async () => {
  let calls = 0;
  const result = await retryDynamicImport(
    async () => {
      calls += 1;
      if (calls === 1) {
        throw new TypeError("Failed to fetch dynamically imported module");
      }
      return { ok: true };
    },
    { retryDelayMs: 0 },
  );

  assert.deepEqual(result, { ok: true });
  assert.equal(calls, 2);
});

test("retryDynamicImport does not retry unrelated errors", async () => {
  let calls = 0;
  const error = new Error("module evaluated but failed");

  await assert.rejects(
    retryDynamicImport(
      async () => {
        calls += 1;
        throw error;
      },
      { retryDelayMs: 0 },
    ),
    error,
  );
  assert.equal(calls, 1);
});
