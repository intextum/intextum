import { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { type ContentItemInfo, type ContentReviewSubmitPayload } from "@/dataProvider";
import { DocumentDataPanel } from "./DocumentDataPanel";

interface DataPaneProps {
  file: ContentItemInfo;
  savingEnrichment: boolean;
  onSubmitReview?: (payload: ContentReviewSubmitPayload) => Promise<unknown>;
  onVerifyClass?: (classificationLabel: string) => Promise<unknown>;
  onNavigateToEvidence?: (docRefs: string[], label: string) => void;
  onRerunEnrichment?: () => void;
}

export const DataPane = ({
  file,
  savingEnrichment,
  onSubmitReview,
  onVerifyClass,
  onNavigateToEvidence,
  onRerunEnrichment,
}: DataPaneProps) => {
  const [footerSlot, setFooterSlot] = useState<HTMLDivElement | null>(null);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background">
      <ScrollArea className="min-h-0 flex-1">
        <div className="p-3">
          <DocumentDataPanel
            file={file}
            savingEnrichment={savingEnrichment}
            onSubmitReview={onSubmitReview}
            onVerifyClass={onVerifyClass}
            onNavigateToEvidence={onNavigateToEvidence}
            onRerunEnrichment={onRerunEnrichment}
            footerSlot={footerSlot}
          />
        </div>
      </ScrollArea>
      <div
        ref={setFooterSlot}
        className="shrink-0 border-t bg-background/95 px-3 py-2 empty:hidden"
      />
    </div>
  );
};
