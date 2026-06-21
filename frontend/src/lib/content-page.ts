import type { ContentListViewProps } from "@/components/ContentListView";
import type { ContentEnrichmentReviewStatus, ContentItemInfo } from "@/dataProvider";
import type {
  ContentItemProcessHandler,
  ProcessingConfigPayload,
} from "@/hooks/useContentItemDetails";

export type ContentPageViewMode = "browse" | "all";

export interface ContentPageUrlState {
  currentPath: string;
  selectedFilePath: string | null;
  viewMode: ContentPageViewMode;
  allFilesStaleOnly: boolean;
  allFilesStatusFilter: string;
  allFilesDocumentClassFilter: string;
  allFilesExtractionSchemaFilter: string;
  allFilesExtractionFieldFilter: string;
  allFilesFieldFilters: string;
  allFilesReviewStatusFilter: string;
  pathParts: string[];
  breadcrumbPaths: string[];
}

export interface BuildContentPageAllFilesViewPropsOptions {
  viewMode: ContentPageViewMode;
  currentPath: string;
  allFilesDocumentClassFilter: string;
  allFilesExtractionSchemaFilter: string;
  allFilesExtractionFieldFilter: string;
  allFilesFieldFilters: string;
  allFilesStaleOnly: boolean;
  allFilesStatusFilter: string;
  allFilesReviewStatusFilter: string;
  refreshKey: number;
  onNavigate: (path: string) => void;
  onImmutableChange: (immutable: boolean) => void;
  onFileClick: (file: ContentItemInfo) => void;
  onProcess: ContentItemProcessHandler;
  onDocumentClassFilterChange: (documentClass: string) => void;
  onExtractionSchemaFilterChange: (schema: string) => void;
  onExtractionFieldFilterChange: (field: string) => void;
  onFieldFiltersChange: (serialized: string) => void;
  onStaleOnlyChange: (staleOnly: boolean) => void;
  onStatusFilterChange: (status: string) => void;
  onReviewStatusFilterChange: (reviewStatus: string) => void;
  onProcessSelected: (paths: string[], processingConfig?: ProcessingConfigPayload) => Promise<void>;
}

export interface BuildContentPageHeaderStateOptions {
  currentPath: string;
  isImmutable: boolean;
}

export interface ContentPageHeaderState {
  showViewTabs: boolean;
  showTitle: boolean;
  showBrowseBreadcrumbs: boolean;
  showBrowseActions: boolean;
}

export interface ContentPageHeaderBreadcrumbItem {
  key: string;
  label: string;
  path: string;
  isCurrent: boolean;
  isRoot: boolean;
  isEllipsis?: boolean;
}

export type ContentPageHeaderAction = "upload" | "mkdir" | "refresh";

const MAX_VISIBLE_CONTENT_BREADCRUMB_PATH_ITEMS = 3;

export interface BuildContentPageContentStateOptions {
  isImmutable: boolean;
  hasDeleteHandler: boolean;
}

export interface ContentPageContentState {
  showReviewWorkspace: boolean;
  showBrowseExplorer: boolean;
  showAllFilesView: boolean;
  canDeleteFromBrowse: boolean;
  canDeleteFromReview: boolean;
}

export interface BuildContentPageContentRenderModelOptions extends BuildContentPageContentStateOptions {
  currentPath: string;
  refreshKey: number;
}

export interface ContentPageContentRenderModel {
  surface: "browse" | "all";
  explorerKey: string | null;
  canDeleteFromBrowse: boolean;
  canDeleteFromReview: boolean;
}

export interface BuildContentPageDialogModelOptions {
  selectedFilePath: string | null;
  selectedFileImmutable: boolean;
}

export interface ContentPageDialogModel {
  showFileDetailsDialog: boolean;
  fileDetailsOpen: boolean;
  canDeleteFromFileDetails: boolean;
}

export function readContentPageUrlState(
  searchParams: URLSearchParams,
  forcedViewMode?: ContentPageViewMode,
): ContentPageUrlState {
  const currentPath = searchParams.get("path") ?? "";
  const selectedFilePath = searchParams.get("file");
  const viewMode =
    forcedViewMode ?? ((searchParams.get("view") as ContentPageViewMode | null) || "browse");
  const allFilesStaleOnly = searchParams.get("stale_enrichment") === "true";
  const allFilesStatusFilter = searchParams.get("status") ?? "";
  const allFilesDocumentClassFilter = searchParams.get("document_class") ?? "";
  const allFilesExtractionSchemaFilter = searchParams.get("extraction_schema") ?? "";
  const allFilesExtractionFieldFilter = searchParams.get("extraction_field") ?? "";
  const allFilesFieldFilters = searchParams.get("field_filters") ?? "";
  const allFilesReviewStatusFilter = searchParams.get("review_status") ?? "";
  const pathParts = currentPath.split("/").filter(Boolean);
  const breadcrumbPaths = pathParts.map((_, index) => pathParts.slice(0, index + 1).join("/"));

  return {
    currentPath,
    selectedFilePath,
    viewMode,
    allFilesStaleOnly,
    allFilesStatusFilter,
    allFilesDocumentClassFilter,
    allFilesExtractionSchemaFilter,
    allFilesExtractionFieldFilter,
    allFilesFieldFilters,
    allFilesReviewStatusFilter,
    pathParts,
    breadcrumbPaths,
  };
}

export function applyContentPageViewModeChange(
  searchParams: URLSearchParams,
  value: string,
  forcedViewMode?: ContentPageViewMode,
): URLSearchParams {
  if (forcedViewMode) {
    return searchParams;
  }

  if (value === "browse") {
    searchParams.delete("view");
  } else {
    searchParams.set("view", value);
  }

  searchParams.delete("file");
  return searchParams;
}

