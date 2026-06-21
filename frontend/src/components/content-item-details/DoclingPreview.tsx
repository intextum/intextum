import { useState, useEffect, useRef } from "react";
import { useTranslate } from "@/lib/app-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { contentApi } from "@/dataProvider";

interface DoclingPreviewProps {
  filePath: string;
  contentItemId?: string;
  highlightItems?: string;
  initialDocData?: unknown;
}

interface DoclingImgElement extends HTMLElement {
  src?: unknown;
}

export const DoclingPreview = ({
  filePath,
  contentItemId,
  highlightItems,
  initialDocData,
}: DoclingPreviewProps) => {
  const translate = useTranslate();
  const [docData, setDocData] = useState<unknown>(initialDocData || null);
  const [loading, setLoading] = useState(!initialDocData);
  const [error, setError] = useState(false);
  const [componentsLoaded, setComponentsLoaded] = useState(false);
  const hasFocusedItems = typeof highlightItems === "string" && highlightItems.trim().length > 0;
  const [showFull, setShowFull] = useState(!hasFocusedItems);
  const doclingRef = useRef<DoclingImgElement>(null);

  useEffect(() => {
    if (customElements.get("docling-img")) {
      setComponentsLoaded(true);
      return;
    }
    import("@docling/docling-components")
      .then(() => {
        setComponentsLoaded(true);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (initialDocData) {
      setDocData(initialDocData);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(false);
    const request = contentItemId
      ? contentApi.getExtractedDocumentById(contentItemId)
      : contentApi.getExtractedDocument(filePath);
    request
      .then(setDocData)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [contentItemId, filePath, initialDocData]);

  useEffect(() => {
    if (hasFocusedItems) {
      setShowFull(false);
    } else {
      setShowFull(true);
    }
  }, [hasFocusedItems, highlightItems]);

  useEffect(() => {
    if (doclingRef.current && docData) {
      doclingRef.current.src = docData;
    }
  }, [docData, componentsLoaded, showFull, highlightItems]);

  if (loading || !componentsLoaded) return <Skeleton className="h-full w-full" />;
  if (error || !docData) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center px-8 text-center text-sm text-muted-foreground">
        {translate("custom.content.preview.docling_unavailable")}
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden">
      {hasFocusedItems && !showFull ? (
        <div className="absolute top-4 left-4 z-20 flex items-center gap-2 rounded-full border bg-background/80 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider shadow-sm backdrop-blur">
          <span>{translate("custom.content.preview.focused_evidence")}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 rounded-full px-2 text-[10px]"
            onClick={() => setShowFull(true)}
          >
            {translate("custom.content.preview.show_full_document")}
          </Button>
        </div>
      ) : null}

      <ScrollArea className="min-h-0 flex-1 bg-background">
        {showFull ? (
          <docling-img ref={doclingRef} key="docling-full" pagenumbers backdrop className="w-full">
            <docling-tooltip />
          </docling-img>
        ) : (
          <docling-img
            ref={doclingRef}
            key={highlightItems ? `docling-focus-${highlightItems}` : "docling-trimmed"}
            items={highlightItems}
            pagenumbers
            backdrop
            trim="pages"
            className="w-full"
          >
            <docling-tooltip />
          </docling-img>
        )}
      </ScrollArea>
    </div>
  );
};
