import { useState } from "react";
import { ChevronDown, Gauge, Microscope, RotateCw, SlidersHorizontal, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ProcessingConfigSheetContent } from "@/components/content-item-details/ProcessingConfigSheetContent";
import { useNotify, useTranslate } from "@/lib/app-context";
import {
  buildCustomProcessingConfigPayload,
  buildPresetProcessingConfig,
  DEFAULT_PROCESSING_CONFIG_FORM,
  PROCESSING_CONFIG_PRESET_IDS,
  type ProcessingConfigPayload,
  type ProcessingConfigPresetId,
} from "@/hooks/useContentItemDetails";

const PRESET_ICONS: Record<ProcessingConfigPresetId, LucideIcon> = {
  fast: Zap,
  balanced: Gauge,
  thorough: Microscope,
};

interface ContentListBatchActionBarProps {
  isLoading: boolean;
  selectedCount: number;
  selectedCountLabel: string;
  clearSelectionLabel: string;
  processSelectedLabel: string;
  selectedFilePaths: string[];
  onProcessSelected?: (
    paths: string[],
    processingConfig?: ProcessingConfigPayload,
  ) => void | Promise<void>;
  onClearSelection?: () => void;
}

export function ContentListBatchActionBar({
  isLoading,
  selectedCount,
  selectedCountLabel,
  clearSelectionLabel,
  processSelectedLabel,
  selectedFilePaths,
  onProcessSelected,
  onClearSelection,
}: ContentListBatchActionBarProps) {
  const translate = useTranslate();
  const notify = useNotify();
  const [configOpen, setConfigOpen] = useState(false);
  const [configForm, setConfigForm] = useState(() => ({ ...DEFAULT_PROCESSING_CONFIG_FORM }));
  const selectionVisible = selectedCount > 0;

  if (!selectionVisible) {
    return null;
  }

  const handleProcessSelected = (processingConfig?: ProcessingConfigPayload) => {
    void onProcessSelected?.(selectedFilePaths, processingConfig);
  };

  const handleCustomProcess = () => {
    const result = buildCustomProcessingConfigPayload(configForm);
    if (!result.ok) {
      notify(result.messageKey, { type: "warning" });
      return;
    }

    setConfigOpen(false);
    handleProcessSelected(result.payload);
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
      <div className="mr-1 text-sm text-muted-foreground">{selectedCountLabel}</div>
      {onProcessSelected && (
        <>
          <ButtonGroup>
            <Button
              type="button"
              variant="default"
              size="sm"
              className="gap-2"
              disabled={isLoading}
              onClick={() => handleProcessSelected()}
            >
              <RotateCw className="h-4 w-4" />
              {processSelectedLabel}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="default"
                  size="icon"
                  className="h-8 w-8"
                  disabled={isLoading}
                  aria-label={translate("custom.content.actions.reprocess_options")}
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-72">
                <DropdownMenuLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {translate("custom.content.processing_config.presets.label")}
                </DropdownMenuLabel>
                {PROCESSING_CONFIG_PRESET_IDS.map((preset) => {
                  const Icon = PRESET_ICONS[preset];
                  return (
                    <DropdownMenuItem
                      key={preset}
                      onSelect={() => handleProcessSelected(buildPresetProcessingConfig(preset))}
                      className="gap-3 py-2"
                    >
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="flex min-w-0 flex-col">
                        <span className="text-sm font-medium leading-tight">
                          {translate(`custom.content.processing_config.presets.${preset}`)}
                        </span>
                        <span className="text-xs leading-tight text-muted-foreground">
                          {translate(`custom.content.processing_config.presets.${preset}_hint`)}
                        </span>
                      </div>
                    </DropdownMenuItem>
                  );
                })}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => {
                    setConfigForm({ ...DEFAULT_PROCESSING_CONFIG_FORM });
                    setConfigOpen(true);
                  }}
                >
                  <SlidersHorizontal className="mr-2 h-4 w-4" />
                  {translate("custom.content.actions.customize_processing")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </ButtonGroup>
          <Sheet open={configOpen} onOpenChange={setConfigOpen}>
            <SheetContent
              side="right"
              className="w-[calc(100vw-1rem)] max-w-[450px] gap-0 overflow-hidden p-0 sm:w-[450px] sm:max-w-[450px]"
            >
              <SheetHeader className="sr-only">
                <SheetTitle>{translate("custom.content.processing_config.title")}</SheetTitle>
              </SheetHeader>
              <ProcessingConfigSheetContent
                idPrefix="batch-cfg"
                form={configForm}
                onFormChange={setConfigForm}
                descriptionKey="custom.content.processing_config.selected_description"
                applyLabel={processSelectedLabel}
                onCancel={() => setConfigOpen(false)}
                onApply={handleCustomProcess}
              />
            </SheetContent>
          </Sheet>
        </>
      )}
      {onClearSelection && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={isLoading}
          onClick={onClearSelection}
        >
          {clearSelectionLabel}
        </Button>
      )}
    </div>
  );
}
