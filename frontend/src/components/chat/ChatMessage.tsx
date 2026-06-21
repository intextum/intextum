import { useCallback, useMemo, useState } from "react";
import { Bot, Check, ChevronDown, Copy, FileText, RefreshCcw, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
  MessageToolbar,
} from "@/components/ai-elements/message";
import { Sources, SourcesContent, SourcesTrigger } from "@/components/ai-elements/sources";
import { extractContextPathsFromMessage } from "@/hooks/chat-context";
import type {
  ConversationMessage as ChatMessageRecord,
  ResearchReportMessageMetadata,
} from "@/dataProvider";
import { buildAssistantResponseExportDocument, buildExportLabels } from "@/lib/chat-export";
import {
  buildChatPanelSources,
  isReviewedEnrichmentSource,
  sourceContextLine,
  sourceDisplayPath,
  sourceDisplayTitle,
} from "@/lib/chat-source-previews";
import { useNotify } from "@/lib/app-context";
import { reportClientError } from "@/lib/report-client-error";
import { ResearchConversationBlock } from "./ResearchConversationBlock";
import { ResponseExportMenu } from "./ResponseExportMenu";
import { CitationText } from "./CitationText";

interface ChatMessageProps {
  canRegenerate?: boolean;
  hideContextBadges?: boolean;
  message: ChatMessageRecord;
  onSourceClick: (filePath: string, docRefs?: string[]) => void;
  onRegenerate?: (message: ChatMessageRecord) => void;
  translate: (key: string, options?: unknown) => string;
}

