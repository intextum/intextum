import type { ChatStatus } from "ai";
import {
  BarChart3,
  BookOpenText,
  FileSearch,
  FileText,
  ListChecks,
  Search,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { ChatInput } from "@/components/chat/ChatInput";
import type { ChatPromptPreset } from "@/dataProvider";
import type { ChatExperienceMode } from "@/lib/chat-experience-state";
import { localizedPresetText, promptPresetRequirementMessageKey } from "@/lib/chat-prompt-presets";

type TranslateFn = (key: string, options?: unknown) => string;

type ChatEmptyStateProps = {
  mode: ChatExperienceMode;
  status: ChatStatus;
  disableSend: boolean;
  composerText: string;
  contextFilePaths: string[];
  displayName: string;
  inputPlaceholder: string;
  locale: string;
  promptPresets: ChatPromptPreset[];
  translate: TranslateFn;
  onClearContextFiles: () => void;
  onInputTextChange: (value: string) => void;
  onModeChange: (mode: ChatExperienceMode) => void;
  onOpenContextPicker: () => void;
  onPresetClick: (preset: ChatPromptPreset) => void;
  onRemoveContextFile: (path: string) => void;
  onStop: () => void;
  onSubmit: (message: { text: string }) => void | Promise<void>;
};

const presetIcons: Record<ChatPromptPreset["icon"], LucideIcon> = {
  "bar-chart": BarChart3,
  "book-open": BookOpenText,
  "file-search": FileSearch,
  "file-text": FileText,
  "list-checks": ListChecks,
  search: Search,
  sparkles: Sparkles,
};

export function ChatEmptyState({
  mode,
  status,
  disableSend,
  composerText,
  contextFilePaths,
  displayName,
  inputPlaceholder,
  locale,
  promptPresets,
  translate,
  onClearContextFiles,
  onInputTextChange,
  onModeChange,
  onOpenContextPicker,
  onPresetClick,
  onRemoveContextFile,
  onStop,
  onSubmit,
}: ChatEmptyStateProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4">
      <div className="w-full max-w-3xl space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-semibold tracking-tight">
            {mode === "research"
              ? translate("custom.pages.research.title")
              : translate("custom.pages.chat.welcome", { name: displayName })}
          </h1>
          <p className="mt-2 text-muted-foreground">
            {translate(
              mode === "research"
                ? "custom.pages.chat.research_welcome_desc"
                : "custom.pages.chat.welcome_desc",
            )}
          </p>
        </div>

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
          autoFocus
        />

        {promptPresets.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {promptPresets.map((preset) => {
              const Icon = presetIcons[preset.icon] ?? Sparkles;
              const requirement = promptPresetRequirementMessageKey(
                preset,
                contextFilePaths.length,
              );
              const requirementText =
                requirement === "min"
                  ? translate("custom.pages.chat.presets.min_files", {
                      count: preset.context.min_files,
                    })
                  : requirement === "max"
                    ? translate("custom.pages.chat.presets.max_files", {
                        count: preset.context.max_files,
                      })
                    : preset.mode === "research"
                      ? translate("custom.pages.chat.mode_research")
                      : translate("custom.pages.chat.mode_chat");
              return (
                <button
                  key={preset.id}
                  type="button"
                  className="flex min-h-28 items-start gap-3 rounded-xl border bg-muted/30 p-4 text-left text-sm transition-colors hover:border-foreground/20 hover:bg-muted/50 disabled:cursor-pointer disabled:opacity-70"
                  onClick={() => onPresetClick(preset)}
                >
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 space-y-1">
                    <span className="block font-medium text-foreground">
                      {localizedPresetText(preset.label, locale)}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {localizedPresetText(preset.description, locale)}
                    </span>
                    <span className="inline-flex rounded border bg-background px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-normal text-muted-foreground">
                      {requirementText}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">
            <div className="flex items-start gap-3">
              <BookOpenText className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{translate("custom.pages.research.description")}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
