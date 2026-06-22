import { useQuery } from "@tanstack/react-query";

import {
  contentApi,
  searchApi,
  type AllFilesBatchFilters,
  type ContentItemInfo,
  type DocumentClassFacet,
  type ExtractionFieldFacet,
  type ExtractionSchemaFacet,
  type ExtractionSchemaFieldFacet,
  type ExtractionValueFacet,
} from "@/dataProvider";
import { groupSearchResults } from "@/lib/search-results";

/** Per-row semantic match metadata overlaid on hydrated content rows. */
export interface ContentSearchMeta {
  /** Best chunk similarity score for the file (0–1). */
  score: number;
  /** Best matching snippet text, if any. */
  snippet: string;
  /** Doc refs of the best chunk, for in-document highlighting. */
  docRefs: string[];
}

interface SemanticListingState {
  files: ContentItemInfo[];
  searchMeta: Map<string, ContentSearchMeta>;
  documentClassFacets: DocumentClassFacet[];
  extractionSchemaFacets: ExtractionSchemaFacet[];
  extractionSchemaFieldFacets: ExtractionSchemaFieldFacet[];
  extractionFieldFacets: ExtractionFieldFacet[];
  extractionValueFacets: ExtractionValueFacet[];
  total: number;
}

const EMPTY_STATE: SemanticListingState = {
  files: [],
  searchMeta: new Map(),
  documentClassFacets: [],
  extractionSchemaFacets: [],
  extractionSchemaFieldFacets: [],
  extractionFieldFacets: [],
  extractionValueFacets: [],
  total: 0,
};

// Candidate set fetched from the vector index before structural filters narrow it.
const SEMANTIC_CANDIDATE_LIMIT = 50;
const SEMANTIC_SCORE_THRESHOLD = 0.2;

interface UseContentListSemanticListingOptions {
  /** Natural-language query; an empty query yields an empty result set. */
  query: string;
  /** Structural filters applied on top of the semantic hits (excludes `name`). */
  filters: AllFilesBatchFilters;
  enabled: boolean;
  refreshKey?: number;
}

export function useContentListSemanticListing({
  query,
  filters,
  enabled,
  refreshKey,
}: UseContentListSemanticListingOptions) {
  const trimmedQuery = query.trim();

  const result = useQuery({
    queryKey: ["content", "semantic-list", trimmedQuery, filters, refreshKey ?? 0],
    enabled: enabled && trimmedQuery.length > 0,
    queryFn: async (): Promise<SemanticListingState> => {
      const search = await searchApi.search(trimmedQuery, {
        limit: SEMANTIC_CANDIDATE_LIMIT,
        score_threshold: SEMANTIC_SCORE_THRESHOLD,
      });

      // One row per file, ordered by relevance, best chunk kept per file.
      const groups = groupSearchResults(search.results);
      const searchMeta = new Map<string, ContentSearchMeta>();
      const orderedIds: string[] = [];
      for (const group of groups) {
        const id = group.bestResult.content_item_id;
        if (!id) {
          continue;
        }
        orderedIds.push(id);
        searchMeta.set(id, {
          score: group.bestResult.score,
          snippet: group.bestResult.text ?? "",
          docRefs: group.bestResult.doc_refs,
        });
      }

      if (orderedIds.length === 0) {
        return EMPTY_STATE;
      }

      // Hydrate the ranked ids into full content rows, applying structural
      // filters on top. The returned set may be a subset (filtered out) and is
      // re-sorted client-side into relevance order.
      const listing = await contentApi.listAll({
        ...filters,
        ids: orderedIds,
        limit: orderedIds.length,
      });
      const rank = new Map(orderedIds.map((id, index) => [id, index]));
      const files = [...listing.files].sort(
        (left, right) =>
          (rank.get(left.id) ?? Number.POSITIVE_INFINITY) -
          (rank.get(right.id) ?? Number.POSITIVE_INFINITY),
      );

      return {
        files,
        searchMeta,
        documentClassFacets: listing.document_class_facets ?? [],
        extractionSchemaFacets: listing.extraction_schema_facets ?? [],
        extractionSchemaFieldFacets: listing.extraction_schema_field_facets ?? [],
        extractionFieldFacets: listing.extraction_field_facets ?? [],
        extractionValueFacets: listing.extraction_value_facets ?? [],
        total: files.length,
      };
    },
  });

  return {
    ...(result.data ?? EMPTY_STATE),
    isLoading: result.isLoading && result.fetchStatus !== "idle",
  };
}
