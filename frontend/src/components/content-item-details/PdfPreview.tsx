import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import {
  EventBus,
  FindState,
  PDFFindController,
  PDFLinkService,
  PDFViewer,
} from "pdfjs-dist/web/pdf_viewer.mjs";
import "pdfjs-dist/web/pdf_viewer.css";
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  Files,
  RotateCwSquare,
  Scan,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useTranslate } from "@/lib/app-context";
import { cn } from "@/lib/utils";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface PdfPreviewProps {
  url: string;
  toolbarPortalTarget?: HTMLElement | null;
  useExternalToolbar?: boolean;
  pagesInitiallyOpen?: boolean;
  pagesOpenStorageKey?: string;
  onError: (error: boolean) => void;
}

type PdfGestureEvent = Event & {
  clientX?: number;
  clientY?: number;
  scale?: number;
};

type PdfFindMatchesCount = {
  current?: number;
  total?: number;
};

type PdfFindEvent = {
  state?: number;
  matchesCount?: PdfFindMatchesCount;
};

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const DEFAULT_ZOOM = 1;
const ZOOM_STEP = 0.25;
const PINCH_ZOOM_SENSITIVITY = 0.0025;
const ZOOM_DRAWING_DELAY = 200;

const clampZoom = (value: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));

const isInteractiveTarget = (target: EventTarget | null) =>
  target instanceof Element &&
  Boolean(
    target.closest('button, a, input, textarea, select, [role="button"], [contenteditable="true"]'),
  );

