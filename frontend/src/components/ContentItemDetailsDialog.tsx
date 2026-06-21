import { lazy, Suspense, useMemo } from "react";
import { useLocation, useNavigate } from "react-router";
import { Skeleton } from "@/components/ui/skeleton";
import { retryDynamicImport } from "@/lib/dynamic-import";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { ContentItemInfo } from "@/dataProvider";
import type { ContentItemProcessHandler } from "@/hooks/useContentItemDetails";

export interface ContentItemDetailsDialogProps {
  file: ContentItemInfo | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onProcess?: ContentItemProcessHandler;
  onDelete?: (path: string) => void;
  initialHighlightRefs?: string[];
}

const LazyContentItemDetailsContent = lazy(async () => {
  const module = await retryDynamicImport(
    () => import("@/components/content-item-details/ContentItemDetailsContent"),
  );
  return { default: module.ContentItemDetailsContent };
});

const inspectorContentClassName =
  "w-full max-w-full gap-0 overflow-hidden p-0 sm:w-[1220px] sm:max-w-[97vw]";
const RESIZE_HANDLE_OUTSIDE_GUARD_PX = 16;

type SheetOutsideInteractionEvent = Event & {
  detail?: {
    originalEvent?: Event;
  };
};

const eventPathHasResizeHandle = (event: Event) => {
  const path = typeof event.composedPath === "function" ? event.composedPath() : [];
  return path.some((target) => {
    if (!(target instanceof Element)) {
      return false;
    }
    return Boolean(target.closest("[data-dialog-resize-handle]"));
  });
};

const pointerEventIsNearResizeHandle = (event: Event | undefined) => {
  if (
    !(event instanceof PointerEvent || event instanceof MouseEvent) ||
    typeof document === "undefined"
  ) {
    return false;
  }

  const handles = document.querySelectorAll("[data-dialog-resize-handle]");
  for (const handle of handles) {
    const rect = handle.getBoundingClientRect();
    if (
      event.clientX >= rect.left - RESIZE_HANDLE_OUTSIDE_GUARD_PX &&
      event.clientX <= rect.right + RESIZE_HANDLE_OUTSIDE_GUARD_PX &&
      event.clientY >= rect.top - RESIZE_HANDLE_OUTSIDE_GUARD_PX &&
      event.clientY <= rect.bottom + RESIZE_HANDLE_OUTSIDE_GUARD_PX
    ) {
      return true;
    }
  }

  return false;
};

const ContentItemDetailsDialogFallback = () => (
  <div className="flex h-full min-h-0 flex-col bg-muted/10">
    <div className="flex h-12 shrink-0 items-center gap-3 border-b bg-background px-4">
      <Skeleton className="h-7 w-7 rounded-md" />
      <Skeleton className="h-4 w-56" />
      <div className="ml-auto flex gap-2">
        <Skeleton className="h-8 w-24 rounded-md" />
        <Skeleton className="h-8 w-28 rounded-md" />
        <Skeleton className="h-8 w-8 rounded-md" />
      </div>
    </div>
    <div className="flex h-9 shrink-0 items-center gap-2 border-b bg-background px-3">
      <Skeleton className="h-6 w-16 rounded-md" />
      <Skeleton className="h-6 w-10 rounded-md" />
    </div>
    <div className="min-h-0 flex-1 p-5">
      <Skeleton className="h-full w-full rounded-xl" />
    </div>
    <div className="h-9 shrink-0 border-t bg-background" />
  </div>
);

export const ContentItemDetailsDialog = ({
  file: initialFile,
  open,
  onOpenChange,
  onProcess,
  onDelete,
  initialHighlightRefs,
}: ContentItemDetailsDialogProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const preventResizeHandleOutsideClose = (event: SheetOutsideInteractionEvent) => {
    const target = event.target instanceof Element ? event.target : null;
    const originalEvent = event.detail?.originalEvent;
    if (
      target?.closest("[data-dialog-resize-handle]") ||
      eventPathHasResizeHandle(event) ||
      (originalEvent ? eventPathHasResizeHandle(originalEvent) : false) ||
      pointerEventIsNearResizeHandle(originalEvent)
    ) {
      event.preventDefault();
    }
  };

  const contentKey = useMemo(
    () => (initialFile ? `${initialFile.path}:${(initialHighlightRefs ?? []).join("|")}` : "none"),
    [initialFile, initialHighlightRefs],
  );
  const contentFile = open ? initialFile : null;
  const closeThenNavigate = (target: string) => {
    onOpenChange(false);
    // Let the Sheet close animation finish so Radix can restore body pointer-events
    // before the route changes (otherwise the body stays locked).
    window.setTimeout(() => navigate(target), 200);
  };
  const handleOpenActivity = () => {
    if (!initialFile) return;
    const from = `${location.pathname}${location.search}`;
    closeThenNavigate(
      `/content/item/${encodeURIComponent(initialFile.id)}/activity?from=${encodeURIComponent(from)}`,
    );
  };
  const handleOpenAsPage = () => {
    if (!initialFile) return;
    const from = `${location.pathname}${location.search}`;
    closeThenNavigate(
      `/content/item/${encodeURIComponent(initialFile.id)}?from=${encodeURIComponent(from)}`,
    );
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className={inspectorContentClassName}
        onInteractOutside={preventResizeHandleOutsideClose}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onPointerDownOutside={preventResizeHandleOutsideClose}
      >
        <SheetHeader className="sr-only">
          <SheetTitle>
            {contentFile?.display_name ?? contentFile?.name ?? "Content details"}
          </SheetTitle>
          <SheetDescription>Content inspector</SheetDescription>
        </SheetHeader>
        {contentFile ? (
          <Suspense fallback={<ContentItemDetailsDialogFallback />}>
            <LazyContentItemDetailsContent
              key={contentKey}
              initialFile={contentFile}
              open={open}
              onProcess={onProcess}
              onDelete={onDelete}
              initialHighlightRefs={initialHighlightRefs}
              onOpenActivity={handleOpenActivity}
              onOpenAsPage={handleOpenAsPage}
            />
          </Suspense>
        ) : null}
      </SheetContent>
    </Sheet>
  );
};
