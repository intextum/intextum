import type { ConversationMessage, ConversationSource } from "@/dataProvider";
import { normalizeContextPaths } from "../hooks/chat-context.ts";

export interface ThreadMessage {
  id?: string;
  type?: string;
  role?: string;
  content?: unknown;
  created_at?: string;
  tool_calls?: unknown[];
  additional_kwargs?: Record<string, unknown>;
}

export interface ChatStreamState extends Record<string, unknown> {
  messages?: ThreadMessage[];
  context_file_paths?: string[];
  title?: string | null;
  created_at?: string;
  updated_at?: string;
}

export const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const createClientId = (prefix: string): string => {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
};

const buildMessageMetadata = (paths: string[]): Record<string, unknown> | undefined =>
  paths.length > 0 ? { context_file_paths: [...paths] } : undefined;

export const messageText = (content: unknown): string => {
  if (typeof content === "string") {
    return content;
  }
  if (!Array.isArray(content)) {
    return "";
  }

  const parts: string[] = [];
  for (const item of content) {
    if (typeof item === "string") {
      parts.push(item);
      continue;
    }
    if (isObjectRecord(item) && typeof item.text === "string") {
      parts.push(item.text);
    }
  }
  return parts.join("");
};

const messageAdditionalKwargs = (message: ThreadMessage): Record<string, unknown> => {
  return isObjectRecord(message.additional_kwargs) ? message.additional_kwargs : {};
};

const messageSources = (message: ThreadMessage): ConversationSource[] => {
  const rawSources = messageAdditionalKwargs(message).sources;
  if (!Array.isArray(rawSources)) {
    return [];
  }

  const sources: ConversationSource[] = [];
  for (const source of rawSources) {
    if (!isObjectRecord(source) || typeof source.file_path !== "string" || !source.file_path) {
      continue;
    }
    sources.push({
      file_path: source.file_path,
      content_item_id:
        typeof source.content_item_id === "string" ? source.content_item_id : undefined,
      display_name: typeof source.display_name === "string" ? source.display_name : undefined,
      content_kind:
        source.content_kind === "file" ||
        source.content_kind === "folder" ||
        source.content_kind === "email_message" ||
        source.content_kind === "attachment"
          ? source.content_kind
          : undefined,
      title: typeof source.title === "string" ? source.title : undefined,
      source_kind: source.source_kind === "reviewed_enrichment" ? source.source_kind : undefined,
      page_numbers: Array.isArray(source.page_numbers)
        ? source.page_numbers.filter((page): page is number => typeof page === "number")
        : [],
      doc_refs: Array.isArray(source.doc_refs)
        ? source.doc_refs.filter((docRef): docRef is string => typeof docRef === "string")
        : [],
      citation_index: typeof source.citation_index === "number" ? source.citation_index : undefined,
      images: Array.isArray(source.images)
        ? source.images.filter((image): image is string => typeof image === "string")
        : [],
      quote: typeof source.quote === "string" ? source.quote : undefined,
    });
  }

  return sources;
};

const messageToolCalls = (message: ThreadMessage): unknown[] => {
  const rawMessage = message as unknown as Record<string, unknown>;
  return Array.isArray(rawMessage.tool_calls) ? rawMessage.tool_calls : [];
};

const messageContextPaths = (message: ThreadMessage): string[] => {
  return normalizeContextPaths(messageAdditionalKwargs(message).context_file_paths);
};

const messageCreatedAt = (message: ThreadMessage): string | undefined => {
  const createdAt = messageAdditionalKwargs(message).created_at;
  return typeof createdAt === "string" ? createdAt : undefined;
};

const messageType = (message: ThreadMessage): string => String(message.type ?? "").toLowerCase();

export const toConversationMessage = (message: ThreadMessage): ConversationMessage | null => {
  const normalizedType = messageType(message);

  if (
    normalizedType === "human" ||
    normalizedType === "user" ||
    normalizedType === "humanmessagechunk"
  ) {
    return {
      id: message.id ?? createClientId("msg"),
      role: "user",
      content: messageText(message.content),
      sources: [],
      metadata: buildMessageMetadata(messageContextPaths(message)),
      created_at: messageCreatedAt(message),
      status: undefined,
    };
  }

  if (
    normalizedType !== "ai" &&
    normalizedType !== "assistant" &&
    normalizedType !== "aimessagechunk"
  ) {
    return null;
  }

  const content = messageText(message.content);
  const sources = messageSources(message);
  const toolCalls = messageToolCalls(message);
  if (!content.trim() && sources.length === 0 && toolCalls.length > 0) {
    return null;
  }
  if (!content.trim() && sources.length === 0) {
    return null;
  }

  return {
    id: message.id ?? createClientId("msg"),
    role: "assistant",
    content,
    sources,
    metadata: undefined,
    created_at: messageCreatedAt(message),
    status: undefined,
  };
};

export const toConversationMessages = (
  messages: ThreadMessage[] | undefined,
): ConversationMessage[] => {
  if (!Array.isArray(messages)) {
    return [];
  }

  const normalized: ConversationMessage[] = [];
  for (const message of messages) {
    const normalizedMessage = toConversationMessage(message);
    if (normalizedMessage) {
      normalized.push(normalizedMessage);
    }
  }
  return normalized;
};

