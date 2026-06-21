import assert from "node:assert/strict";
import test from "node:test";

import {
  shouldResetResearchComposerMode,
  shouldShowTransientResearchBlock,
} from "./chat-research-state.ts";

test("shouldResetResearchComposerMode resets the composer only for completed active research runs", () => {
  assert.equal(
    shouldResetResearchComposerMode({
      currentMode: "research",
      activeThreadId: "thread-1",
      settledConversationId: "thread-1",
      settledMode: "research",
      status: "COMPLETED",
    }),
    true,
  );

  assert.equal(
    shouldResetResearchComposerMode({
      currentMode: "research",
      activeThreadId: "thread-1",
      settledConversationId: "thread-2",
      settledMode: "research",
      status: "COMPLETED",
    }),
    false,
  );
  assert.equal(
    shouldResetResearchComposerMode({
      currentMode: "research",
      activeThreadId: "thread-1",
      settledConversationId: "thread-1",
      settledMode: "research",
      status: "FAILED",
    }),
    false,
  );
  assert.equal(
    shouldResetResearchComposerMode({
      currentMode: "chat",
      activeThreadId: "thread-1",
      settledConversationId: "thread-1",
      settledMode: "research",
      status: "COMPLETED",
    }),
    false,
  );
});

test("shouldShowTransientResearchBlock hides the transient block once research settles", () => {
  assert.equal(
    shouldShowTransientResearchBlock({
      activeRunMode: "research",
      progressEventCount: 0,
    }),
    true,
  );
  assert.equal(
    shouldShowTransientResearchBlock({
      activeRunMode: null,
      progressEventCount: 2,
    }),
    true,
  );
  assert.equal(
    shouldShowTransientResearchBlock({
      activeRunMode: null,
      progressEventCount: 0,
    }),
    false,
  );
});
