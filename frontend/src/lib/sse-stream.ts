export interface SseFrame {
  id?: string;
  event: string;
  data: unknown;
}

export const parseSseFrames = (chunk: string): SseFrame[] => {
  const frames: SseFrame[] = [];
  for (const rawFrame of chunk.split("\n\n")) {
    if (!rawFrame.trim()) {
      continue;
    }

    let id: string | undefined;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of rawFrame.split(/\r?\n/)) {
      if (line.startsWith("id:")) {
        id = line.slice(3).trim();
      } else if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }

    const dataText = dataLines.join("\n");
    let data: unknown = dataText;
    if (dataText) {
      try {
        data = JSON.parse(dataText);
      } catch {
        data = dataText;
      }
    }
    frames.push(id ? { id, event, data } : { event, data });
  }
  return frames;
};

export const takeCompleteSseFrames = (
  buffer: string,
): { frames: SseFrame[]; remaining: string } => {
  const boundary = buffer.lastIndexOf("\n\n");
  if (boundary === -1) {
    return { frames: [], remaining: buffer };
  }

  const complete = buffer.slice(0, boundary + 2);
  return {
    frames: parseSseFrames(complete),
    remaining: buffer.slice(boundary + 2),
  };
};

export const readSseStream = async (
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: SseFrame) => void,
): Promise<void> => {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const parsed = takeCompleteSseFrames(buffer);
      buffer = parsed.remaining;
      for (const frame of parsed.frames) {
        onFrame(frame);
      }
    }

    buffer += decoder.decode();
    for (const frame of parseSseFrames(buffer)) {
      onFrame(frame);
    }
  } finally {
    reader.releaseLock();
  }
};