export const PdfPreview = ({
  url,
  toolbarPortalTarget,
  useExternalToolbar = false,
  pagesInitiallyOpen = true,
  pagesOpenStorageKey,
  onError,
}: PdfPreviewProps) => {
  const translate = useTranslate();
  const viewportRef = useRef<HTMLDivElement>(null);
  const viewerContainerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const pdfDocumentRef = useRef<PDFDocumentProxy | null>(null);
  const eventBusRef = useRef<EventBus | null>(null);
  const pdfViewerRef = useRef<PDFViewer | null>(null);
  const pdfLinkServiceRef = useRef<PDFLinkService | null>(null);
  const findSourceRef = useRef({});
  const zoomRef = useRef(1);
  const gestureStartZoomRef = useRef<number | null>(null);
  const panStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    scrollLeft: number;
    scrollTop: number;
  } | null>(null);
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [activePage, setActivePage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [overviewOpen, setOverviewOpenState] = useState<boolean>(() => {
    if (pagesOpenStorageKey && typeof window !== "undefined") {
      try {
        const stored = window.localStorage.getItem(pagesOpenStorageKey);
        if (stored === "true") return true;
        if (stored === "false") return false;
      } catch {
        // ignore storage errors (private mode, etc.)
      }
    }
    return pagesInitiallyOpen;
  });
  const setOverviewOpen = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      setOverviewOpenState((prev) => {
        const resolved = typeof next === "function" ? next(prev) : next;
        if (pagesOpenStorageKey && typeof window !== "undefined") {
          try {
            window.localStorage.setItem(pagesOpenStorageKey, String(resolved));
          } catch {
            // ignore storage errors
          }
        }
        return resolved;
      });
    },
    [pagesOpenStorageKey],
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchState, setSearchState] = useState<number | null>(null);
  const [searchMatches, setSearchMatches] = useState<PdfFindMatchesCount>({
    current: 0,
    total: 0,
  });

  const pageNumbers = useMemo(
    () => Array.from({ length: numPages }, (_, index) => index + 1),
    [numPages],
  );
  const normalizedSearchQuery = searchQuery.trim();

  const goToPage = useCallback(
    (pageNumber: number) => {
      const nextPage = Math.min(Math.max(pageNumber, 1), Math.max(numPages, 1));
      pdfViewerRef.current?.scrollPageIntoView({ pageNumber: nextPage });
      setActivePage(nextPage);
    },
    [numPages],
  );

  const syncZoom = useCallback((nextZoom: number) => {
    const clampedZoom = clampZoom(nextZoom);
    zoomRef.current = clampedZoom;
    setZoom(clampedZoom);
  }, []);

  const getViewerZoomOrigin = useCallback((point: { x: number; y: number }) => {
    const container = viewerContainerRef.current;
    if (!container) return undefined;

    const rect = container.getBoundingClientRect();
    return {
      x: container.offsetLeft + point.x - rect.left,
      y: container.offsetTop + point.y - rect.top,
    };
  }, []);

  const applyViewerZoom = useCallback(
    (nextZoomValue: number, focalPoint?: { x: number; y: number }) => {
      const pdfViewer = pdfViewerRef.current;
      if (!pdfViewer) return false;

      const currentZoom = pdfViewer.currentScale || zoomRef.current || 1;
      const nextZoom = clampZoom(nextZoomValue);
      if (Math.abs(nextZoom - currentZoom) < 0.001) {
        syncZoom(nextZoom);
        return false;
      }

      syncZoom(nextZoom);
      const origin = focalPoint ? getViewerZoomOrigin(focalPoint) : undefined;
      pdfViewer.updateScale({
        drawingDelay: ZOOM_DRAWING_DELAY,
        origin: origin ? [origin.x, origin.y] : undefined,
        scaleFactor: nextZoom / currentZoom,
      });
      return true;
    },
    [getViewerZoomOrigin, syncZoom],
  );

  const rotateClockwise = useCallback(() => {
    const nextRotation = (rotation + 90) % 360;
    const pdfViewer = pdfViewerRef.current;
    if (pdfViewer) {
      pdfViewer.pagesRotation = nextRotation;
    }
    setRotation(nextRotation);
  }, [rotation]);

  const dispatchFind = useCallback(
    (query: string, options: { again?: boolean; findPrevious?: boolean } = {}) => {
      const eventBus = eventBusRef.current;
      if (!eventBus) return;

      eventBus.dispatch("find", {
        source: findSourceRef.current,
        type: options.again ? "again" : "",
        query,
        phraseSearch: true,
        caseSensitive: false,
        entireWord: false,
        highlightAll: true,
        findPrevious: Boolean(options.findPrevious),
        matchDiacritics: false,
      });
    },
    [],
  );

  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  useEffect(() => {
    const container = viewerContainerRef.current;
    const viewerElement = viewerRef.current;
    if (!container || !viewerElement) return;

    let cancelled = false;
    viewerElement.replaceChildren();

    const eventBus = new EventBus();
    const pdfLinkService = new PDFLinkService({ eventBus });
    const pdfFindController = new PDFFindController({
      eventBus,
      linkService: pdfLinkService,
      updateMatchesCountOnProgress: true,
    });
    const pdfViewer = new PDFViewer({
      container,
      viewer: viewerElement,
      eventBus,
      linkService: pdfLinkService,
      findController: pdfFindController,
      removePageBorders: true,
      maxCanvasPixels: 4096 * 8192,
      enableDetailCanvas: true,
      enableHWA: true,
    });

    pdfLinkService.setViewer(pdfViewer);
    eventBusRef.current = eventBus;
    pdfViewerRef.current = pdfViewer;
    pdfLinkServiceRef.current = pdfLinkService;

    const handlePagesInit = () => {
      pdfViewer.currentScaleValue = String(DEFAULT_ZOOM);
      syncZoom(pdfViewer.currentScale || DEFAULT_ZOOM);
      setLoading(false);
    };
    const handlePageChanging = (event: { pageNumber?: number }) => {
      if (typeof event.pageNumber === "number") {
        setActivePage(event.pageNumber);
      }
    };
    const handleScaleChanging = (event: { scale?: number }) => {
      if (typeof event.scale === "number") {
        syncZoom(event.scale);
      }
    };
    const handleFindMatchesCount = (event: PdfFindEvent) => {
      setSearchMatches(event.matchesCount ?? { current: 0, total: 0 });
      setSearchLoading(false);
    };
    const handleFindControlState = (event: PdfFindEvent) => {
      if (typeof event.state === "number") {
        setSearchState(event.state);
        setSearchLoading(event.state === FindState.PENDING);
      }
      if (event.matchesCount) {
        setSearchMatches(event.matchesCount);
      }
    };

    eventBus.on("pagesinit", handlePagesInit);
    eventBus.on("pagechanging", handlePageChanging);
    eventBus.on("scalechanging", handleScaleChanging);
    eventBus.on("updatefindmatchescount", handleFindMatchesCount);
    eventBus.on("updatefindcontrolstate", handleFindControlState);

    const loadingTask = pdfjsLib.getDocument({
      url,
      withCredentials: true,
      cMapPacked: true,
      cMapUrl: "/pdfjs/cmaps/",
      standardFontDataUrl: "/pdfjs/standard_fonts/",
      wasmUrl: "/pdfjs/wasm/",
    });

    void loadingTask.promise
      .then(async (loadedDocument) => {
        if (cancelled) {
          await loadedDocument.destroy();
          return;
        }

        pdfDocumentRef.current = loadedDocument;
        setPdfDocument(loadedDocument);
        setNumPages(loadedDocument.numPages);
        setRotation(0);
        pdfLinkService.setDocument(loadedDocument, null);
        pdfFindController.setDocument(loadedDocument);
        pdfViewer.setDocument(loadedDocument);
        onError(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(true);
        setLoading(false);
        onError(true);
      });

    return () => {
      cancelled = true;
      eventBus.off("pagesinit", handlePagesInit);
      eventBus.off("pagechanging", handlePageChanging);
      eventBus.off("scalechanging", handleScaleChanging);
      eventBus.off("updatefindmatchescount", handleFindMatchesCount);
      eventBus.off("updatefindcontrolstate", handleFindControlState);
      void loadingTask.destroy();
      pdfViewer.cleanup();
      viewerElement.replaceChildren();
      if (pdfDocumentRef.current) {
        void pdfDocumentRef.current.destroy();
      }
      pdfDocumentRef.current = null;
      eventBusRef.current = null;
      pdfViewerRef.current = null;
      pdfLinkServiceRef.current = null;
    };
  }, [onError, syncZoom, url]);

  useEffect(() => {
    if (!eventBusRef.current) return;

    if (!normalizedSearchQuery) {
      dispatchFind("");
      return;
    }

    const timeout = window.setTimeout(() => {
      dispatchFind(normalizedSearchQuery);
    }, 150);

    return () => window.clearTimeout(timeout);
  }, [dispatchFind, normalizedSearchQuery]);

  const isEventInsideViewer = useCallback((event: Event) => {
    const viewport = viewportRef.current;
    if (!viewport) return false;

    if (event.target instanceof Node && viewport.contains(event.target)) {
      return true;
    }

    const pointerEvent = event as PdfGestureEvent;
    if (typeof pointerEvent.clientX !== "number" || typeof pointerEvent.clientY !== "number") {
      return false;
    }

    const rect = viewport.getBoundingClientRect();
    return (
      pointerEvent.clientX >= rect.left &&
      pointerEvent.clientX <= rect.right &&
      pointerEvent.clientY >= rect.top &&
      pointerEvent.clientY <= rect.bottom
    );
  }, []);

  useEffect(() => {
    const handleNativeWheel = (event: WheelEvent) => {
      if (!event.ctrlKey || event.deltaY === 0 || !isEventInsideViewer(event)) return;

      event.preventDefault();
      event.stopPropagation();

      const gestureZoomRatio = Math.exp(-event.deltaY * PINCH_ZOOM_SENSITIVITY);
      applyViewerZoom(zoomRef.current * gestureZoomRatio, {
        x: event.clientX,
        y: event.clientY,
      });
    };

    const handleGestureStart = (event: Event) => {
      if (!isEventInsideViewer(event)) return;

      event.preventDefault();
      event.stopPropagation();
      gestureStartZoomRef.current = zoomRef.current;
    };

    const handleGestureChange = (event: Event) => {
      if (!isEventInsideViewer(event)) return;

      event.preventDefault();
      event.stopPropagation();

      const gestureEvent = event as PdfGestureEvent;
      const scale = typeof gestureEvent.scale === "number" ? gestureEvent.scale : 1;
      const startZoom = gestureStartZoomRef.current ?? zoomRef.current;
      applyViewerZoom(startZoom * scale, {
        x: gestureEvent.clientX ?? window.innerWidth / 2,
        y: gestureEvent.clientY ?? window.innerHeight / 2,
      });
    };

    const handleGestureEnd = (event: Event) => {
      if (!isEventInsideViewer(event)) return;

      event.preventDefault();
      event.stopPropagation();
      gestureStartZoomRef.current = null;
    };

    window.addEventListener("wheel", handleNativeWheel, { passive: false, capture: true });
    window.addEventListener("gesturestart", handleGestureStart, {
      passive: false,
      capture: true,
    });
    window.addEventListener("gesturechange", handleGestureChange, {
      passive: false,
      capture: true,
    });
    window.addEventListener("gestureend", handleGestureEnd, {
      passive: false,
      capture: true,
    });

    return () => {
      window.removeEventListener("wheel", handleNativeWheel, { capture: true });
      window.removeEventListener("gesturestart", handleGestureStart, { capture: true });
      window.removeEventListener("gesturechange", handleGestureChange, { capture: true });
      window.removeEventListener("gestureend", handleGestureEnd, { capture: true });
    };
  }, [applyViewerZoom, isEventInsideViewer]);

  useEffect(() => {
    const scrollContainer = viewerContainerRef.current;
    if (!scrollContainer) return;

    const endPan = (event: PointerEvent) => {
      const panState = panStateRef.current;
      if (!panState || panState.pointerId !== event.pointerId) return;

      panStateRef.current = null;
      setIsPanning(false);
      if (scrollContainer.hasPointerCapture(event.pointerId)) {
        scrollContainer.releasePointerCapture(event.pointerId);
      }
    };

    const handlePointerDown = (event: PointerEvent) => {
      if (zoomRef.current <= 1 || event.button !== 0 || isInteractiveTarget(event.target)) return;

      const canPanHorizontally = scrollContainer.scrollWidth > scrollContainer.clientWidth;
      const canPanVertically = scrollContainer.scrollHeight > scrollContainer.clientHeight;
      if (!canPanHorizontally && !canPanVertically) return;

      panStateRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        scrollLeft: scrollContainer.scrollLeft,
        scrollTop: scrollContainer.scrollTop,
      };
      setIsPanning(true);
      scrollContainer.setPointerCapture(event.pointerId);
      event.preventDefault();
    };

    const handlePointerMove = (event: PointerEvent) => {
      const panState = panStateRef.current;
      if (!panState || panState.pointerId !== event.pointerId) return;

      scrollContainer.scrollLeft = panState.scrollLeft - (event.clientX - panState.startX);
      scrollContainer.scrollTop = panState.scrollTop - (event.clientY - panState.startY);
      event.preventDefault();
    };

    scrollContainer.addEventListener("pointerdown", handlePointerDown);
    scrollContainer.addEventListener("pointermove", handlePointerMove);
    scrollContainer.addEventListener("pointerup", endPan);
    scrollContainer.addEventListener("pointercancel", endPan);

    return () => {
      scrollContainer.removeEventListener("pointerdown", handlePointerDown);
      scrollContainer.removeEventListener("pointermove", handlePointerMove);
      scrollContainer.removeEventListener("pointerup", endPan);
      scrollContainer.removeEventListener("pointercancel", endPan);
      if (panStateRef.current) {
        panStateRef.current = null;
        setIsPanning(false);
      }
    };
  }, [loading]);

  const moveSearchResult = (findPrevious: boolean) => {
    if (!normalizedSearchQuery || !searchMatches.total) return;
    setSearchLoading(true);
    dispatchFind(normalizedSearchQuery, { again: true, findPrevious });
  };

  const updateSearchQuery = (value: string) => {
    setSearchQuery(value);
    if (value.trim()) {
      setSearchLoading(true);
    } else {
      setSearchLoading(false);
      setSearchState(null);
      setSearchMatches({ current: 0, total: 0 });
    }
  };

  if (loadError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center text-muted-foreground">
        <FileText className="h-12 w-12 opacity-30" />
        <div>
          <p className="font-medium text-foreground">
            {translate("custom.content.preview.pdf_load_failed")}
          </p>
          <p className="mt-1 text-sm">{translate("custom.content.preview.pdf_load_failed_hint")}</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="outline" size="sm" onClick={() => window.open(url, "_blank")}>
            <ExternalLink className="mr-2 h-4 w-4" />
            {translate("custom.content.actions.open_original")}
          </Button>
        </div>
      </div>
    );
  }

  const searchHasMatches = Boolean(searchMatches.total && searchMatches.total > 0);
  const togglePagesPane = () => {
    setOverviewOpen((current) => !current);
  };
  const toolbarControls = (
    <div className="flex min-w-max flex-1 items-center gap-2 pr-2">
      <Button
        type="button"
        variant={overviewOpen ? "secondary" : "outline"}
        size="icon"
        className="h-8 w-8"
        onClick={togglePagesPane}
        aria-label={translate(
          overviewOpen
            ? "custom.content.preview.pdf_hide_overview"
            : "custom.content.preview.pdf_show_overview",
        )}
        title={translate(
          overviewOpen
            ? "custom.content.preview.pdf_hide_overview"
            : "custom.content.preview.pdf_show_overview",
        )}
      >
        <Files className="h-4 w-4" />
      </Button>
      <div className="min-w-[3.75rem] rounded-md border bg-muted/30 px-2 py-1 text-center text-xs text-muted-foreground">
        {activePage}/{numPages || "-"}
      </div>
      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => applyViewerZoom(zoomRef.current + ZOOM_STEP)}
          disabled={zoom >= MAX_ZOOM}
          title={translate("custom.content.preview.pdf_zoom_in")}
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <span className="w-12 text-center text-xs text-muted-foreground">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => applyViewerZoom(zoomRef.current - ZOOM_STEP)}
          disabled={zoom <= MIN_ZOOM}
          title={translate("custom.content.preview.pdf_zoom_out")}
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => applyViewerZoom(1)}
          title={translate("custom.content.preview.pdf_reset_zoom")}
        >
          <Scan className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={rotateClockwise}
          title={translate("custom.content.preview.pdf_rotate_clockwise")}
        >
          <RotateCwSquare className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex min-w-[14rem] flex-1 items-center gap-1">
        <div className="relative min-w-[12rem] max-w-xs flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(event) => updateSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault();
              moveSearchResult(event.shiftKey);
            }}
            placeholder={translate("custom.content.preview.pdf_search_placeholder")}
            className="h-8 pl-8 pr-8 text-xs"
          />
          {searchQuery ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute right-0.5 top-0.5 h-7 w-7"
              onClick={() => updateSearchQuery("")}
              aria-label={translate("custom.content.preview.pdf_clear_search")}
              title={translate("custom.content.preview.pdf_clear_search")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => moveSearchResult(false)}
          disabled={!searchHasMatches}
          aria-label={translate("custom.content.preview.pdf_next_match")}
          title={translate("custom.content.preview.pdf_next_match")}
        >
          <ChevronDown className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => moveSearchResult(true)}
          disabled={!searchHasMatches}
          aria-label={translate("custom.content.preview.pdf_previous_match")}
          title={translate("custom.content.preview.pdf_previous_match")}
        >
          <ChevronUp className="h-4 w-4" />
        </Button>
        <div className="min-w-[5.5rem] text-center text-xs text-muted-foreground">
          {normalizedSearchQuery
            ? searchLoading
              ? translate("custom.content.preview.pdf_searching")
              : searchHasMatches
                ? translate("custom.content.preview.pdf_search_count", {
                    current: searchMatches.current ?? 0,
                    total: searchMatches.total ?? 0,
                  })
                : searchState === FindState.NOT_FOUND || searchMatches.total === 0
                  ? translate("custom.content.preview.pdf_no_matches")
                  : null
            : null}
        </div>
      </div>
    </div>
  );

  return (
    <div className="h-full min-h-0 bg-muted/20">
      {toolbarPortalTarget ? createPortal(toolbarControls, toolbarPortalTarget) : null}
      <div className="flex h-full min-h-0 flex-col">
        {!useExternalToolbar && !toolbarPortalTarget ? (
          <div className="flex shrink-0 overflow-x-auto border-b bg-background/95 px-3 py-2 shadow-sm backdrop-blur">
            {toolbarControls}
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {overviewOpen ? (
            <aside className="hidden min-h-0 w-56 shrink-0 flex-col border-r bg-background md:flex xl:w-64">
              <div className="shrink-0 border-b px-3 py-2 text-xs font-medium text-muted-foreground">
                {translate("custom.content.preview.pdf_pages")}
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                <div className="space-y-3">
                  {pageNumbers.map((pageNumber) => (
                    <PdfThumbnailButton
                      key={pageNumber}
                      active={activePage === pageNumber}
                      pageNumber={pageNumber}
                      pdfDocument={pdfDocument}
                      rotation={rotation}
                      totalPages={numPages}
                      onClick={() => goToPage(pageNumber)}
                    />
                  ))}
                </div>
              </div>
            </aside>
          ) : null}

          <section ref={viewportRef} className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <div className="relative min-h-0 flex-1">
              <div
                ref={viewerContainerRef}
                className={cn(
                  "pdf-scroll-container absolute inset-0 overflow-auto bg-muted/30 p-4",
                  zoom > 1 && "cursor-grab",
                  isPanning && "cursor-grabbing select-none",
                )}
                tabIndex={0}
              >
                {loading ? <PdfLoading /> : null}
                <div
                  ref={viewerRef}
                  className="pdfViewer [&_.page]:rounded-sm [&_.page]:shadow-sm [&_.textLayer_.highlight]:rounded-[2px] [&_.textLayer_.highlight]:bg-yellow-300/80"
                />
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

const PdfThumbnailButton = ({
  active,
  pageNumber,
  pdfDocument,
  rotation,
  totalPages,
  onClick,
}: {
  active: boolean;
  pageNumber: number;
  pdfDocument: PDFDocumentProxy | null;
  rotation: number;
  totalPages: number;
  onClick: () => void;
}) => {
  const translate = useTranslate();
  const wrapperRef = useRef<HTMLButtonElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pdfDocument || !visible) return;

    let cancelled = false;
    let page: PDFPageProxy | null = null;
    let renderTask: ReturnType<PDFPageProxy["render"]> | null = null;

    const renderThumbnail = async () => {
      page = await pdfDocument.getPage(pageNumber);
      if (cancelled) return;

      const pageRotation = (page.rotate + rotation) % 360;
      const baseViewport = page.getViewport({ scale: 1, rotation: pageRotation });
      const cssWidth = 104;
      const scale = cssWidth / baseViewport.width;
      const viewport = page.getViewport({ scale, rotation: pageRotation });
      const pixelRatio = window.devicePixelRatio || 1;
      const context = canvas.getContext("2d");
      if (!context) return;

      canvas.width = Math.floor(viewport.width * pixelRatio);
      canvas.height = Math.floor(viewport.height * pixelRatio);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      renderTask = page.render({ canvas, canvasContext: context, viewport });
      await renderTask.promise;
    };

    void renderThumbnail().catch(() => {
      if (!cancelled) {
        canvas.removeAttribute("style");
      }
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
      page?.cleanup();
    };
  }, [pageNumber, pdfDocument, rotation, visible]);

  return (
    <button
      ref={wrapperRef}
      type="button"
      className={cn(
        "flex w-full flex-col items-center gap-2 rounded-md border bg-muted/30 p-2 text-xs text-muted-foreground transition-colors hover:border-primary/60 hover:bg-muted",
        active && "border-primary bg-primary/5 text-primary",
      )}
      onClick={onClick}
    >
      <canvas className="rounded-sm bg-white shadow-sm ring-1 ring-black/10" ref={canvasRef} />
      <span className="rounded px-2 py-1">
        {translate("custom.content.preview.pdf_page", {
          page: pageNumber,
          total: totalPages,
        })}
      </span>
    </button>
  );
};

const PdfLoading = () => (
  <div className="absolute inset-0 z-10 flex h-full flex-col gap-3 bg-muted/20 p-6">
    <Skeleton className="h-9 w-full rounded-md" />
    <div className="flex min-h-0 flex-1 gap-4">
      <Skeleton className="hidden h-full w-56 rounded-md md:block" />
      <Skeleton className="h-full flex-1 rounded-md" />
    </div>
  </div>
);
