import { useTranslate } from "@/lib/app-context";
import {
  ChevronDown,
  Download,
  ExternalLink,
  Gauge,
  History,
  Maximize2,
  Microscope,
  MoreHorizontal,
  RefreshCw,
  Share2,
  SlidersHorizontal,
  Trash2,
  WandSparkles,
  XCircle,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { type ContentItemInfo } from "@/dataProvider";
import {
  buildPresetProcessingConfig,
  PROCESSING_CONFIG_PRESET_IDS,
  type ContentItemProcessHandler,
  type ProcessingConfigPresetId,
} from "@/hooks/useContentItemDetails";

const PRESET_ICONS: Record<ProcessingConfigPresetId, LucideIcon> = {
  fast: Zap,
  balanced: Gauge,
  thorough: Microscope,
};

interface ContentItemHeaderProps {
  file: ContentItemInfo;
  isProcessing: boolean;
  downloadUrl: string;
  openOriginalUrl?: string;
  onCopyLink: () => void;
  onProcess?: ContentItemProcessHandler;
  onAbort?: () => void;
  onDelete?: () => void;
  onRerunEnrichment?: () => void;
  onOpenActivity?: () => void;
  onOpenAsPage?: () => void;
  configPopoverOpen?: boolean;
  onConfigPopoverOpenChange?: (open: boolean) => void;
  configPopoverContent?: React.ReactNode;
}

export const ContentItemHeader = ({
  file,
  isProcessing,
  downloadUrl,
  openOriginalUrl,
  onCopyLink,
  onProcess,
  onAbort,
  onDelete,
  onRerunEnrichment,
  onOpenActivity,
  onOpenAsPage,
  configPopoverOpen,
  onConfigPopoverOpenChange,
  configPopoverContent,
}: ContentItemHeaderProps) => {
  const translate = useTranslate();

  const hasPresetItems = Boolean(onProcess);
  const hasReprocessMenu = Boolean(configPopoverContent || onRerunEnrichment || hasPresetItems);
  const hasOverflowItems = Boolean(onOpenAsPage || onOpenActivity || onDelete);

  return (
    <div className="flex shrink-0 items-center gap-2">
      <ButtonGroup>
        {isProcessing ? (
          <Button
            variant="outline"
            size="sm"
            className="h-8 font-normal text-destructive hover:text-destructive"
            onClick={onAbort}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5" />
            {translate("custom.content.actions.abort")}
          </Button>
        ) : (
          <>
            <Button
              variant="outline"
              size="sm"
              className="h-8 font-normal"
              onClick={() => void onProcess?.(file.path)}
              disabled={!onProcess}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              {translate("custom.content.actions.reprocess")}
            </Button>
            {hasReprocessMenu ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    aria-label={translate("custom.content.actions.reprocess_options")}
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-72">
                  {hasPresetItems ? (
                    <>
                      <DropdownMenuLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        {translate("custom.content.processing_config.presets.label")}
                      </DropdownMenuLabel>
                      {PROCESSING_CONFIG_PRESET_IDS.map((preset) => {
                        const Icon = PRESET_ICONS[preset];
                        return (
                          <DropdownMenuItem
                            key={preset}
                            onSelect={() =>
                              void onProcess?.(file.path, buildPresetProcessingConfig(preset))
                            }
                            className="gap-3 py-2"
                          >
                            <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                            <div className="flex min-w-0 flex-col">
                              <span className="text-sm font-medium leading-tight">
                                {translate(`custom.content.processing_config.presets.${preset}`)}
                              </span>
                              <span className="text-xs text-muted-foreground leading-tight">
                                {translate(
                                  `custom.content.processing_config.presets.${preset}_hint`,
                                )}
                              </span>
                            </div>
                          </DropdownMenuItem>
                        );
                      })}
                    </>
                  ) : null}
                  {hasPresetItems && (configPopoverContent || onRerunEnrichment) ? (
                    <DropdownMenuSeparator />
                  ) : null}
                  {configPopoverContent ? (
                    <DropdownMenuItem
                      onSelect={() => {
                        onConfigPopoverOpenChange?.(true);
                      }}
                    >
                      <SlidersHorizontal className="mr-2 h-4 w-4" />
                      {translate("custom.content.actions.customize_processing")}
                    </DropdownMenuItem>
                  ) : null}
                  {onRerunEnrichment ? (
                    <DropdownMenuItem onSelect={() => onRerunEnrichment()}>
                      <WandSparkles className="mr-2 h-4 w-4" />
                      {translate("custom.content.actions.rerun_enrichment")}
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            {configPopoverContent ? (
              <Sheet open={configPopoverOpen} onOpenChange={onConfigPopoverOpenChange}>
                <SheetContent
                  side="right"
                  className="w-[calc(100vw-1rem)] max-w-[450px] gap-0 overflow-hidden p-0 sm:w-[450px] sm:max-w-[450px]"
                >
                  <SheetHeader className="sr-only">
                    <SheetTitle>{translate("custom.content.processing_config.title")}</SheetTitle>
                  </SheetHeader>
                  {configPopoverContent}
                </SheetContent>
              </Sheet>
            ) : null}
          </>
        )}
      </ButtonGroup>

      <ButtonGroup>
        <Button
          variant="outline"
          size="sm"
          className="h-8 font-normal"
          onClick={() => window.open(downloadUrl, "_blank", "noopener,noreferrer")}
        >
          <Download className="mr-1.5 h-3.5 w-3.5" />
          {translate("custom.content.actions.download")}
        </Button>
        {openOriginalUrl ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                aria-label={translate("custom.content.actions.download_options", {
                  defaultValue: "More download options",
                })}
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem
                onSelect={() => window.open(openOriginalUrl, "_blank", "noopener,noreferrer")}
              >
                <ExternalLink className="mr-2 h-4 w-4" />
                {translate("custom.content.actions.open_original")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </ButtonGroup>

      {hasOverflowItems ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              aria-label={translate("custom.content.actions.more_actions", {
                defaultValue: "More actions",
              })}
              title={translate("custom.content.actions.more_actions", {
                defaultValue: "More actions",
              })}
            >
              <MoreHorizontal className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem onSelect={() => void onCopyLink()}>
              <Share2 className="mr-2 h-4 w-4" />
              {translate("custom.content.actions.copy_link")}
            </DropdownMenuItem>
            {onOpenAsPage ? (
              <DropdownMenuItem onSelect={onOpenAsPage}>
                <Maximize2 className="mr-2 h-4 w-4" />
                {translate("custom.content.actions.open_as_page", {
                  defaultValue: "Open as page",
                })}
              </DropdownMenuItem>
            ) : null}
            {onOpenActivity ? (
              <DropdownMenuItem onSelect={onOpenActivity}>
                <History className="mr-2 h-4 w-4" />
                {translate("custom.content.audit.title")}
              </DropdownMenuItem>
            ) : null}
            {onDelete ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={onDelete}
                  className={cn(
                    "text-destructive focus:bg-destructive/10 focus:text-destructive",
                    "data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive",
                  )}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {translate("custom.content.delete.button")}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
};
