import assert from "node:assert/strict";
import test from "node:test";

import { parseSseFrames, readSseStream, takeCompleteSseFrames } from "./sse-stream.ts";

test("parseSseFrames decodes ids, event names and JSON payloads", () => {
  const frames = parseSseFrames(
    [
      "id: 1713870000000-0",
      "event: values",
      'data: {"messages":[{"id":"msg-1","content":"hello"}]}',
      "",
      "",
    ].join("\n"),
  );

  assert.deepEqual(frames, [
    {
      id: "1713870000000-0",
      event: "values",
      data: { messages: [{ id: "msg-1", content: "hello" }] },
    },
  ]);
});

test("takeCompleteSseFrames keeps partial frames buffered", () => {
  const firstChunk = [
    "id: 1-0",
    "event: messages",
    'data: ["hello"]',
    "",
    "id: 2-0",
    "event: values",
    'data: {"title":"partial"',
  ].join("\n");

  const first = takeCompleteSseFrames(firstChunk);

  assert.deepEqual(first.frames, [
    {
      id: "1-0",
      event: "messages",
      data: ["hello"],
    },
  ]);
  assert.equal(first.remaining, 'id: 2-0\nevent: values\ndata: {"title":"partial"');

  const second = takeCompleteSseFrames(`${first.remaining}}\n\n`);

  assert.deepEqual(second.frames, [
    {
      id: "2-0",
      event: "values",
      data: { title: "partial" },
    },
  ]);
  assert.equal(second.remaining, "");
});

test("parseSseFrames preserves non JSON data as text", () => {
  const frames = parseSseFrames("event: error\ndata: plain failure\n\n");

  assert.deepEqual(frames, [
    {
      event: "error",
      data: "plain failure",
    },
  ]);
});

test("readSseStream parses frames across streamed chunks", async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode("id: 1-0\nevent: messages\ndata: "));
      controller.enqueue(encoder.encode('["hello"]\n\nid: 2-0\nevent: done\n'));
      controller.enqueue(encoder.encode('data: {"status":"COMPLETED"}\n\n'));
      controller.close();
    },
  });
  const frames: unknown[] = [];

  await readSseStream(body, (frame) => frames.push(frame));

  assert.deepEqual(frames, [
    {
      id: "1-0",
      event: "messages",
      data: ["hello"],
    },
    {
      id: "2-0",
      event: "done",
      data: { status: "COMPLETED" },
    },
  ]);
});
