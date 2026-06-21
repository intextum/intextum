import { useCallback, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslate } from "@/lib/app-context";

import { ContentListBatchActionBar } from "@/components/content-list/ContentListBatchActionBar";
import { ContentListFilterBar } from "@/components/content-list/ContentListFilterBar";
import { ContentListTable } from "@/components/content-list/ContentListTable";
import type { SortBy, SortOrder } from "@/components/content-list/types";
import { useContentListFilters } from "@/components/content-list/useContentListFilters";
import { useContentListFolders } from "@/components/content-list/useContentListFolders";
import { useContentListListing } from "@/components/content-list/useContentListListing";
import {
  type AllFilesBatchFilters,
  type ContentEnrichmentReviewStatus,
  type ContentItemInfo,
  type ContentItemKind,
} from "@/dataProvider";
import {
  buildDocumentClassFilterChips,
  buildExtractionSchemaFilterChips,
  buildExtractionValueFilterChips,
} from "@/lib/content-enrichment";
import { normalizeDtype, type FieldFilterLeaf } from "@/lib/field-filters";
import type { ProcessingConfigPayload } from "@/hooks/useContentItemDetails";

export interface ContentListViewProps {
  currentPath?: string;
  onNavigate?: (path: string) => void;
  onImmutableChange?: (immutable: boolean) => void;
  onFileClick?: (file: ContentItemInfo) => void;
  onActiveFiltersChange?: (filters: AllFilesBatchFilters) => void;
  onProcess?: (path: string) => void;
  initialSortBy?: SortBy;
  initialSortOrder?: SortOrder;
  initialContentKindFilter?: ContentItemKind | "";
  initialDocumentClassFilter?: string;
  initialExtractionSchemaFilter?: string;
  initialExtractionFieldFilter?: string;
  initialFieldFilters?: string;
  initialStaleOnly?: boolean;
  initialStatusFilter?: string;
  initialReviewStatusFilter?: ContentEnrichmentReviewStatus | "";
  onDocumentClassFilterChange?: (documentClass: string) => void;
  onExtractionSchemaFilterChange?: (schema: string) => void;
  onExtractionFieldFilterChange?: (field: string) => void;
  onFieldFiltersChange?: (serialized: string) => void;
  onStaleOnlyChange?: (staleOnly: boolean) => void;
  onStatusFilterChange?: (status: string) => void;
  onReviewStatusFilterChange?: (status: ContentEnrichmentReviewStatus | "") => void;
  onProcessSelected?: (
    paths: string[],
    processingConfig?: ProcessingConfigPayload,
  ) => void | Promise<void>;
  refreshKey?: number;
}

