import { useCallback, useMemo, useState } from "react";
import type { ChatStatus } from "ai";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useGetIdentity, useLocaleState, useNotify, useTranslate } from "@/lib/app-context";
import { ContentItemDetailsDialog } from "@/components/ContentItemDetailsDialog";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import { ChatContextPickerDialog } from "@/components/chat/ChatContextPickerDialog";
import { ChatThreadView } from "@/components/chat/ChatThreadView";
import { useChatConversationActions } from "@/hooks/useChatConversationActions";
import {
  useChatConversationLoader,
  useChatConversationRouteLoad,
} from "@/hooks/useChatConversationLoader";
import { useChatContextControls } from "@/hooks/useChatContextControls";
import { useChatPromptPresets } from "@/hooks/useChatPromptPresets";
import { useChatRouteState } from "@/hooks/useChatRouteState";
import { useChatSourceDetails } from "@/hooks/useChatSourceDetails";
import { useConversationRun } from "@/hooks/useConversationRun";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { buildConversationExportDocument, buildExportLabels } from "@/lib/chat-export";
import { invalidateConversationQueries } from "@/lib/query-client";
import { reportClientError } from "@/lib/report-client-error";
import { createClientId, toConversationMessages } from "@/lib/chat-stream";
import {
  buildChatExperienceSearch,
  readChatExperienceState,
  type ChatExperienceMode,
} from "@/lib/chat-experience-state";
import {
  shouldResetResearchComposerMode,
  shouldShowTransientResearchBlock,
} from "@/lib/chat-research-state";

