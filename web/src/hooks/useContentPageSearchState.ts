import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { NotificationOptions, NotificationType } from "@/lib/app-context";

import { contentApi, type ContentItemInfo } from "@/dataProvider";
import {
  applyContentPageReviewStatusFilterChange,
  applyContentPageViewModeChange,
  readContentPageUrlState,
  type ContentPageViewMode,
} from "@/lib/content-page";
import { startContentPageSelectedFileLoad } from "@/lib/content-page-search-state";
import { invalidateContentQueries } from "@/lib/query-client";

type NotifyFn = (
  message: ReactNode,
  options?: NotificationOptions & { type?: NotificationType },
) => void;
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

interface UseContentPageSearchStateOptions {
  forcedViewMode?: ContentPageViewMode;
  notify: NotifyFn;
  translate: TranslateFn;
}

export function useContentPageSearchState({
  forcedViewMode,
  notify,
  translate,
}: UseContentPageSearchStateOptions) {
  const [searchParams, setSearchParams] = useSearchParams();
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
    pathParts,
    breadcrumbPaths,
  } = readContentPageUrlState(searchParams, forcedViewMode);

  const [selectedFile, setSelectedFile] = useState<ContentItemInfo | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [isImmutable, setIsImmutable] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mkdirOpen, setMkdirOpen] = useState(false);
  const searchParamsString = searchParams.toString();
  const searchParamsStringRef = useRef(searchParamsString);

  useLayoutEffect(() => {
    searchParamsStringRef.current = searchParamsString;
  }, [searchParamsString]);

  const handleRefresh = useCallback(() => {
    void invalidateContentQueries();
    setRefreshKey((previous) => previous + 1);
  }, []);

  const updateSearchParams = useCallback(
    (
      updater: (next: URLSearchParams) => void,
      options?: {
        replace?: boolean;
      },
    ) => {
      const current = searchParamsStringRef.current;
      const next = new URLSearchParams(current);
      updater(next);
      const nextString = next.toString();
      if (nextString === current) {
        return;
      }
      searchParamsStringRef.current = nextString;
      setSearchParams(next, options);
    },
    [setSearchParams],
  );

  useEffect(() => {
    const params = new URLSearchParams(searchParamsString);
    if (params.get("upload") !== "true") {
      return;
    }
    const openTimer = window.setTimeout(() => setUploadOpen(true), 0);
    updateSearchParams((next) => next.delete("upload"), { replace: true });
    return () => window.clearTimeout(openTimer);
  }, [searchParamsString, updateSearchParams]);

  const clearSelectedFileSelection = useCallback(() => {
    updateSearchParams((next) => {
      next.delete("file");
    });
  }, [updateSearchParams]);

  const setBooleanSearchParam = useCallback(
    (key: string, enabled: boolean) => {
      updateSearchParams((next) => {
        if (enabled) {
          next.set(key, "true");
        } else {
          next.delete(key);
        }
      });
    },
    [updateSearchParams],
  );

  const setOptionalSearchParam = useCallback(
    (key: string, value: string, trimBeforeChecking = false) => {
      updateSearchParams((next) => {
        const normalizedValue = trimBeforeChecking ? value.trim() : value;
        if (normalizedValue) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
      });
    },
    [updateSearchParams],
  );

  useEffect(() => {
    return startContentPageSelectedFileLoad({
      selectedFilePath,
      currentSelectedFilePath: selectedFile?.path ?? null,
      getDetails: contentApi.getDetails,
      onSelectFile: setSelectedFile,
      onMissingFile: () => {
        notify(translate("custom.file_not_found"), { type: "error" });
        updateSearchParams(
          (next) => {
            next.delete("file");
          },
          { replace: true },
        );
      },
    });
  }, [notify, selectedFile?.path, selectedFilePath, translate, updateSearchParams]);

  const handleViewChange = useCallback(
    (value: string) => {
      if (forcedViewMode) {
        return;
      }

      updateSearchParams((next) => {
        applyContentPageViewModeChange(next, value, forcedViewMode);
      });
    },
    [forcedViewMode, updateSearchParams],
  );

  const handleNavigate = useCallback(
    (path: string) => {
      updateSearchParams((next) => {
        if (path) {
          next.set("path", path);
        } else {
          next.delete("path");
        }
        next.delete("file");
      });
    },
    [updateSearchParams],
  );

  const handleFileClick = useCallback(
    (file: ContentItemInfo) => {
      setSelectedFile(file);
      updateSearchParams((next) => {
        next.set("file", file.path);
      });
    },
    [updateSearchParams],
  );

  const handleDetailsOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        clearSelectedFileSelection();
      }
    },
    [clearSelectedFileSelection],
  );

  const handleAllFilesStaleOnlyChange = useCallback(
    (staleOnly: boolean) => {
      setBooleanSearchParam("stale_enrichment", staleOnly);
    },
    [setBooleanSearchParam],
  );

  const handleAllFilesStatusFilterChange = useCallback(
    (status: string) => {
      setOptionalSearchParam("status", status);
    },
    [setOptionalSearchParam],
  );

  const handleAllFilesDocumentClassFilterChange = useCallback(
    (documentClass: string) => {
      setOptionalSearchParam("document_class", documentClass);
    },
    [setOptionalSearchParam],
  );

  const handleAllFilesExtractionSchemaFilterChange = useCallback(
    (extractionSchema: string) => {
      setOptionalSearchParam("extraction_schema", extractionSchema);
    },
    [setOptionalSearchParam],
  );

  const handleAllFilesExtractionFieldFilterChange = useCallback(
    (extractionField: string) => {
      setOptionalSearchParam("extraction_field", extractionField);
    },
    [setOptionalSearchParam],
  );

  const handleAllFilesFieldFiltersChange = useCallback(
    (serialized: string) => {
      setOptionalSearchParam("field_filters", serialized);
    },
    [setOptionalSearchParam],
  );

  const handleAllFilesReviewStatusFilterChange = useCallback(
    (reviewStatus: string) => {
      updateSearchParams((next) => {
        applyContentPageReviewStatusFilterChange(next, reviewStatus);
      });
    },
    [updateSearchParams],
  );

  const activeSelectedFile = selectedFile?.path === selectedFilePath ? selectedFile : null;

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
    selectedFile,
    setSelectedFile,
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
    handleViewChange,
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
  };
}
