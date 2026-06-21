import type { ContentItemInfo } from "../dataProvider.ts";

import {
  getDocumentClassificationLabel,
  hasNeedsReviewContentEnrichment,
  hasStaleContentEnrichment,
} from "./content-enrichment.ts";

export interface ContentListRowModel {
  folderPath: string;
  isProcessing: boolean;
  visibleStatus: string | null;
  showDocumentClassBadge: boolean;
  showNeedsReviewBadge: boolean;
}

const ACTIVE_PROCESSING_STATUSES = new Set(["QUEUED", "PROCESSING", "RETRYING"]);
const QUIET_STATUSES = new Set(["COMPLETED"]);

export function buildContentListRowModel(file: ContentItemInfo): ContentListRowModel {
  const pathParts = file.path.split("/");
  const folderPath = pathParts.length > 1 ? pathParts.slice(0, -1).join("/") : "";
  const isProcessing = ACTIVE_PROCESSING_STATUSES.has(file.status ?? "");
  const hasClassLabel = getDocumentClassificationLabel(file.document_classification) !== null;
  const isStale = hasStaleContentEnrichment(
    file.document_enrichment?.classification_lifecycle,
    file.document_enrichment?.extraction_lifecycle,
  );

  return {
    folderPath,
    isProcessing,
    visibleStatus: !file.status || QUIET_STATUSES.has(file.status) ? null : file.status,
    showDocumentClassBadge: hasClassLabel || isStale,
    showNeedsReviewBadge: hasNeedsReviewContentEnrichment(file.document_extraction),
  };
}
