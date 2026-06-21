import assert from "node:assert/strict";
import test from "node:test";

import {
  markConversationRunReady,
  markConversationRunStreaming,
  shouldDetachActiveRun,
  shouldJoinStoredRun,
  visibleConversationRunState,
} from "./conversation-run-state.ts";

test("visibleConversationRunState scopes values and loading to the active conversation", () => {
  const runStatus = markConversationRunStreaming("thread-a");
  const valuesByConversation = {
    "thread-a": { messages: [{ id: "a", content: "from a" }] },
    "thread-b": { messages: [{ id: "b", content: "from b" }] },
  };

  assert.deepEqual(visibleConversationRunState(valuesByConversation, runStatus, "thread-a"), {
    values: valuesByConversation["thread-a"],
    isLoading: true,
  });
  assert.deepEqual(visibleConversationRunState(valuesByConversation, runStatus, "thread-b"), {
    values: valuesByConversation["thread-b"],
    isLoading: false,
  });
});

test("markConversationRunReady only clears the matching conversation", () => {
  const runStatus = markConversationRunStreaming("thread-a");

  assert.deepEqual(markConversationRunReady(runStatus, "thread-b"), runStatus);
  assert.deepEqual(markConversationRunReady(runStatus, "thread-a"), {
    conversationId: null,
    status: "ready",
  });
});

test("shouldDetachActiveRun detaches only when navigating to another conversation", () => {
  const activeRun = { conversationId: "thread-a", runId: "run-a" };

  assert.equal(shouldDetachActiveRun(activeRun, "thread-a"), false);
  assert.equal(shouldDetachActiveRun(activeRun, "thread-b"), true);
  assert.equal(shouldDetachActiveRun(activeRun, null), true);
  assert.equal(shouldDetachActiveRun(null, "thread-a"), false);
});

test("shouldJoinStoredRun rejoins terminal runs for final event replay", () => {
  assert.equal(
    shouldJoinStoredRun({ conversation_id: "thread-a", status: "COMPLETED" }, "thread-a"),
    true,
  );
  assert.equal(
    shouldJoinStoredRun({ conversation_id: "thread-b", status: "RUNNING" }, "thread-a"),
    false,
  );
});
