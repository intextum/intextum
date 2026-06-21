import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChatStatus } from "ai";
import { ExternalLink, MessageSquare } from "lucide-react";
import { useNavigate } from "react-router";
import { Conversation, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import {
  conversationsApi,
  contentApi,
  type ContentItemInfo,
  type ConversationMessage,
} from "@/dataProvider";
import { useNotify, useTranslate } from "@/lib/app-context";
import { invalidateConversationQueries } from "@/lib/query-client";
import {
  applyStreamMessageEvent,
  buildUserThreadMessage,
  createClientId,
  mergeChatStreamState,
  toConversationMessage,
  toConversationMessages,
  toThreadMessage,
  type ChatStreamState,
} from "@/lib/chat-stream";
import { readSseStream } from "@/lib/sse-stream";
import { reportClientError } from "@/lib/report-client-error";

interface ContentItemChatTabProps {
  file: ContentItemInfo;
  onNavigateToEvidence?: (docRefs: string[], label: string) => void;
  onOpenRelatedItem?: (path: string) => void | Promise<void>;
}

const isAbortError = (error: unknown) =>
  error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";

export const ContentItemChatTab = ({
  file,
  onNavigateToEvidence,
  onOpenRelatedItem,
}: ContentItemChatTabProps) => {
  const translate = useTranslate();
  const notify = useNotify();
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState(() => createClientId("thread"));
  const [streamState, setStreamState] = useState<ChatStreamState>({
    messages: [],
    context_file_paths: [file.path],
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const canChat =
    file.kind !== "folder" &&
    file.status === "COMPLETED" &&
    file.capabilities?.supports_search !== false;
  const messages = useMemo(
    () => toConversationMessages(streamState.messages),
    [streamState.messages],
  );
  const status = (isStreaming ? "streaming" : "ready") as ChatStatus;
  const showContinueAction = messages.length > 0;

  useEffect(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setThreadId(createClientId("thread"));
    setInput("");
    setStreamState({
      messages: [],
      context_file_paths: [file.path],
    });
    setIsStreaming(false);
    setIsImporting(false);
  }, [file.path]);

  const showStreamError = useCallback(
    (error: unknown) => {
      if (isAbortError(error)) {
        return;
      }
      reportClientError(error, undefined, { routeName: "content-item-chat:stream" });
      notify(
        translate("custom.content.chat.stream_failed", {
          defaultValue: "Chat response failed.",
        }),
        { type: "error" },
      );
    },
    [notify, translate],
  );

  const streamRequestMessages = useCallback(
    async (requestMessages: ReturnType<typeof toThreadMessage>[]) => {
      if (isStreaming || !canChat) return;

      const controller = new AbortController();

      setStreamState((current) => ({
        ...current,
        messages: requestMessages,
        context_file_paths: [file.path],
      }));
      setIsStreaming(true);
      abortControllerRef.current = controller;

      try {
        const response = await contentApi.streamChat(
          {
            thread_id: threadId,
            content_path: file.path,
            messages: requestMessages,
          },
          controller.signal,
        );
        if (!response.ok || !response.body) {
          throw new Error(response.statusText || "Document chat stream failed.");
        }
        await readSseStream(response.body, (frame) => {
          if (frame.event === "messages") {
            setStreamState((current) => applyStreamMessageEvent(current, frame.data));
            return;
          }
          if (frame.event === "values") {
            setStreamState((current) => mergeChatStreamState(current, frame.data));
            return;
          }
          if (frame.event === "error") {
            throw new Error("Document chat stream failed.");
          }
        });
      } catch (error) {
        showStreamError(error);
      } finally {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
        setIsStreaming(false);
      }
    },
    [canChat, file.path, isStreaming, showStreamError, threadId],
  );

  const handleSubmit = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text || isStreaming || !canChat) return;

      const userThreadMessage = buildUserThreadMessage(text, [file.path]);
      const userMessage = toConversationMessage(userThreadMessage) as ConversationMessage;
      const optimisticMessages = [...messages, userMessage];
      const requestMessages = optimisticMessages.map(toThreadMessage);

      setInput("");
      await streamRequestMessages(requestMessages);
    },
    [canChat, file.path, isStreaming, messages, streamRequestMessages],
  );

  const handlePromptSubmit = useCallback(
    (message: PromptInputMessage) => {
      void handleSubmit(message.text);
    },
    [handleSubmit],
  );

  const handleRegenerateMessage = useCallback(
    async (message: ConversationMessage) => {
      if (isStreaming || !canChat || message.role !== "assistant") {
        return;
      }
      const messageIndex = messages.findIndex((item) => item.id === message.id);
      if (messageIndex <= 0) {
        return;
      }
      const transcriptBeforeMessage = messages.slice(0, messageIndex);
      if (transcriptBeforeMessage[transcriptBeforeMessage.length - 1]?.role !== "user") {
        return;
      }
      await streamRequestMessages(transcriptBeforeMessage.map(toThreadMessage));
    },
    [canChat, isStreaming, messages, streamRequestMessages],
  );

  const handleStop = () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setIsStreaming(false);
  };

  const handleSourceClick = async (filePath: string, docRefs?: string[]) => {
    const refs = docRefs ?? [];
    if (filePath === file.path) {
      if (refs.length > 0) {
        onNavigateToEvidence?.(refs, file.display_name || file.name);
      }
      return;
    }
    if (onOpenRelatedItem) {
      await onOpenRelatedItem(filePath);
      if (refs.length > 0) {
        onNavigateToEvidence?.(refs, filePath);
      }
    }
  };

  const handleContinueInChat = async () => {
    if (messages.length === 0 || isStreaming || isImporting) return;
    setIsImporting(true);
    try {
      const imported = await conversationsApi.import({
        title: file.display_name || file.name,
        context_file_paths: [file.path],
        messages: messages.map(toThreadMessage),
      });
      void invalidateConversationQueries();
      navigate(`/chat/${imported.conversation_id}`);
    } catch (error) {
      reportClientError(error, undefined, { routeName: "content-item-chat:import" });
      notify(
        translate("custom.content.chat.import_failed", {
          defaultValue: "Failed to continue this chat.",
        }),
        { type: "error" },
      );
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {!canChat ? (
        <div className="flex min-h-0 flex-1 items-center justify-center p-6 text-center">
          <div className="max-w-xs space-y-2">
            <MessageSquare className="mx-auto h-6 w-6 text-muted-foreground" />
            <div className="text-sm font-medium">
              {translate("custom.content.chat.unavailable_title", {
                defaultValue: "Chat is unavailable",
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              {translate("custom.content.chat.unavailable_description", {
                defaultValue: "Process this document before starting a document chat.",
              })}
            </p>
          </div>
        </div>
      ) : (
        <>
          {showContinueAction ? (
            <div className="flex shrink-0 items-center justify-end border-b bg-background/95 px-3 py-1.5 backdrop-blur-sm">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
                disabled={isStreaming || isImporting}
                onClick={handleContinueInChat}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                {translate("custom.content.chat.continue", { defaultValue: "Continue in Chat" })}
              </Button>
            </div>
          ) : null}
          <Conversation className="min-h-0 flex-1">
            {messages.length === 0 && !isStreaming ? (
              <div className="flex h-full items-center justify-center p-6 text-center">
                <div className="max-w-xs space-y-2">
                  <MessageSquare className="mx-auto h-6 w-6 text-muted-foreground" />
                  <div className="text-sm font-medium">
                    {translate("custom.content.chat.empty_title", {
                      defaultValue: "Ask about this document",
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {translate("custom.content.chat.empty_description", {
                      defaultValue: "This chat stays temporary until you continue it in Chat.",
                    })}
                  </p>
                </div>
              </div>
            ) : (
              <ChatMessageList
                messages={messages}
                status={status}
                hideContextBadges
                translate={translate}
                onRegenerateMessage={handleRegenerateMessage}
                onSourceClick={handleSourceClick}
              />
            )}
            <ConversationScrollButton className="bottom-3 h-8 w-8" />
          </Conversation>

          <div className="shrink-0 border-t bg-background p-2">
            <PromptInput
              onSubmit={handlePromptSubmit}
              className="rounded-xl border bg-muted/30 shadow-sm transition-colors focus-within:bg-background"
            >
              <PromptInputBody>
                <PromptInputTextarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder={translate("custom.content.chat.placeholder", {
                    defaultValue: "Ask about this document...",
                  })}
                  className="min-h-[60px] bg-transparent text-sm"
                  disabled={isStreaming}
                />
              </PromptInputBody>
              <PromptInputFooter>
                <PromptInputTools />
                <PromptInputSubmit
                  status={status}
                  onStop={handleStop}
                  disabled={!input.trim() || !canChat}
                />
              </PromptInputFooter>
            </PromptInput>
          </div>
        </>
      )}
    </div>
  );
};