export const ChatPage = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const translate = useTranslate();
  const [locale] = useLocaleState();
  useDocumentTitle(translate("custom.pages.chat.title"));
  const notify = useNotify();
  const { identity } = useGetIdentity();
  const chatExperience = useMemo(() => readChatExperienceState(searchParams), [searchParams]);

  const defaultPendingThreadId = useMemo(
    () => (conversationId ? null : createClientId("thread")),
    [conversationId],
  );
  const routeScopeKey = conversationId
    ? `conversation:${conversationId}`
    : `new:${defaultPendingThreadId}`;

  const { detailsOpen, handleSourceClick, highlightRefs, selectedFile, setDetailsOpen } =
    useChatSourceDetails({ notify, translate });
  const [composerText, setComposerText] = useState("");
  const {
    contextFilePaths,
    contextFilePathsRef,
    conversationTitle,
    loadedMessages,
    pendingThreadId,
    resetPendingThread,
    setContextFilePathsForScope,
    setConversationTitle,
    setCurrentContextFilePaths,
    syncLoadedMessages,
    updateCurrentContextFilePaths,
  } = useChatRouteState({ defaultPendingThreadId, routeScopeKey });

  const activeThreadId = conversationId ?? pendingThreadId ?? null;
  const exportLabels = useMemo(() => buildExportLabels(translate), [translate]);
  const exportUrlOptions = useMemo(() => ({ absoluteBaseUrl: window.location.origin }), []);

  const promptPresets = useChatPromptPresets({ notify, translate });

  const setChatExperienceMode = useCallback(
    (mode: ChatExperienceMode) => {
      setSearchParams(buildChatExperienceSearch(searchParams, { mode }), { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleRunError = useCallback(
    (error: unknown) => {
      reportClientError(error, undefined, { routeName: "chat:run" });
      notify(
        translate("custom.pages.chat.stream_failed", {
          _: "Chat response failed.",
        }),
        { type: "error" },
      );
      if (!conversationId) {
        resetPendingThread();
      }
    },
    [conversationId, notify, resetPendingThread, translate],
  );

  const { handleConversationLoadError, loadConversation } = useChatConversationLoader({
    conversationId,
    navigate,
    notify,
    setConversationTitle,
    setCurrentContextFilePaths,
    syncLoadedMessages,
    translate,
  });

  const handleConversationRunSettled = useCallback(
    (
      settledConversationId: string,
      mode: "chat" | "research",
      status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED",
    ) => {
      void invalidateConversationQueries();
      void loadConversation(settledConversationId);
      if (
        shouldResetResearchComposerMode({
          currentMode: chatExperience.mode,
          activeThreadId,
          settledConversationId,
          settledMode: mode,
          status,
        })
      ) {
        setChatExperienceMode("chat");
      }
    },
    [activeThreadId, chatExperience.mode, loadConversation, setChatExperienceMode],
  );

  const { values, submit, stop, isLoading, progressEvents, activeRunMode, joinCreatedRun } =
    useConversationRun({
      activeConversationId: activeThreadId,
      onError: handleRunError,
      onRunSettled: handleConversationRunSettled,
    });

  useChatConversationRouteLoad({
    activeThreadId,
    conversationId,
    handleConversationLoadError,
    isLoading,
    setConversationTitle,
    setCurrentContextFilePaths,
    syncLoadedMessages,
  });

  const rawStreamMessages = Array.isArray(values.messages) ? values.messages : undefined;
  const streamMessages = useMemo(
    () => toConversationMessages(rawStreamMessages),
    [rawStreamMessages],
  );

  const messages = useMemo(
    () => (streamMessages.length > 0 ? streamMessages : loadedMessages),
    [loadedMessages, streamMessages],
  );
  const conversationExportDocument = useMemo(() => {
    if (messages.length === 0) {
      return null;
    }
    return buildConversationExportDocument(
      {
        title: conversationTitle,
        messages,
      },
      exportLabels,
      exportUrlOptions,
    );
  }, [conversationTitle, exportLabels, exportUrlOptions, messages]);

  const chatStatus: ChatStatus = isLoading ? "streaming" : "ready";

  const { applyPromptPreset, handleRegenerateMessage, handleStop, handleSubmit } =
    useChatConversationActions({
      activeThreadId,
      contextFilePathsRef,
      conversationId,
      isLoading,
      joinCreatedRun,
      loadConversation,
      loadedMessages,
      locale,
      messages,
      mode: chatExperience.mode,
      navigate,
      notify,
      pendingThreadId,
      searchParams,
      setChatExperienceMode,
      setComposerText,
      setContextFilePathsForScope,
      streamMessages,
      submit,
      syncLoadedMessages,
      stop,
      translate,
    });

  const {
    contextPickerOpen,
    handleAddContextPaths,
    handleClearContextFiles,
    handleContextPickerOpenChange,
    handleOpenContextPicker,
    handlePresetClick,
    handleRemoveContextFile,
  } = useChatContextControls({
    applyPromptPreset,
    contextFilePaths,
    contextFilePathsRef,
    locale,
    notify,
    setChatExperienceMode,
    setComposerText,
    setCurrentContextFilePaths,
    translate,
    updateCurrentContextFilePaths,
  });

  const hasResearchContent = shouldShowTransientResearchBlock({
    activeRunMode,
    progressEventCount: progressEvents.length,
  });
  const isNewChat = !conversationId && messages.length === 0 && !isLoading && !hasResearchContent;
  const hasMessages = messages.length > 0 || isLoading || hasResearchContent;

  const displayName = identity?.fullName || "";

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col bg-background">
        {isNewChat && !hasMessages ? (
          <ChatEmptyState
            mode={chatExperience.mode}
            status={chatStatus}
            disableSend={isLoading}
            composerText={composerText}
            contextFilePaths={contextFilePaths}
            displayName={displayName}
            inputPlaceholder={translate(
              chatExperience.mode === "research"
                ? "custom.pages.research.prompt_placeholder"
                : "custom.pages.chat.input_placeholder",
            )}
            locale={locale}
            promptPresets={promptPresets}
            translate={translate}
            onClearContextFiles={handleClearContextFiles}
            onInputTextChange={setComposerText}
            onModeChange={setChatExperienceMode}
            onOpenContextPicker={handleOpenContextPicker}
            onPresetClick={(preset) => {
              void handlePresetClick(preset);
            }}
            onRemoveContextFile={handleRemoveContextFile}
            onStop={handleStop}
            onSubmit={handleSubmit}
          />
        ) : (
          <ChatThreadView
            activeRunMode={activeRunMode}
            composerText={composerText}
            contextFilePaths={contextFilePaths}
            conversationExportDocument={conversationExportDocument}
            disableSend={isLoading}
            hasResearchContent={hasResearchContent}
            inputPlaceholder={translate(
              chatExperience.mode === "research"
                ? "custom.pages.research.prompt_placeholder"
                : "custom.pages.chat.input_placeholder",
            )}
            isLoading={isLoading}
            messages={messages}
            mode={chatExperience.mode}
            progressEvents={progressEvents}
            status={chatStatus}
            translate={translate}
            onClearContextFiles={handleClearContextFiles}
            onInputTextChange={setComposerText}
            onModeChange={setChatExperienceMode}
            onOpenContextPicker={handleOpenContextPicker}
            onRegenerateMessage={handleRegenerateMessage}
            onRemoveContextFile={handleRemoveContextFile}
            onSourceClick={handleSourceClick}
            onStop={handleStop}
            onSubmit={handleSubmit}
          />
        )}
      </div>

      <ChatContextPickerDialog
        open={contextPickerOpen}
        onOpenChange={handleContextPickerOpenChange}
        onAddPaths={handleAddContextPaths}
        translate={translate}
      />

      <ContentItemDetailsDialog
        file={selectedFile}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        initialHighlightRefs={highlightRefs}
      />
    </>
  );
};
