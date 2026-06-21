import assert from "node:assert/strict";
import test from "node:test";

import { buildChatExperienceSearch, readChatExperienceState } from "./chat-experience-state.ts";

test("readChatExperienceState defaults to chat mode", () => {
  const state = readChatExperienceState(new URLSearchParams());

  assert.deepEqual(state, {
    mode: "chat",
  });
});

test("readChatExperienceState respects explicit research mode", () => {
  const state = readChatExperienceState(new URLSearchParams("mode=research"));

  assert.deepEqual(state, {
    mode: "research",
  });
});

test("buildChatExperienceSearch preserves unrelated params and stores research mode", () => {
  const next = buildChatExperienceSearch(new URLSearchParams("foo=1"), {
    mode: "research",
  });

  assert.equal(next.toString(), "foo=1&mode=research");
});

test("buildChatExperienceSearch clears research params when switching back to chat", () => {
  const next = buildChatExperienceSearch(new URLSearchParams("foo=1&mode=research"), {
    mode: "chat",
  });

  assert.equal(next.toString(), "foo=1");
});
