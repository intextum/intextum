import { useCallback, useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";

import {
  contentApi,
  type DocumentClassFacet,
  type ExtractionSchemaFacet,
  type ExtractionSchemaFieldFacet,
  type ExtractionFieldFacet,
  type ExtractionValueFacet,
  type ContentItemInfo,
  type ReviewQueueSummary,
  type ReviewReasonFacet,
} from "@/dataProvider";
import { queryKeys } from "@/lib/query-client";

const DEFAULT_PAGE_SIZE = 50;

interface UseAllFilesListingOptions {
  fetchParams: Parameters<typeof contentApi.listAll>[0];
  refreshKey?: number;
  pageSize?: number;
}

interface FlatFileListingState {
  files: ContentItemInfo[];
  documentClassFacets: DocumentClassFacet[];
  extractionSchemaFacets: ExtractionSchemaFacet[];
  extractionSchemaFieldFacets: ExtractionSchemaFieldFacet[];
  extractionFieldFacets: ExtractionFieldFacet[];
  extractionValueFacets: ExtractionValueFacet[];
  reviewReasonFacets: ReviewReasonFacet[];
  reviewSummary: ReviewQueueSummary | null;
  total: number;
  hasMore: boolean;
}

const EMPTY_LISTING_STATE: FlatFileListingState = {
  files: [],
  documentClassFacets: [],
  extractionSchemaFacets: [],
  extractionSchemaFieldFacets: [],
  extractionFieldFacets: [],
  extractionValueFacets: [],
  reviewReasonFacets: [],
  reviewSummary: null,
  total: 0,
  hasMore: false,
};

function toListingState(
  response: Awaited<ReturnType<typeof contentApi.listAll>>,
): FlatFileListingState {
  return {
    files: response.files,
    documentClassFacets: response.document_class_facets ?? [],
    extractionSchemaFacets: response.extraction_schema_facets ?? [],
    extractionSchemaFieldFacets: response.extraction_schema_field_facets ?? [],
    extractionFieldFacets: response.extraction_field_facets ?? [],
    extractionValueFacets: response.extraction_value_facets ?? [],
    reviewReasonFacets: response.review_reason_facets ?? [],
    reviewSummary: response.review_summary ?? null,
    total: response.total,
    hasMore: response.has_more,
  };
}

export function useContentListListing({
  fetchParams,
  refreshKey,
  pageSize = DEFAULT_PAGE_SIZE,
}: UseAllFilesListingOptions) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  const query = useInfiniteQuery({
    queryKey: [...queryKeys.content.listAll(fetchParams), pageSize, refreshKey ?? 0],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      contentApi.listAll({
        limit: pageSize,
        offset: pageParam,
        ...fetchParams,
      }),
    getNextPageParam: (lastPage, allPages) =>
      lastPage.has_more
        ? allPages.reduce((total, page) => total + page.files.length, 0)
        : undefined,
  });
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = query;

  const listingState = useMemo(() => {
    const pages = data?.pages;
    const firstPage = pages?.[0];
    if (!firstPage) {
      return EMPTY_LISTING_STATE;
    }
    const mergedFiles = pages.flatMap((page) => page.files);
    return {
      ...toListingState(firstPage),
      files: mergedFiles,
      hasMore: hasNextPage,
    };
  }, [data, hasNextPage]);

  const loadMore = useCallback(() => {
    if (isLoading || isFetchingNextPage || !hasNextPage) {
      return;
    }
    void fetchNextPage();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, isLoading]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadMore();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore]);

  return {
    ...listingState,
    isLoading: query.isLoading,
    isLoadingMore: query.isFetchingNextPage,
    sentinelRef,
  };
}