export function ContentListView({
  currentPath = "",
  onNavigate,
  onImmutableChange,
  onFileClick,
  onActiveFiltersChange,
  onProcess,
  initialSortBy = "name",
  initialSortOrder = "asc",
  initialContentKindFilter = "",
  initialDocumentClassFilter = "",
  initialExtractionSchemaFilter = "",
  initialExtractionFieldFilter = "",
  initialFieldFilters = "",
  initialStaleOnly = false,
  initialStatusFilter = "",
  initialReviewStatusFilter = "",
  onDocumentClassFilterChange,
  onExtractionSchemaFilterChange,
  onExtractionFieldFilterChange,
  onFieldFiltersChange,
  onStaleOnlyChange,
  onStatusFilterChange,
  onReviewStatusFilterChange,
  onProcessSelected,
  refreshKey,
}: ContentListViewProps) {
  const translate = useTranslate();
  const [selectedFilePaths, setSelectedFilePaths] = useState<Set<string>>(() => new Set());
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      translate(`custom.content.content_list.${key}`, options),
    [translate],
  );

  const {
    nameFilter,
    setNameFilter,
    nameRegex,
    setNameRegex,
    searchPath,
    setSearchPath,
    contentKindFilter,
    setContentKindFilter,
    documentClassFilter,
    setDocumentClassFilter,
    extractionSchemaFilter,
    setExtractionSchemaFilter,
    extractionFieldFilter,
    setExtractionFieldFocus,
    fieldPredicates,
    addFieldCondition,
    updateFieldCondition,
    removeFieldCondition,
    extensionFilter,
    setExtensionFilter,
    statusFilter,
    staleOnly,
    reviewStatusFilter,
    sortBy,
    sortOrder,
    fetchParams,
    currentBatchFilters,
    handleToggleSort,
    handleToggleStaleOnly,
    handleStatusFilterChange,
    handleReviewStatusFilterChange,
    hasAnyFilter,
    activeFilterChips,
  } = useContentListFilters({
    currentPath,
    initialSortBy,
    initialSortOrder,
    initialContentKindFilter,
    initialDocumentClassFilter,
    initialExtractionSchemaFilter,
    initialExtractionFieldFilter,
    initialFieldFilters,
    initialStaleOnly,
    initialStatusFilter,
    initialReviewStatusFilter,
    onActiveFiltersChange,
    onDocumentClassFilterChange,
    onExtractionSchemaFilterChange,
    onExtractionFieldFilterChange,
    onFieldFiltersChange,
    onStaleOnlyChange,
    onStatusFilterChange,
    onReviewStatusFilterChange,
  });

  const {
    files,
    documentClassFacets,
    extractionSchemaFacets,
    extractionSchemaFieldFacets,
    extractionFieldFacets,
    extractionValueFacets,
    total,
    isLoading,
    isLoadingMore,
    sentinelRef,
  } = useContentListListing({
    fetchParams,
    refreshKey,
  });

  const folderModeEnabled = !hasAnyFilter && Boolean(onNavigate);
  const folderState = useContentListFolders({
    enabled: folderModeEnabled,
    path: currentPath,
    refreshKey,
    onImmutableChange,
  });

  const visibleFiles = folderModeEnabled ? folderState.files : files;
  const visibleFolders = folderModeEnabled ? folderState.folders : [];
  const visibleTotal = folderModeEnabled ? folderState.files.length : total;
  const visibleIsLoading = folderModeEnabled ? folderState.isLoading : isLoading;
  const selectedFilePathList = useMemo(() => Array.from(selectedFilePaths), [selectedFilePaths]);

  const suggestedDocumentClasses = useMemo(
    () => buildDocumentClassFilterChips(documentClassFacets, documentClassFilter),
    [documentClassFacets, documentClassFilter],
  );
  const suggestedExtractionSchemas = useMemo(
    () => buildExtractionSchemaFilterChips(extractionSchemaFacets, extractionSchemaFilter),
    [extractionSchemaFacets, extractionSchemaFilter],
  );
  // Prefer the configured schema's typed leaf paths (incl. nested object_list
  // and currency leaves); fall back to observed top-level field names.
  const fieldLeaves = useMemo<FieldFilterLeaf[]>(() => {
    if (extractionSchemaFieldFacets.length > 0) {
      return extractionSchemaFieldFacets.map((facet) => ({
        label: facet.label || facet.field,
        segments: facet.segments,
        dtype: normalizeDtype(facet.dtype),
        count: facet.count,
      }));
    }
    return extractionFieldFacets.map((facet) => ({
      label: facet.field,
      segments: [{ k: facet.field }],
      dtype: "str" as const,
      count: facet.count,
    }));
  }, [extractionFieldFacets, extractionSchemaFieldFacets]);
  const suggestedExtractionValues = useMemo(
    () => buildExtractionValueFilterChips(extractionValueFacets, ""),
    [extractionValueFacets],
  );

  const handleToggleFileSelection = useCallback((path: string, selected: boolean) => {
    setSelectedFilePaths((current) => {
      const next = new Set(current);
      if (selected) {
        next.add(path);
      } else {
        next.delete(path);
      }
      return next;
    });
  }, []);

  const handleToggleVisibleFileSelection = useCallback(
    (selected: boolean) => {
      setSelectedFilePaths((current) => {
        const next = new Set(current);
        for (const file of visibleFiles) {
          if (selected) {
            next.add(file.path);
          } else {
            next.delete(file.path);
          }
        }
        return next;
      });
    },
    [visibleFiles],
  );

  const handleClearSelection = useCallback(() => {
    setSelectedFilePaths(new Set());
  }, []);

  const handleProcessSelected = useCallback(
    async (paths: string[], processingConfig?: ProcessingConfigPayload) => {
      await onProcessSelected?.(paths, processingConfig);
      setSelectedFilePaths(new Set());
    },
    [onProcessSelected],
  );

  // Reset the selection whenever the active filters or folder change. Done
  // during render (not in an effect) to avoid a cascading-render lint/perf hit.
  const [selectionScope, setSelectionScope] = useState<{
    filters: AllFilesBatchFilters;
    path: string;
  }>(() => ({ filters: currentBatchFilters, path: currentPath }));
  if (selectionScope.filters !== currentBatchFilters || selectionScope.path !== currentPath) {
    setSelectionScope({ filters: currentBatchFilters, path: currentPath });
    setSelectedFilePaths(new Set());
  }

  return (
    <div className="flex flex-col gap-3">
      <ContentListFilterBar
        t={t}
        total={visibleTotal}
        isLoading={visibleIsLoading}
        nameFilter={nameFilter}
        nameRegex={nameRegex}
        searchPath={searchPath}
        contentKindFilter={contentKindFilter}
        documentClassFilter={documentClassFilter}
        extractionSchemaFilter={extractionSchemaFilter}
        extractionFieldFilter={extractionFieldFilter}
        fieldPredicates={fieldPredicates}
        extensionFilter={extensionFilter}
        statusFilter={statusFilter}
        staleOnly={staleOnly}
        reviewStatusFilter={reviewStatusFilter}
        activeFilterChips={activeFilterChips}
        documentClassChips={suggestedDocumentClasses}
        extractionSchemaChips={suggestedExtractionSchemas}
        fieldLeaves={fieldLeaves}
        extractionValueChips={suggestedExtractionValues}
        onNameFilterChange={setNameFilter}
        onNameRegexChange={setNameRegex}
        onSearchPathChange={setSearchPath}
        onContentKindFilterChange={setContentKindFilter}
        onDocumentClassFilterChange={setDocumentClassFilter}
        onExtractionSchemaFilterChange={setExtractionSchemaFilter}
        onSetExtractionFieldFocus={setExtractionFieldFocus}
        onAddFieldCondition={addFieldCondition}
        onUpdateFieldCondition={updateFieldCondition}
        onRemoveFieldCondition={removeFieldCondition}
        onExtensionFilterChange={setExtensionFilter}
        onStatusFilterChange={handleStatusFilterChange}
        onReviewStatusFilterChange={handleReviewStatusFilterChange}
        onToggleStaleOnly={handleToggleStaleOnly}
      />

      <ContentListBatchActionBar
        isLoading={visibleIsLoading}
        selectedCount={selectedFilePathList.length}
        selectedCountLabel={translate("custom.content.selection.count", {
          count: selectedFilePathList.length,
        })}
        clearSelectionLabel={translate("custom.content.selection.clear")}
        processSelectedLabel={translate("custom.content.actions.process_selected")}
        selectedFilePaths={selectedFilePathList}
        onProcessSelected={onProcessSelected ? handleProcessSelected : undefined}
        onClearSelection={handleClearSelection}
      />

      <ContentListTable
        t={t}
        processTooltip={translate("custom.content.actions.process")}
        files={visibleFiles}
        folders={visibleFolders}
        isLoading={visibleIsLoading}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onToggleSort={handleToggleSort}
        onFileClick={onFileClick}
        onFolderClick={onNavigate}
        onProcess={onProcess}
        selectedFilePaths={selectedFilePaths}
        onToggleFileSelection={handleToggleFileSelection}
        onToggleVisibleFileSelection={handleToggleVisibleFileSelection}
      />

      {!folderModeEnabled && (
        <>
          <div ref={sentinelRef} className="h-1" />
          {isLoadingMore && (
            <div className="flex justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              <span className="ml-2 text-sm text-muted-foreground">{t("loading_more")}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
