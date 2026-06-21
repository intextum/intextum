import assert from "node:assert/strict";
import test from "node:test";

import { httpErrorStatus, shouldIgnorePendingConversationLoadError } from "./chat-route-state.ts";

test("httpErrorStatus extracts numeric fetch error statuses", () => {
  assert.equal(httpErrorStatus({ status: 404 }), 404);
  assert.equal(httpErrorStatus({ status: "404" }), undefined);
  assert.equal(httpErrorStatus(new Error("Not Found")), undefined);
});

test("ignores 404 while the routed conversation is still being generated", () => {
  assert.equal(
    shouldIgnorePendingConversationLoadError({
      activeThreadId: "thread-new",
      conversationId: "thread-new",
      isLoading: true,
      status: 404,
    }),
    true,
  );
});

test("does not hide real missing conversation loads", () => {
  assert.equal(
    shouldIgnorePendingConversationLoadError({
      activeThreadId: "thread-other",
      conversationId: "thread-missing",
      isLoading: true,
      status: 404,
    }),
    false,
  );
  assert.equal(
    shouldIgnorePendingConversationLoadError({
      activeThreadId: "thread-missing",
      conversationId: "thread-missing",
      isLoading: false,
      status: 404,
    }),
    false,
  );
});
