import assert from "node:assert/strict";
import test from "node:test";

import {
  applyStreamMessageEvent,
  toConversationMessages,
  type ChatStreamState,
} from "./chat-stream.ts";

test("applyStreamMessageEvent preserves tool calls for assistant tool request chunks", () => {
  const current: ChatStreamState = {};

  const next = applyStreamMessageEvent(current, [
    {
      id: "run-1",
      type: "ai",
      content: "",
      tool_calls: [
        {
          id: "call-1",
          name: "search_documents",
          args: { query: "invoice" },
        },
      ],
    },
  ]);

  assert.deepEqual(next.messages?.[0]?.tool_calls, [
    {
      id: "call-1",
      name: "search_documents",
      args: { query: "invoice" },
    },
  ]);
  assert.deepEqual(toConversationMessages(next.messages), []);
});
