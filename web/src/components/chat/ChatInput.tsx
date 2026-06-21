import { useMemo, useState } from "react";
import {
  BookOpenText,
  Check,
  ChevronDown,
  FileText,
  FolderOpen,
  MessageSquareText,
  X,
} from "lucide-react";
import {
  PromptInput,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputButton,
  PromptInputHeader,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { shouldDisablePromptSubmit } from "@/lib/chat-input-state";
import type { ChatStatus } from "ai";
import type { ChatExperienceMode } from "@/lib/chat-experience-state";

interface ChatInputProps {
  mode: ChatExperienceMode;
  status: ChatStatus;
  isLoading: boolean;
  disableSend?: boolean;
  onModeChange: (mode: ChatExperienceMode) => void;
  onStop: () => void;
  onSubmit: (message: { text: string }) => void | Promise<void>;
  inputText: string;
  onInputTextChange: (value: string) => void;
  onOpenContextPicker: () => void;
  contextFilePaths: string[];
  onRemoveContextFile: (path: string) => void;
  onClearContextFiles: () => void;
  translate: (key: string, options?: unknown) => string;
  autoFocus?: boolean;
  inputPlaceholder?: string;
}

export const ChatInput = ({
  mode,
  status,
  isLoading,
  disableSend = false,
  onModeChange,
  onStop,
  onSubmit,
  inputText,
  onInputTextChange,
  onOpenContextPicker,
  contextFilePaths,
  onRemoveContextFile,
  onClearContextFiles,
  translate,
  autoFocus,
  inputPlaceholder,
}: ChatInputProps) => {
  const [contextManagerOpen, setContextManagerOpen] = useState(false);
  const ActiveModeIcon = mode === "research" ? BookOpenText : MessageSquareText;
  const collapsedContext = contextFilePaths.length > 3;
  const visibleContextPaths = useMemo(
    () => (collapsedContext ? contextFilePaths.slice(0, 3) : contextFilePaths),
    [collapsedContext, contextFilePaths],
  );
  const fileNameForPath = (path: string) => path.split("/").pop() || path;

  const handleSubmit = async (message: { text: string }) => {
    if (disableSend) return;
    if (!message.text.trim()) return;
    await onSubmit(message);
    onInputTextChange("");
  };

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PromptInput
        onSubmit={handleSubmit}
        className="rounded-xl border bg-muted/30 shadow-sm transition-colors focus-within:bg-background"
      >
        {contextFilePaths.length > 0 && (
          <PromptInputHeader className="border-b py-1.5">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
              {visibleContextPaths.map((path) => {
                const fileName = fileNameForPath(path);
                return (
                  <Badge
                    key={path}
                    variant="secondary"
                    className="h-6 max-w-full gap-1 px-1.5 pr-0.5 text-xs font-normal"
                  >
                    <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
                    <span className="max-w-[180px] truncate" title={path}>
                      {fileName}
                    </span>
                    <button
                      type="button"
                      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm hover:bg-muted-foreground/20"
                      onClick={() => onRemoveContextFile(path)}
                      aria-label={translate("custom.pages.chat.context.remove_file", {
                        file: fileName,
                      })}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                );
              })}
              {collapsedContext && (
                <button
                  type="button"
                  className="h-6 rounded-full px-2 text-xs text-muted-foreground hover:bg-muted"
                  onClick={() => setContextManagerOpen(true)}
                >
                  {translate("custom.pages.chat.context.more_count", {
                    count: contextFilePaths.length - visibleContextPaths.length,
                  })}
                </button>
              )}
            </div>
            <button
              type="button"
              className="h-6 rounded px-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setContextManagerOpen(true)}
              title={translate("custom.pages.chat.context.manage")}
            >
              {translate("custom.pages.chat.context.manage")}
            </button>
          </PromptInputHeader>
        )}
        <PromptInputBody>
          <PromptInputTextarea
            value={inputText}
            onChange={(e) => onInputTextChange(e.target.value)}
            placeholder={inputPlaceholder ?? translate("custom.pages.chat.input_placeholder")}
            className="min-h-[80px] bg-transparent"
            autoFocus={autoFocus}
            disabled={disableSend}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputTools>
            <PromptInputActionMenu>
              <PromptInputActionMenuTrigger
                disabled={isLoading}
                className="h-8 gap-1.5 px-2 text-xs text-muted-foreground"
                tooltip={translate("custom.pages.chat.tool_menu")}
              >
                <ActiveModeIcon className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {translate(
                    mode === "research"
                      ? "custom.pages.chat.mode_research"
                      : "custom.pages.chat.mode_chat",
                  )}
                </span>
                <ChevronDown className="h-3.5 w-3.5" />
              </PromptInputActionMenuTrigger>
              <PromptInputActionMenuContent className="w-48">
                <PromptInputActionMenuItem onSelect={() => onModeChange("chat")}>
                  <MessageSquareText className="mr-2 h-4 w-4" />
                  <span className="flex-1">{translate("custom.pages.chat.mode_chat")}</span>
                  {mode === "chat" ? <Check className="h-4 w-4" /> : null}
                </PromptInputActionMenuItem>
                <PromptInputActionMenuItem onSelect={() => onModeChange("research")}>
                  <BookOpenText className="mr-2 h-4 w-4" />
                  <span className="flex-1">{translate("custom.pages.chat.mode_research")}</span>
                  {mode === "research" ? <Check className="h-4 w-4" /> : null}
                </PromptInputActionMenuItem>
              </PromptInputActionMenuContent>
            </PromptInputActionMenu>
            <PromptInputButton
              className="h-8 gap-1.5 px-2 text-xs text-muted-foreground"
              onClick={onOpenContextPicker}
              tooltip={translate("custom.pages.chat.context.add_files")}
            >
              <FolderOpen className="h-4 w-4" />
              <span className="hidden sm:inline">
                {contextFilePaths.length > 0
                  ? translate("custom.pages.chat.context.active_count", {
                      count: contextFilePaths.length,
                    })
                  : translate("custom.pages.chat.context.add_files")}
              </span>
            </PromptInputButton>
          </PromptInputTools>
          <PromptInputSubmit
            status={status}
            onStop={onStop}
            disabled={shouldDisablePromptSubmit({
              disableSend,
              inputText,
              isLoading,
            })}
          />
        </PromptInputFooter>
      </PromptInput>
      <p className="mt-3 text-center text-[10px] text-muted-foreground">
        {translate("custom.pages.chat.disclaimer")}
      </p>

      <Dialog open={contextManagerOpen} onOpenChange={setContextManagerOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.chat.context.manage_title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.chat.context.manage_description", {
                count: contextFilePaths.length,
              })}
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[420px] rounded-md border">
            <div className="space-y-1 p-2">
              {contextFilePaths.map((path) => {
                const fileName = fileNameForPath(path);
                const folderPath = path.split("/").slice(0, -1).join("/");
                return (
                  <div
                    key={path}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/40"
                  >
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <p className="truncate text-sm" title={path}>
                        {fileName}
                      </p>
                      {folderPath && (
                        <p className="truncate text-xs text-muted-foreground">{folderPath}</p>
                      )}
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => onRemoveContextFile(path)}
                      title={translate("custom.pages.chat.context.remove_file", {
                        file: fileName,
                      })}
                    >
                      <X />
                    </Button>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
          <DialogFooter className="gap-2 sm:justify-between">
            <Button type="button" variant="outline" onClick={onOpenContextPicker}>
              <FolderOpen className="h-4 w-4" />
              {translate("custom.pages.chat.context.add_more")}
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={onClearContextFiles}>
                {translate("custom.pages.chat.context.clear_all")}
              </Button>
              <Button type="button" onClick={() => setContextManagerOpen(false)}>
                {translate("custom.pages.chat.context.done")}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
