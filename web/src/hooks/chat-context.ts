import type { ConversationMessage } from "@/dataProvider";

export const normalizePath = (path: string): string => path.trim().replace(/^\/+|\/+$/g, "");

export const normalizePaths = (paths: string[]): string[] => {
  const deduped: string[] = [];
  const seen = new Set<string>();
  for (const item of paths) {
    const normalized = normalizePath(item);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    deduped.push(normalized);
  }
  return deduped;
};

export const addPaths = (
  current: string[],
  incoming: string[],
): { paths: string[]; addedCount: number; skippedCount: number } => {
  const next = [...current];
  const seen = new Set(current);
  let addedCount = 0;
  let skippedCount = 0;

  for (const raw of incoming) {
    const normalized = normalizePath(raw);
    if (!normalized || seen.has(normalized)) {
      skippedCount += 1;
      continue;
    }
    seen.add(normalized);
    next.push(normalized);
    addedCount += 1;
  }

  return { paths: next, addedCount, skippedCount };
};

export const removePath = (current: string[], path: string): string[] => {
  const normalized = normalizePath(path);
  return current.filter((item) => item !== normalized);
};

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const normalizeContextPaths = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];

  const candidates = value.filter((item): item is string => typeof item === "string");
  return normalizePaths(candidates);
};

export const extractContextPathsFromMessage = (message: ConversationMessage): string[] => {
  const metadata = message.metadata;
  if (isObjectRecord(metadata)) {
    const fromMetadata = normalizeContextPaths(metadata.context_file_paths);
    if (fromMetadata.length > 0) {
      return fromMetadata;
    }
  }

  return [];
};