export const ChatMessage = ({
  canRegenerate = false,
  hideContextBadges = false,
  message,
  onSourceClick,
  onRegenerate,
  translate,
}: ChatMessageProps) => {
  const notify = useNotify();
  const [copied, setCopied] = useState(false);
  const exportLabels = useMemo(() => buildExportLabels(translate), [translate]);
  const exportUrlOptions = useMemo(
    () => ({
      absoluteBaseUrl: typeof window !== "undefined" ? window.location.origin : undefined,
    }),
    [],
  );
  const messageContextFilePaths = useMemo(() => extractContextPathsFromMessage(message), [message]);
  const researchReport = useMemo<ResearchReportMessageMetadata | null>(() => {
    const metadata = message.metadata;
    if (
      !metadata ||
      typeof metadata !== "object" ||
      metadata.kind !== "research_report" ||
      !Array.isArray((metadata as { sections?: unknown }).sections) ||
      !Array.isArray((metadata as { sources?: unknown }).sources)
    ) {
      return null;
    }
    return metadata as unknown as ResearchReportMessageMetadata;
  }, [message.metadata]);

  const panelSources = useMemo(() => {
    if (researchReport) {
      return [];
    }
    return buildChatPanelSources(message.sources ?? []);
  }, [message.sources, researchReport]);

  const exportDocument = useMemo(() => {
    if (message.role !== "assistant" || researchReport || !message.content.trim()) {
      return null;
    }
    return buildAssistantResponseExportDocument(message, exportLabels, exportUrlOptions);
  }, [exportLabels, exportUrlOptions, message, researchReport]);
  const canCopy = Boolean(message.content.trim());
  const showActions = canCopy || exportDocument || (canRegenerate && onRegenerate);

  const handleCopy = useCallback(async () => {
    if (!message.content.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch (error) {
      reportClientError(error, undefined, { routeName: "chat:copy-message" });
      notify(
        translate("custom.pages.chat.actions.copy_failed", {
          defaultValue: "Failed to copy message.",
        }),
        { type: "error" },
      );
    }
  }, [message.content, notify, translate]);

  if (researchReport) {
    return (
      <ResearchConversationBlock
        report={researchReport}
        events={[]}
        isLoading={false}
        translate={translate}
        onSourceClick={onSourceClick}
      />
    );
  }

  return (
    <Message from={message.role === "user" ? "user" : "assistant"}>
      <div
        className={`flex items-start gap-4 ${message.role === "user" ? "flex-row-reverse" : ""}`}
      >
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-background shadow-sm">
          {message.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
        </div>
        <div
          className={`relative flex min-w-0 max-w-full flex-col ${
            message.role === "user" ? "items-end" : "items-start"
          }`}
        >
          <MessageContent>
            {message.role === "user" &&
              !hideContextBadges &&
              messageContextFilePaths.length > 0 && (
                <div className="mb-2 flex flex-wrap items-center gap-1.5">
                  {messageContextFilePaths.map((path) => (
                    <Badge key={path} variant="outline" className="text-[10px] font-normal">
                      {path.split("/").pop() || path}
                    </Badge>
                  ))}
                </div>
              )}

            {message.role === "assistant" ? (
              <CitationText
                text={message.content}
                sources={message.sources}
                onSourceClick={onSourceClick}
              />
            ) : (
              <div className="whitespace-pre-wrap">{message.content}</div>
            )}

            {panelSources.length > 0 && (
              <Sources className="mt-4">
                <SourcesTrigger count={panelSources.length}>
                  <p className="font-medium">
                    {translate("custom.pages.chat.tools.used_sources", {
                      count: panelSources.length,
                    })}
                  </p>
                  <ChevronDown className="h-4 w-4" />
                </SourcesTrigger>
                <SourcesContent>
                  <div className="mt-2 grid gap-2">
                    {panelSources.map((source, idx) => (
                      <div
                        key={
                          typeof source.citation_index === "number"
                            ? `cite-${source.citation_index}`
                            : `file-${idx}`
                        }
                        className="rounded-md border bg-muted/30 p-2"
                      >
                        <button
                          type="button"
                          title={sourceDisplayTitle(source)}
                          onClick={() => onSourceClick(source.file_path, source.doc_refs)}
                          className="flex w-full items-center gap-2 rounded-sm text-left text-xs transition-colors hover:text-foreground"
                        >
                          {typeof source.citation_index === "number" && (
                            <span className="inline-flex items-center justify-center rounded bg-muted px-1 py-0 text-[10px] font-medium text-primary">
                              [{source.citation_index}]
                            </span>
                          )}
                          <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                          <div className="min-w-0 flex-1">
                            <div className="flex min-w-0 flex-wrap items-center gap-2">
                              <span className="min-w-0 truncate font-medium">
                                {sourceDisplayTitle(source)}
                              </span>
                              {isReviewedEnrichmentSource(source) && (
                                <Badge variant="secondary" className="text-[10px]">
                                  {translate(
                                    "custom.pages.chat.tools.source_badge_reviewed_enrichment",
                                  )}
                                </Badge>
                              )}
                            </div>
                            {sourceDisplayPath(source) && (
                              <div className="truncate text-[11px] text-muted-foreground">
                                {sourceDisplayPath(source)}
                              </div>
                            )}
                            {sourceContextLine(source, translate) && (
                              <div className="truncate text-[11px] text-muted-foreground">
                                {sourceContextLine(source, translate)}
                              </div>
                            )}
                          </div>
                          {source.page_numbers.length > 0 && (
                            <Badge
                              variant="secondary"
                              className="h-3.5 shrink-0 px-1 py-0 font-mono text-[9px]"
                            >
                              p. {source.page_numbers.join(", ")}
                            </Badge>
                          )}
                        </button>
                        {source.preview_images.length > 0 && (
                          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                            {source.preview_images.map((imageUrl, imageIndex) => (
                              <button
                                key={`${source.file_path}-${imageUrl}-${imageIndex}`}
                                type="button"
                                className="overflow-hidden rounded border bg-background transition-colors hover:border-primary/40"
                                onClick={() => onSourceClick(source.file_path, source.doc_refs)}
                                title={sourceDisplayTitle(source)}
                              >
                                <img
                                  src={imageUrl}
                                  alt={`${sourceDisplayTitle(source)} ${imageIndex + 1}`}
                                  loading="lazy"
                                  className="aspect-[4/3] w-full object-cover"
                                />
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </SourcesContent>
              </Sources>
            )}
          </MessageContent>
          {showActions ? (
            <MessageToolbar className="mt-1 justify-end gap-2">
              <MessageActions
                className={
                  message.role === "user"
                    ? "justify-end text-muted-foreground"
                    : "justify-start text-muted-foreground"
                }
              >
                {canRegenerate && onRegenerate ? (
                  <MessageAction
                    label={translate("custom.pages.chat.actions.regenerate", {
                      defaultValue: "Regenerate message",
                    })}
                    tooltip={translate("custom.pages.chat.actions.regenerate", {
                      defaultValue: "Regenerate message",
                    })}
                    onClick={() => onRegenerate(message)}
                  >
                    <RefreshCcw className="size-3.5" />
                  </MessageAction>
                ) : null}
                {canCopy ? (
                  <MessageAction
                    label={translate("custom.pages.chat.actions.copy", {
                      defaultValue: "Copy message",
                    })}
                    tooltip={translate("custom.pages.chat.actions.copy", {
                      defaultValue: "Copy message",
                    })}
                    onClick={() => {
                      void handleCopy();
                    }}
                  >
                    {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                  </MessageAction>
                ) : null}
                {exportDocument ? (
                  <ResponseExportMenu document={exportDocument} translate={translate} />
                ) : null}
              </MessageActions>
            </MessageToolbar>
          ) : null}
        </div>
      </div>
    </Message>
  );
};