export const toThreadMessage = (message: ConversationMessage): ThreadMessage => {
  if (message.role === "user") {
    const additionalKwargs: Record<string, unknown> = {};
    const contextPaths = normalizeContextPaths(message.metadata?.context_file_paths);
    if (contextPaths.length > 0) {
      additionalKwargs.context_file_paths = contextPaths;
    }
    if (message.created_at) {
      additionalKwargs.created_at = message.created_at;
    }
    return {
      id: message.id,
      type: "human",
      content: message.content,
      additional_kwargs: additionalKwargs,
    };
  }

  const additionalKwargs: Record<string, unknown> = {};
  if (message.sources.length > 0) {
    additionalKwargs.sources = message.sources;
  }
  if (message.created_at) {
    additionalKwargs.created_at = message.created_at;
  }
  return {
    id: message.id,
    type: "ai",
    content: message.content,
    additional_kwargs: additionalKwargs,
  };
};

export const buildUserThreadMessage = (text: string, contextPaths: string[]): ThreadMessage => ({
  id: createClientId("msg"),
  type: "human",
  content: text,
  additional_kwargs: {
    created_at: new Date().toISOString(),
    ...(contextPaths.length > 0 ? { context_file_paths: [...contextPaths] } : {}),
  },
});

const conversationSourceEquals = (
  left: ConversationMessage["sources"][number],
  right: ConversationMessage["sources"][number],
): boolean =>
  left.file_path === right.file_path &&
  left.title === right.title &&
  left.citation_index === right.citation_index &&
  left.quote === right.quote &&
  left.page_numbers.length === right.page_numbers.length &&
  left.page_numbers.every((value, index) => value === right.page_numbers[index]) &&
  left.doc_refs.length === right.doc_refs.length &&
  left.doc_refs.every((value, index) => value === right.doc_refs[index]) &&
  left.images.length === right.images.length &&
  left.images.every((value, index) => value === right.images[index]);

const conversationMessageEquals = (
  left: ConversationMessage,
  right: ConversationMessage,
): boolean =>
  left.id === right.id &&
  left.role === right.role &&
  left.content === right.content &&
  left.created_at === right.created_at &&
  left.status === right.status &&
  JSON.stringify(left.metadata ?? null) === JSON.stringify(right.metadata ?? null) &&
  left.sources.length === right.sources.length &&
  left.sources.every((source, index) => conversationSourceEquals(source, right.sources[index]));

export const conversationMessagesEqual = (
  left: ConversationMessage[],
  right: ConversationMessage[],
): boolean =>
  left.length === right.length &&
  left.every((message, index) => conversationMessageEquals(message, right[index]));

const normalizeThreadMessage = (value: unknown): ThreadMessage | null => {
  if (!isObjectRecord(value)) {
    return null;
  }

  return {
    id: typeof value.id === "string" ? value.id : undefined,
    type: typeof value.type === "string" ? value.type : undefined,
    role: typeof value.role === "string" ? value.role : undefined,
    content: "content" in value ? value.content : "",
    tool_calls: Array.isArray(value.tool_calls) ? value.tool_calls : undefined,
    additional_kwargs: isObjectRecord(value.additional_kwargs) ? value.additional_kwargs : {},
  };
};

export const coerceThreadMessages = (value: unknown): ThreadMessage[] | undefined => {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const messages: ThreadMessage[] = [];
  for (const item of value) {
    const normalized = normalizeThreadMessage(item);
    if (normalized) {
      messages.push(normalized);
    }
  }
  return messages;
};

export const mergeChatStreamState = (current: ChatStreamState, patch: unknown): ChatStreamState => {
  if (!isObjectRecord(patch)) {
    return current;
  }

  const next: ChatStreamState = { ...current };
  if ("messages" in patch) {
    next.messages = coerceThreadMessages(patch.messages) ?? [];
  }
  if ("context_file_paths" in patch) {
    next.context_file_paths = normalizeContextPaths(patch.context_file_paths);
  }
  if ("title" in patch) {
    next.title = typeof patch.title === "string" || patch.title === null ? patch.title : next.title;
  }
  if ("created_at" in patch && typeof patch.created_at === "string") {
    next.created_at = patch.created_at;
  }
  if ("updated_at" in patch && typeof patch.updated_at === "string") {
    next.updated_at = patch.updated_at;
  }

  return next;
};

const mergeMessageContent = (current: unknown, incoming: unknown): unknown => {
  const currentText = messageText(current);
  const incomingText = messageText(incoming);
  if (!incomingText) {
    return currentText;
  }
  if (!currentText) {
    return incomingText;
  }
  return `${currentText}${incomingText}`;
};

export const applyStreamMessageEvent = (
  current: ChatStreamState,
  payload: unknown,
): ChatStreamState => {
  if (!Array.isArray(payload) || payload.length === 0) {
    return current;
  }

  const incoming = normalizeThreadMessage(payload[0]);
  if (!incoming) {
    return current;
  }

  const messageId = incoming.id ?? createClientId("msg");
  const currentMessages = [...(current.messages ?? [])];
  const existingIndex = currentMessages.findIndex((message) => message.id === messageId);

  if (existingIndex === -1) {
    currentMessages.push({
      ...incoming,
      id: messageId,
      content: messageText(incoming.content),
    });
    return { ...current, messages: currentMessages };
  }

  const existing = currentMessages[existingIndex];
  currentMessages[existingIndex] = {
    ...existing,
    ...incoming,
    id: messageId,
    content: mergeMessageContent(existing.content, incoming.content),
    additional_kwargs: {
      ...(isObjectRecord(existing.additional_kwargs) ? existing.additional_kwargs : {}),
      ...(isObjectRecord(incoming.additional_kwargs) ? incoming.additional_kwargs : {}),
    },
  };
  return { ...current, messages: currentMessages };
};
