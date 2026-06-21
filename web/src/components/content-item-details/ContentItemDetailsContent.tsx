import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslate, useNotify } from "@/lib/app-context";
import { useConfirm } from "@/lib/confirm-context";
import { FileCode, FileText, PanelRightClose, PanelRightOpen } from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { contentApi, type ContentItemInfo, type ExtractedAsset } from "@/dataProvider";
import { reportClientError } from "@/lib/report-client-error";
import { ContentItemHeader } from "./ContentItemHeader";
import { ContentItemPreview } from "./ContentItemPreview";
import { ContentItemStatusBar } from "./ContentItemStatusBar";
import { AssetOverlay } from "./AssetOverlay";
import { BreadcrumbPortal } from "@/components/app/BreadcrumbPortal";
import { InfoPane, type InfoTab } from "./inspector/InfoPane";
import { buildEnrichmentOnlyProcessingConfig } from "@/lib/content-processing";
import { isObjectRecord } from "@/lib/content-enrichment";
import {
  useContentItemDetails,
  type ContentItemProcessHandler,
  buildCustomProcessingConfigPayload,
  parseFormFromLastConfig,
  type ProcessingConfigPayload,
  type ProcessingConfigFormState,
} from "@/hooks/useContentItemDetails";
import { ProcessingConfigSheetContent } from "./ProcessingConfigSheetContent";
import {
  getContentItemDisplayName,
  getPreviewType,
  isDocxFile,
  isExcelFile,
} from "@/lib/content-utils";

const RAIL_COLLAPSED_KEY = "viewer.rail.collapsed";
const RAIL_TAB_KEY = "viewer.rail.tab";

const readStored = (key: string, fallback: boolean): boolean => {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "1") return true;
    if (raw === "0") return false;
  } catch {
    // ignore
  }
  return fallback;
};

const writeStored = (key: string, value: boolean) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // ignore
  }
};

const readStoredRailTab = (): InfoTab | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(RAIL_TAB_KEY);
    if (raw === "chat" || raw === "data" || raw === "info" || raw === "media") return raw;
  } catch {
    // ignore
  }
  return null;
};

const computeNeedsAttention = (file: ContentItemInfo): boolean => {
  if (file.document_classification?.needs_review === true) return true;
  if (
    file.document_extraction &&
    isObjectRecord(file.document_extraction.summary) &&
    file.document_extraction.summary.needs_review === true
  ) {
    return true;
  }
  if (file.document_enrichment?.classification_lifecycle?.stale === true) return true;
  if (file.document_enrichment?.extraction_lifecycle?.stale === true) return true;
  return false;
};

const computeDefaultRailTab = (file: ContentItemInfo): InfoTab => {
  if (file.kind === "folder") return "info";
  const hasData =
    Boolean(file.capabilities?.supports_review) ||
    Boolean(file.document_classification) ||
    Boolean(file.document_extraction);
  if (hasData && computeNeedsAttention(file)) return "data";
  return "chat";
};

export interface ContentItemDetailsContentProps {
  initialFile: ContentItemInfo;
  open: boolean;
  onProcess?: ContentItemProcessHandler;
  onDelete?: (path: string) => void;
  onOpenActivity?: () => void;
  onOpenAsPage?: () => void;
  onOpenRelatedItem?: (path: string) => void | Promise<void>;
  initialHighlightRefs?: string[];
  hideIdentity?: boolean;
}

