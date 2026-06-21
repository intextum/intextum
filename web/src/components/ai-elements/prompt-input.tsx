"use client";

import type { FileUIPart } from "ai";
import type { ComponentProps, FormEvent, HTMLAttributes } from "react";

import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { InputGroup } from "@/components/ui/input-group";
import { cn } from "@/lib/utils";
import { ImageIcon } from "lucide-react";
import { useCallback } from "react";
import {
  PromptInputAttachmentsProvider,
  usePromptInputAttachments,
} from "./prompt-input-attachments-context";
import {
  usePromptInputFileHandling,
  type PromptInputFileError,
} from "./prompt-input-content-handling";
import { usePromptInputController } from "./prompt-input-provider";
import {
  LocalReferencedSourcesContext,
  usePromptInputReferencedSourcesState,
} from "./prompt-input-referenced-sources";
import { usePromptInputSubmit } from "./prompt-input-submit";

export type PromptInputActionAddAttachmentsProps = ComponentProps<typeof DropdownMenuItem> & {
  label?: string;
};

export const PromptInputActionAddAttachments = ({
  label = "Add photos or files",
  ...props
}: PromptInputActionAddAttachmentsProps) => {
  const attachments = usePromptInputAttachments();

  const handleSelect = useCallback(
    (e: Event) => {
      e.preventDefault();
      attachments.openFileDialog();
    },
    [attachments],
  );

  return (
    <DropdownMenuItem {...props} onSelect={handleSelect}>
      <ImageIcon className="mr-2 size-4" /> {label}
    </DropdownMenuItem>
  );
};

export interface PromptInputMessage {
  text: string;
  files: FileUIPart[];
}

export type PromptInputProps = Omit<HTMLAttributes<HTMLFormElement>, "onSubmit" | "onError"> & {
  // e.g., "image/*" or leave undefined for any
  accept?: string;
  multiple?: boolean;
  // When true, accepts drops anywhere on document. Default false (opt-in).
  globalDrop?: boolean;
  // Render a hidden input with given name and keep it in sync for native form posts. Default false.
  syncHiddenInput?: boolean;
  // Minimal constraints
  maxFiles?: number;
  // bytes
  maxFileSize?: number;
  onError?: (err: PromptInputFileError) => void;
  onSubmit: (
    message: PromptInputMessage,
    event: FormEvent<HTMLFormElement>,
  ) => void | Promise<void>;
};

export const PromptInput = ({
  className,
  accept,
  multiple,
  globalDrop,
  syncHiddenInput,
  maxFiles,
  maxFileSize,
  onError,
  onSubmit,
  children,
  ...props
}: PromptInputProps) => {
  // Try to use a provider controller if present
  const controller = usePromptInputController(false);

  const { attachmentsCtx, clearAttachments, files, formRef, handleChange, inputRef } =
    usePromptInputFileHandling({
      accept,
      controller,
      globalDrop,
      maxFileSize,
      maxFiles,
      onError,
      syncHiddenInput,
    });

  const { clearReferencedSources, refsCtx } = usePromptInputReferencedSourcesState();

  const clear = useCallback(() => {
    clearAttachments();
    clearReferencedSources();
  }, [clearAttachments, clearReferencedSources]);

  const handleSubmit = usePromptInputSubmit({
    clear,
    controller,
    files,
    onSubmit,
  });

  // Render with or without local provider
  const inner = (
    <>
      <input
        accept={accept}
        aria-label="Upload files"
        className="hidden"
        multiple={multiple}
        onChange={handleChange}
        ref={inputRef}
        title="Upload files"
        type="file"
      />
      <form className={cn("w-full", className)} onSubmit={handleSubmit} ref={formRef} {...props}>
        <InputGroup className="overflow-hidden">{children}</InputGroup>
      </form>
    </>
  );

  const withReferencedSources = (
    <LocalReferencedSourcesContext.Provider value={refsCtx}>
      {inner}
    </LocalReferencedSourcesContext.Provider>
  );

  // Always provide LocalAttachmentsContext so children get validated add function
  return (
    <PromptInputAttachmentsProvider value={attachmentsCtx}>
      {withReferencedSources}
    </PromptInputAttachmentsProvider>
  );
};

export {
  PromptInputProvider,
  usePromptInputController,
  useProviderAttachments,
} from "./prompt-input-provider";
export type {
  AttachmentsContext,
  PromptInputControllerProps,
  PromptInputProviderProps,
  TextInputContext,
} from "./prompt-input-provider";
export { usePromptInputAttachments } from "./prompt-input-attachments-context";
export { PromptInputTextarea } from "./prompt-input-textarea";
export type { PromptInputTextareaProps } from "./prompt-input-textarea";
export {
  LocalReferencedSourcesContext,
  usePromptInputReferencedSources,
} from "./prompt-input-referenced-sources";
export type { ReferencedSourcesContext } from "./prompt-input-referenced-sources";

export {
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputButton,
  PromptInputCommand,
  PromptInputCommandEmpty,
  PromptInputCommandGroup,
  PromptInputCommandInput,
  PromptInputCommandItem,
  PromptInputCommandList,
  PromptInputCommandSeparator,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputHoverCard,
  PromptInputHoverCardContent,
  PromptInputHoverCardTrigger,
  PromptInputSelect,
  PromptInputSelectContent,
  PromptInputSelectItem,
  PromptInputSelectTrigger,
  PromptInputSelectValue,
  PromptInputSubmit,
  PromptInputTab,
  PromptInputTabBody,
  PromptInputTabItem,
  PromptInputTabLabel,
  PromptInputTabsList,
  PromptInputTools,
} from "./prompt-input-primitives";
export type {
  PromptInputActionMenuContentProps,
  PromptInputActionMenuItemProps,
  PromptInputActionMenuProps,
  PromptInputActionMenuTriggerProps,
  PromptInputBodyProps,
  PromptInputButtonProps,
  PromptInputButtonTooltip,
  PromptInputCommandEmptyProps,
  PromptInputCommandGroupProps,
  PromptInputCommandInputProps,
  PromptInputCommandItemProps,
  PromptInputCommandListProps,
  PromptInputCommandProps,
  PromptInputCommandSeparatorProps,
  PromptInputFooterProps,
  PromptInputHeaderProps,
  PromptInputHoverCardContentProps,
  PromptInputHoverCardProps,
  PromptInputHoverCardTriggerProps,
  PromptInputSelectContentProps,
  PromptInputSelectItemProps,
  PromptInputSelectProps,
  PromptInputSelectTriggerProps,
  PromptInputSelectValueProps,
  PromptInputSubmitProps,
  PromptInputTabBodyProps,
  PromptInputTabItemProps,
  PromptInputTabLabelProps,
  PromptInputTabProps,
  PromptInputTabsListProps,
  PromptInputToolsProps,
} from "./prompt-input-primitives";
