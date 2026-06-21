import assert from "node:assert/strict";
import test from "node:test";

import { shouldDisablePromptSubmit } from "./chat-input-state.ts";

test("keeps the prompt submit button enabled while streaming so it can stop", () => {
  assert.equal(
    shouldDisablePromptSubmit({
      disableSend: true,
      inputText: "",
      isLoading: true,
    }),
    false,
  );
});

test("disables submit when idle and the input is empty", () => {
  assert.equal(
    shouldDisablePromptSubmit({
      disableSend: false,
      inputText: "  ",
      isLoading: false,
    }),
    true,
  );
});

test("honors disableSend for idle submissions", () => {
  assert.equal(
    shouldDisablePromptSubmit({
      disableSend: true,
      inputText: "hello",
      isLoading: false,
    }),
    true,
  );
});

test("enables submit when idle with non-empty input", () => {
  assert.equal(
    shouldDisablePromptSubmit({
      disableSend: false,
      inputText: "hello",
      isLoading: false,
    }),
    false,
  );
});