export const ContentItemDetailsContent = ({
  initialFile,
  open,
  onProcess,
  onDelete,
  onOpenActivity,
  onOpenAsPage,
  onOpenRelatedItem,
  initialHighlightRefs,
  hideIdentity = false,
}: ContentItemDetailsContentProps) => {
  const translate = useTranslate();
  const notify = useNotify();
  const confirm = useConfirm();

  const {
    file,
    extractedData,
    extractedLoading,
    isProcessing,
    loadFile,
    savingEnrichment,
    setReprocessingTriggered,
    handleAbort,
    verifyClass,
    submitReview,
  } = useContentItemDetails(initialFile, open);

  const [previewError, setPreviewError] = useState(false);
  const [highlightRefs, setHighlightRefs] = useState<string | undefined>(
    initialHighlightRefs && initialHighlightRefs.length > 0
      ? initialHighlightRefs.join(", ")
      : undefined,
  );
  const [selectedAsset, setSelectedAsset] = useState<ExtractedAsset | null>(null);
  const [activePreviewOverride, setActivePreviewOverride] = useState<{
    path: string;
    value: "parsed" | "original";
  } | null>(null);
  const [pdfToolbarTarget, setPdfToolbarTarget] = useState<HTMLDivElement | null>(null);
  const [configPopoverOpen, setConfigPopoverOpen] = useState(false);
  const [docDataCache, setDocDataCache] = useState<{
    version: string;
    data: unknown;
  } | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(() => readStored(RAIL_COLLAPSED_KEY, false));
  const [railTab, setRailTabRaw] = useState<InfoTab>(() => {
    const stored = readStoredRailTab();
    return stored ?? computeDefaultRailTab(initialFile);
  });
  const railPanelRef = useRef<PanelImperativeHandle | null>(null);
  const [configForm, setConfigForm] = useState<ProcessingConfigFormState>(() =>
    parseFormFromLastConfig(initialFile.last_processing_config),
  );

  const currentExtension = file?.extension ?? initialFile.extension;
  const currentPreviewType = getPreviewType(currentExtension);
  const doclingAvailable = extractedData?.has_docling_document ?? null;
  const isExcel = isExcelFile(currentExtension);
  const isDocx = isDocxFile(currentExtension);
  const supportsChunking = file?.capabilities?.supports_chunking ?? false;
  const supportsEnrichment = file?.capabilities?.supports_enrichment ?? false;
  const supportsProcessing = supportsChunking || supportsEnrichment;
  const showMediaTab = file?.kind !== "folder";
  const extractionSummary =
    file?.document_extraction && isObjectRecord(file.document_extraction.summary)
      ? file.document_extraction.summary
      : null;
  const extractionNeedsReview = extractionSummary?.needs_review === true;
  const hasAttention =
    Boolean(file?.processing_error) ||
    file?.document_classification?.needs_review === true ||
    extractionNeedsReview ||
    file?.document_enrichment?.classification_lifecycle?.stale === true ||
    file?.document_enrichment?.extraction_lifecycle?.stale === true;
  const dataNeedsAttention = file ? computeNeedsAttention(file) : false;
  const previewContentVersion = file ? `${file.path}:${file.processed_at ?? ""}` : "";
  const docData = docDataCache?.version === previewContentVersion ? docDataCache.data : null;

  const docLoading = Boolean(
    open &&
    file &&
    showMediaTab &&
    extractedData?.has_docling_document &&
    !docData &&
    !isExcel &&
    !isDocx,
  );

  useEffect(() => {
    if (!docLoading || !file) {
      return;
    }

    let cancelled = false;

    contentApi
      .getExtractedDocument(file.path)
      .then((data) => {
        if (!cancelled) {
          setDocDataCache({ version: previewContentVersion, data });
        }
      })
      .catch((err) => reportClientError(err, undefined, { routeName: "content-item:doc-data" }));

    return () => {
      cancelled = true;
    };
  }, [docLoading, file, previewContentVersion]);

  useEffect(() => {
    writeStored(RAIL_COLLAPSED_KEY, railCollapsed);
  }, [railCollapsed]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(RAIL_TAB_KEY, railTab);
    } catch {
      // ignore
    }
  }, [railTab]);

  const collapseRail = () => {
    setRailCollapsed(true);
    railPanelRef.current?.collapse();
  };
  const expandRail = () => {
    setRailCollapsed(false);
    railPanelRef.current?.expand();
  };
  const toggleRail = () => (railCollapsed ? expandRail() : collapseRail());

  const setRailTab = (tab: InfoTab) => {
    setRailTabRaw(tab);
  };

  const bindPdfToolbarTarget = useCallback((node: HTMLDivElement | null) => {
    setPdfToolbarTarget(node);
  }, []);

  if (!file) return null;

  const previewUrl = contentApi.getPreviewUrl(file.path);
  const downloadUrl = contentApi.getDownloadUrl(file.path);
  const shareUrl =
    typeof window === "undefined"
      ? `/content/item/${encodeURIComponent(file.id)}`
      : `${window.location.origin}/content/item/${encodeURIComponent(file.id)}`;
  const activePreview =
    activePreviewOverride?.path === file.path
      ? activePreviewOverride.value
      : currentPreviewType === "audio" && doclingAvailable
        ? "parsed"
        : "original";
  const setActivePreview = (value: "parsed" | "original") => {
    setActivePreviewOverride({ path: file.path, value });
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      notify(translate("custom.content.actions.link_copied", { defaultValue: "Link copied" }), {
        type: "info",
      });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "content-item:copy-link" });
    }
  };

  const handleProcess = async (path: string, processingConfig?: ProcessingConfigPayload) => {
    if (!onProcess) return false;
    setReprocessingTriggered(true);
    try {
      const started = await onProcess(path, processingConfig);
      if (started === false) {
        setReprocessingTriggered(false);
        return false;
      }
      return true;
    } catch {
      setReprocessingTriggered(false);
      return false;
    }
  };

  const handleCustomProcess = async () => {
    const result = buildCustomProcessingConfigPayload(configForm);
    if (!result.ok) {
      notify(result.messageKey, { type: "warning" });
      return;
    }

    setConfigPopoverOpen(false);
    await handleProcess(file.path, result.payload);
  };

  const handleEnrichmentOnlyProcess = async () => {
    await handleProcess(file.path, buildEnrichmentOnlyProcessingConfig());
  };

  const onAbortWrapper = async () => {
    if (
      await confirm({
        description: translate("custom.content.actions.confirm_abort"),
        destructive: true,
      })
    ) {
      await handleAbort();
    }
  };

  const handlePopoverOpenChange = (isOpen: boolean) => {
    if (isOpen && file) {
      setConfigForm(parseFormFromLastConfig(file.last_processing_config));
    }
    setConfigPopoverOpen(isOpen);
  };

  const navigateToEvidence = (docRefs: string[]) => {
    if (docRefs.length === 0) return;
    setHighlightRefs(docRefs.join(", "));
    setActivePreview("parsed");
  };

  const handleOpenRelatedItem = async (path: string) => {
    setPreviewError(false);
    setDocDataCache(null);
    setSelectedAsset(null);
    setHighlightRefs(undefined);
    setActivePreviewOverride(null);
    if (onOpenRelatedItem) {
      await onOpenRelatedItem(path);
      return;
    }
    await loadFile(path);
  };

  const configPopoverContent = (
    <ProcessingConfigSheetContent
      idPrefix="cfg"
      form={configForm}
      onFormChange={setConfigForm}
      onCancel={() => setConfigPopoverOpen(false)}
      onApply={() => void handleCustomProcess()}
    />
  );

  const previewType = currentPreviewType;
  const showPdfToolbar = activePreview === "original" && previewType === "pdf";

  const canTogglePreviewMode =
    Boolean(doclingAvailable) &&
    !isExcel &&
    !isDocx &&
    (previewType === "pdf" ||
      previewType === "document" ||
      previewType === "image" ||
      previewType === "audio");
  const nextPreviewMode = activePreview === "original" ? "parsed" : "original";

  const previewModeToggle = canTogglePreviewMode ? (
    <Button
      type="button"
      variant={activePreview === "parsed" ? "secondary" : "outline"}
      size="icon"
      className="h-8 w-8 shrink-0"
      onClick={() => setActivePreview(nextPreviewMode)}
      aria-label={translate(
        nextPreviewMode === "parsed"
          ? "custom.content.preview.show_parsed"
          : "custom.content.preview.show_original",
        {
          defaultValue:
            nextPreviewMode === "parsed" ? "Show parsed preview" : "Show original preview",
        },
      )}
      title={translate(
        nextPreviewMode === "parsed"
          ? "custom.content.preview.show_parsed"
          : "custom.content.preview.show_original",
        {
          defaultValue:
            nextPreviewMode === "parsed" ? "Show parsed preview" : "Show original preview",
        },
      )}
    >
      {activePreview === "parsed" ? (
        <FileCode className="h-3.5 w-3.5" />
      ) : (
        <FileText className="h-3.5 w-3.5" />
      )}
    </Button>
  ) : null;

  const railToggleButton = (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-8 w-8 shrink-0"
      onClick={toggleRail}
      aria-label={translate("custom.content.details.toggle_info_pane", {
        defaultValue: "Toggle details panel",
      })}
      title={translate("custom.content.details.toggle_info_pane", {
        defaultValue: "Toggle details panel",
      })}
    >
      {railCollapsed ? (
        <PanelRightOpen className="h-3.5 w-3.5" />
      ) : (
        <PanelRightClose className="h-3.5 w-3.5" />
      )}
    </Button>
  );

  const previewBlock = (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-background px-2 py-1">
        {previewModeToggle}
        {showPdfToolbar ? (
          <div
            ref={bindPdfToolbarTarget}
            className="flex min-w-[18rem] flex-1 items-center overflow-x-auto"
          />
        ) : (
          <div className="min-w-0 flex-1" />
        )}
        {railToggleButton}
      </div>
      <main className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <ContentItemPreview
          file={file}
          doclingAvailable={doclingAvailable}
          activePreview={activePreview}
          previewError={previewError}
          previewUrl={previewUrl}
          highlightRefs={highlightRefs}
          docData={docData}
          pdfToolbarTarget={pdfToolbarTarget}
          useExternalPdfToolbar={showPdfToolbar}
          pdfPagesInitiallyOpen={false}
          pdfPagesOpenStorageKey="viewer.pdf-pages-open"
          onPreviewError={setPreviewError}
        />
      </main>
    </div>
  );

  const railBlock = (
    <InfoPane
      file={file}
      activeTab={railTab}
      onTabChange={setRailTab}
      savingEnrichment={savingEnrichment}
      onSubmitReview={submitReview}
      onVerifyClass={verifyClass}
      onNavigateToEvidence={(docRefs) => navigateToEvidence(docRefs)}
      onOpenRelatedItem={handleOpenRelatedItem}
      extractedData={extractedData}
      extractedLoading={extractedLoading}
      onSelectAsset={setSelectedAsset}
      dataNeedsAttention={dataNeedsAttention}
      onRerunEnrichment={
        onProcess && supportsEnrichment && !isProcessing
          ? () => void handleEnrichmentOnlyProcess()
          : undefined
      }
    />
  );

  const actionToolbar = (
    <ContentItemHeader
      file={file}
      isProcessing={isProcessing}
      downloadUrl={downloadUrl}
      openOriginalUrl={previewUrl}
      onCopyLink={handleCopyLink}
      onProcess={onProcess && supportsProcessing ? handleProcess : undefined}
      onAbort={onAbortWrapper}
      onDelete={onDelete ? () => onDelete(file.path) : undefined}
      onRerunEnrichment={
        onProcess && supportsEnrichment ? () => void handleEnrichmentOnlyProcess() : undefined
      }
      onOpenActivity={onOpenActivity}
      onOpenAsPage={onOpenAsPage}
      configPopoverOpen={configPopoverOpen}
      onConfigPopoverOpenChange={handlePopoverOpenChange}
      configPopoverContent={onProcess && supportsProcessing ? configPopoverContent : undefined}
    />
  );

  const headerStrip = hideIdentity ? (
    <BreadcrumbPortal>
      <div className="order-2 flex shrink-0 items-center pl-3">{actionToolbar}</div>
    </BreadcrumbPortal>
  ) : (
    <div className="flex shrink-0 items-center gap-3 border-b bg-background px-3 py-2">
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-sm font-semibold leading-tight">
          {getContentItemDisplayName(file)}
        </h2>
        <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">{file.path}</p>
      </div>
      <div className="min-w-0 shrink-0 overflow-x-auto">
        <div className="flex min-w-max justify-end">{actionToolbar}</div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full w-full min-h-0 flex-col overflow-hidden bg-muted/10">
      {headerStrip}
      <ResizablePanelGroup direction="horizontal" className="min-h-0 flex-1 overflow-hidden">
        <ResizablePanel
          id="viewer-preview-pane"
          defaultSize="68%"
          minSize="35%"
          className="min-w-0"
        >
          {previewBlock}
        </ResizablePanel>
        <ResizableHandle withHandle className={railCollapsed ? "pointer-events-none" : undefined} />
        <ResizablePanel
          id="viewer-rail-pane"
          panelRef={railPanelRef}
          defaultSize="32%"
          minSize="22%"
          maxSize="50%"
          collapsible
          collapsedSize="0%"
          onResize={(size) => setRailCollapsed(size.asPercentage <= 1)}
          className="min-w-0"
        >
          {railBlock}
        </ResizablePanel>
      </ResizablePanelGroup>
      <AssetOverlay asset={selectedAsset} onClose={() => setSelectedAsset(null)} />
      <ContentItemStatusBar file={file} isProcessing={isProcessing} hasAttention={hasAttention} />
    </div>
  );
};
