/**
 * Content browser page with unified navigation-based explorer and flat "All Content" view.
 */
import { useNotify, useTranslate } from "@/lib/app-context";
import { ContentPageContent } from "@/components/content-page/ContentPageContent";
import { ContentPageHeader } from "@/components/content-page/ContentPageHeader";
import { ContentItemDetailsDialog } from "@/components/ContentItemDetailsDialog";
import { UploadDialog } from "@/components/UploadDialog";
import { CreateDirectoryDialog } from "@/components/CreateDirectoryDialog";
import { PageShell } from "@/components/page/PageShell";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useContentPageContentListViewProps } from "@/hooks/useContentPageContentListViewProps";
import { useContentPageSearchState } from "@/hooks/useContentPageSearchState";
import { useContentPageActions } from "@/hooks/useContentPageActions";
import { buildContentPageDialogModel, type ContentPageViewMode } from "@/lib/content-page";

type ViewMode = ContentPageViewMode;

interface ContentListProps {
  forcedViewMode?: ViewMode;
  titleKey?: string;
}

export const ContentList = ({
  forcedViewMode,
  titleKey = "resources.content.name",
}: ContentListProps = {}) => {
  const notify = useNotify();
  const translate = useTranslate();
  useDocumentTitle(translate(titleKey));
  const {
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
    allFilesSearchMode,
    allFilesInitialQuery,
    activeSelectedFile,
    refreshKey,
    isImmutable,
    setIsImmutable,
    uploadOpen,
    setUploadOpen,
    mkdirOpen,
    setMkdirOpen,
    pathParts,
    breadcrumbPaths,
    handleRefresh,
    handleNavigate,
    handleFileClick,
    clearSelectedFileSelection,
    handleDetailsOpenChange,
    handleAllFilesStaleOnlyChange,
    handleAllFilesStatusFilterChange,
    handleAllFilesDocumentClassFilterChange,
    handleAllFilesExtractionSchemaFilterChange,
    handleAllFilesExtractionFieldFilterChange,
    handleAllFilesFieldFiltersChange,
    handleAllFilesReviewStatusFilterChange,
    handleAllFilesSearchModeChange,
  } = useContentPageSearchState({
    forcedViewMode,
    notify,
    translate,
  });

  const { handleProcess, handleProcessSelected, handleDelete, handleMutationSuccess } =
    useContentPageActions({
      notify,
      translate,
      selectedFilePath,
      onRefresh: handleRefresh,
      onClearSelectedFile: clearSelectedFileSelection,
    });
  const allFilesViewProps = useContentPageContentListViewProps({
    viewMode,
    currentPath,
    allFilesDocumentClassFilter,
    allFilesExtractionSchemaFilter,
    allFilesExtractionFieldFilter,
    allFilesFieldFilters,
    allFilesStaleOnly,
    allFilesStatusFilter,
    allFilesReviewStatusFilter,
    allFilesSearchMode,
    allFilesInitialQuery,
    refreshKey,
    onNavigate: handleNavigate,
    onImmutableChange: setIsImmutable,
    onFileClick: handleFileClick,
    onProcess: handleProcess,
    onSearchModeChange: handleAllFilesSearchModeChange,
    onDocumentClassFilterChange: handleAllFilesDocumentClassFilterChange,
    onExtractionSchemaFilterChange: handleAllFilesExtractionSchemaFilterChange,
    onExtractionFieldFilterChange: handleAllFilesExtractionFieldFilterChange,
    onFieldFiltersChange: handleAllFilesFieldFiltersChange,
    onStaleOnlyChange: handleAllFilesStaleOnlyChange,
    onStatusFilterChange: handleAllFilesStatusFilterChange,
    onReviewStatusFilterChange: handleAllFilesReviewStatusFilterChange,
    onProcessSelected: handleProcessSelected,
  });
  const dialogModel = buildContentPageDialogModel({
    selectedFilePath,
    selectedFileImmutable: activeSelectedFile?.immutable ?? false,
  });

  return (
    <PageShell contentClassName="space-y-4 p-4 md:p-6">
      <ContentPageHeader
        titleKey={titleKey}
        currentPath={currentPath}
        isImmutable={isImmutable}
        pathParts={pathParts}
        breadcrumbPaths={breadcrumbPaths}
        onNavigate={handleNavigate}
        onOpenUpload={() => setUploadOpen(true)}
        onOpenCreateDirectory={() => setMkdirOpen(true)}
        onRefresh={handleRefresh}
      />

      <ContentPageContent allFilesViewProps={allFilesViewProps} />

      {dialogModel.showFileDetailsDialog && (
        <ContentItemDetailsDialog
          file={activeSelectedFile}
          open={dialogModel.fileDetailsOpen}
          onOpenChange={handleDetailsOpenChange}
          onProcess={handleProcess}
          onDelete={dialogModel.canDeleteFromFileDetails ? handleDelete : undefined}
        />
      )}

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        currentPath={currentPath}
        onSuccess={handleMutationSuccess}
      />
      <CreateDirectoryDialog
        open={mkdirOpen}
        onOpenChange={setMkdirOpen}
        currentPath={currentPath}
        onSuccess={handleMutationSuccess}
      />
    </PageShell>
  );
};
