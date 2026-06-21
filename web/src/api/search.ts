import { apiUrl, httpClient } from "./client.ts";
import type { ContentItemKind, SearchResult } from "./content.ts";

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export const searchApi = {
  search: async (
    query: string,
    options: {
      limit?: number;
      offset?: number;
      content_kind?: ContentItemKind;
      extension?: string;
      path_prefix?: string;
      score_threshold?: number;
    } = {},
  ): Promise<SearchResponse> => {
    const params = new URLSearchParams({ q: query });
    if (options.limit) params.set("limit", String(options.limit));
    if (options.offset) params.set("offset", String(options.offset));
    if (options.content_kind) params.set("content_kind", options.content_kind);
    if (options.extension) params.set("extension", options.extension);
    if (options.path_prefix) params.set("path_prefix", options.path_prefix);
    if (options.score_threshold !== undefined) {
      params.set("score_threshold", String(options.score_threshold));
    }

    const { json } = await httpClient(`${apiUrl}/query/?${params}`);
    return json;
  },
};
