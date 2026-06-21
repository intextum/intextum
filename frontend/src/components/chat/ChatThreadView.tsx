import type { ChatStatus } from "ai";
import { Conversation, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { ResearchConversationBlock } from "@/components/chat/ResearchConversationBlock";
import { ResponseExportMenu } from "@/components/chat/ResponseExportMenu";
import type { ConversationMessage, ConversationRun } from "@/dataProvider";
import type { ConversationProgressEvent } from "@/hooks/useConversationRun";
import type { ExportDocument } from "@/lib/chat-export";
import type { ChatExperienceMode } from "@/lib/chat-experience-state";

type TranslateFn = (key: string, options?: unknown) => string;

type ChatThreadViewProps = {
  activeRunMode: ConversationRun["mode"] | null;
  composerText: string;
  contextFilePaths: string[];
  conversationExportDocument: ExportDocument | null;
  disableSend: boolean;
  hasResearchContent: boolean;
  inputPlaceholder: string;
  isLoading: boolean;
  messages: ConversationMessage[];
  mode: ChatExperienceMode;
  progressEvents: ConversationProgressEvent[];
  status: ChatStatus;
  translate: TranslateFn;
  onClearContextFiles: () => void;
  onInputTextChange: (value: string) => void;
  onModeChange: (mode: ChatExperienceMode) => void;
  onOpenContextPicker: () => void;
  onRegenerateMessage: (message: ConversationMessage) => void;
  onRemoveContextFile: (path: string) => void;
  onSourceClick: (filePath: string, docRefs?: string[]) => void | Promise<void>;
  onStop: () => void;
  onSubmit: (message: { text: string }) => void | Promise<void>;
};

export function ChatThreadView({
  activeRunMode,
  composerText,
  contextFilePaths,
  conversationExportDocument,
  disableSend,
  hasResearchContent,
  inputPlaceholder,
  isLoading,
  messages,
  mode,
  progressEvents,
  status,
  translate,
  onClearContextFiles,
  onInputTextChange,
  onModeChange,
  onOpenContextPicker,
  onRegenerateMessage,
  onRemoveContextFile,
  onSourceClick,
  onStop,
  onSubmit,
}: ChatThreadViewProps) {
  return (
    <>
      <Conversation>
        <ChatMessageList
          header={
            conversationExportDocument ? (
              <div className="flex justify-end">
                <ResponseExportMenu
                  document={conversationExportDocument}
                  triggerLabel={translate("custom.exports.conversation_trigger")}
                  translate={translate}
                />
              </div>
            ) : null
          }
          messages={messages}
          status={status}
          suppressThinking={hasResearchContent}
          translate={translate}
          onRegenerateMessage={hasResearchContent ? undefined : onRegenerateMessage}
          onSourceClick={onSourceClick}
        >
          {hasResearchContent ? (
            <ResearchConversationBlock
              report={null}
              events={progressEvents}
              isLoading={activeRunMode === "research" && isLoading}
              translate={translate}
              onSourceClick={onSourceClick}
            />
          ) : null}
        </ChatMessageList>
        <ConversationScrollButton />
      </Conversation>

      <div className="border-t p-4 pb-6">
        <ChatInput
          mode={mode}
          status={status}
          isLoading={disableSend}
          disableSend={disableSend}
          onModeChange={onModeChange}
          onStop={onStop}
          onSubmit={onSubmit}
          inputText={composerText}
          onInputTextChange={onInputTextChange}
          onOpenContextPicker={onOpenContextPicker}
          contextFilePaths={contextFilePaths}
          onRemoveContextFile={onRemoveContextFile}
          onClearContextFiles={onClearContextFiles}
          translate={translate}
          inputPlaceholder={inputPlaceholder}
        />
      </div>
    </>
  );
}
