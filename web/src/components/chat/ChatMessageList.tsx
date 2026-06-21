import type { ReactNode } from "react";
import type { ChatStatus } from "ai";
import { Bot } from "lucide-react";
import { ConversationContent } from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import type { ConversationMessage } from "@/dataProvider";
import { ChatMessage } from "./ChatMessage";

interface ChatMessageListProps {
  children?: ReactNode;
  contentClassName?: string;
  header?: ReactNode;
  messages: ConversationMessage[];
  scrollClassName?: string;
  status: ChatStatus;
  suppressThinking?: boolean;
  hideContextBadges?: boolean;
  translate: (key: string, options?: unknown) => string;
  onRegenerateMessage?: (message: ConversationMessage) => void;
  onSourceClick: (filePath: string, docRefs?: string[]) => void;
}

export const ChatMessageList = ({
  children,
  contentClassName = "mx-auto w-full max-w-3xl",
  header,
  messages,
  scrollClassName = "overflow-y-auto overscroll-contain",
  status,
  suppressThinking = false,
  hideContextBadges = false,
  translate,
  onRegenerateMessage,
  onSourceClick,
}: ChatMessageListProps) => {
  const lastMessage = messages[messages.length - 1];
  const lastAssistantMessage = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");
  const shouldShowThinking =
    !suppressThinking &&
    status === "streaming" &&
    (!lastMessage ||
      lastMessage.role !== "assistant" ||
      (!lastMessage.content.trim() && lastMessage.status !== "complete"));

  return (
    <ConversationContent className={contentClassName} scrollClassName={scrollClassName}>
      {header}

      {messages.map((message) => (
        <ChatMessage
          key={message.id}
          canRegenerate={
            Boolean(onRegenerateMessage) &&
            status !== "streaming" &&
            message.role === "assistant" &&
            message.id === lastAssistantMessage?.id
          }
          hideContextBadges={hideContextBadges}
          message={message}
          onRegenerate={onRegenerateMessage}
          onSourceClick={onSourceClick}
          translate={translate}
        />
      ))}

      {children}

      {shouldShowThinking && (
        <Message from="assistant">
          <div className="flex items-start gap-4">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-background shadow-sm">
              <Bot className="size-4" />
            </div>
            <MessageContent>
              <Shimmer>{translate("custom.pages.chat.thinking")}</Shimmer>
            </MessageContent>
          </div>
        </Message>
      )}
    </ConversationContent>
  );
};