export function applyContentPageReviewStatusFilterChange(
  searchParams: URLSearchParams,
  reviewStatus: string,
): URLSearchParams {
  if (reviewStatus) {
    searchParams.set("review_status", reviewStatus);
  } else {
    searchParams.delete("review_status");
  }
  return searchParams;
}

export function buildContentPageHeaderState({
  currentPath,
  isImmutable,
}: BuildContentPageHeaderStateOptions): ContentPageHeaderState {
  return {
    showViewTabs: false,
    showTitle: true,
    showBrowseBreadcrumbs: true,
    showBrowseActions: Boolean(currentPath) && !isImmutable,
  };
}

export function buildContentPageHeaderBreadcrumbItems({
  pathParts,
  breadcrumbPaths,
}: {
  pathParts: string[];
  breadcrumbPaths: string[];
}): ContentPageHeaderBreadcrumbItem[] {
  const hasHiddenPathParts = pathParts.length > MAX_VISIBLE_CONTENT_BREADCRUMB_PATH_ITEMS;
  const visibleStartIndex = hasHiddenPathParts
    ? pathParts.length - MAX_VISIBLE_CONTENT_BREADCRUMB_PATH_ITEMS
    : 0;
  const items: ContentPageHeaderBreadcrumbItem[] = [
    {
      key: "root",
      label: "custom.root",
      path: "",
      isCurrent: pathParts.length === 0,
      isRoot: true,
    },
  ];

  if (hasHiddenPathParts) {
    items.push({
      key: "ellipsis",
      label: "...",
      path: "",
      isCurrent: false,
      isRoot: false,
      isEllipsis: true,
    });
  }

  pathParts.slice(visibleStartIndex).forEach((part, visibleIndex) => {
    const index = visibleStartIndex + visibleIndex;
    items.push({
      key: breadcrumbPaths[index] ?? part,
      label: part,
      path: breadcrumbPaths[index] ?? "",
      isCurrent: index === pathParts.length - 1,
      isRoot: false,
    });
  });

  return items;
}

export function buildContentPageHeaderActions({
  currentPath,
  isImmutable,
}: {
  currentPath: string;
  isImmutable: boolean;
}): ContentPageHeaderAction[] {
  const actions: ContentPageHeaderAction[] = [];

  if (currentPath && !isImmutable) {
    actions.push("upload", "mkdir");
  }

  actions.push("refresh");
  return actions;
}

export function buildContentPageContentState({
  isImmutable,
  hasDeleteHandler,
}: BuildContentPageContentStateOptions): ContentPageContentState {
  return {
    showReviewWorkspace: false,
    showBrowseExplorer: true,
    showAllFilesView: true,
    canDeleteFromBrowse: hasDeleteHandler && !isImmutable,
    canDeleteFromReview: false,
  };
}

export function buildContentPageContentRenderModel({
  currentPath,
  refreshKey,
  ...stateOptions
}: BuildContentPageContentRenderModelOptions): ContentPageContentRenderModel {
  const state = buildContentPageContentState(stateOptions);

  return {
    surface: "all",
    explorerKey: `${currentPath}-${refreshKey}`,
    canDeleteFromBrowse: state.canDeleteFromBrowse,
    canDeleteFromReview: false,
  };
}

export function buildContentPageDialogModel({
  selectedFilePath,
  selectedFileImmutable,
}: BuildContentPageDialogModelOptions): ContentPageDialogModel {
  return {
    showFileDetailsDialog: true,
    fileDetailsOpen: Boolean(selectedFilePath),
    canDeleteFromFileDetails: !selectedFileImmutable,
  };
}

export function buildContentPageAllFilesViewProps({
  viewMode: _viewMode,
  currentPath,
  allFilesDocumentClassFilter,
  allFilesExtractionSchemaFilter,
  allFilesExtractionFieldFilter,
  allFilesFieldFilters,
  allFilesStaleOnly,
  allFilesStatusFilter,
  allFilesReviewStatusFilter,
  refreshKey,
  onNavigate,
  onImmutableChange,
  onFileClick,
  onProcess,
  onDocumentClassFilterChange,
  onExtractionSchemaFilterChange,
  onExtractionFieldFilterChange,
  onFieldFiltersChange,
  onStaleOnlyChange,
  onStatusFilterChange,
  onReviewStatusFilterChange,
  onProcessSelected,
}: BuildContentPageAllFilesViewPropsOptions): ContentListViewProps {
  return {
    currentPath,
    onNavigate,
    onImmutableChange,
    onFileClick,
    onProcess,
    initialSortBy: "name",
    initialSortOrder: "asc",
    initialDocumentClassFilter: allFilesDocumentClassFilter,
    initialExtractionSchemaFilter: allFilesExtractionSchemaFilter,
    initialExtractionFieldFilter: allFilesExtractionFieldFilter,
    initialFieldFilters: allFilesFieldFilters,
    initialStaleOnly: allFilesStaleOnly,
    initialStatusFilter: allFilesStatusFilter,
    initialReviewStatusFilter: allFilesReviewStatusFilter as ContentEnrichmentReviewStatus | "",
    onDocumentClassFilterChange,
    onExtractionSchemaFilterChange,
    onExtractionFieldFilterChange,
    onFieldFiltersChange,
    onStaleOnlyChange,
    onStatusFilterChange,
    onReviewStatusFilterChange,
    onProcessSelected,
    refreshKey,
  };
}
