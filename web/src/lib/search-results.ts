import type { SearchResult } from "@/dataProvider";

export interface SearchResultGroup {
  id: string;
  bestResult: SearchResult;
  results: SearchResult[];
}

export interface HighlightedTextSegment {
  text: string;
  highlighted: boolean;
}

const MAX_HIGHLIGHT_TERMS = 8;

function uniqueValues<T>(values: T[]): T[] {
  const seen = new Set<T>();
  return values.filter((value) => {
    if (seen.has(value)) {
      return false;
    }
    seen.add(value);
    return true;
  });
}

function groupKey(result: SearchResult): string {
  return result.content_item_id || result.file_path;
}

export function groupSearchResults(results: SearchResult[]): SearchResultGroup[] {
  const groups = new Map<string, SearchResultGroup>();

  for (const result of results) {
    const key = groupKey(result);
    const current = groups.get(key);
    if (!current) {
      groups.set(key, {
        id: key,
        bestResult: result,
        results: [result],
      });
      continue;
    }

    current.results.push(result);
    if (result.score > current.bestResult.score) {
      current.bestResult = result;
    }
  }

  return [...groups.values()];
}

export function combineSearchResults(results: SearchResult[]): SearchResult {
  const bestResult = results.reduce((best, result) => (result.score > best.score ? result : best));

  return {
    ...bestResult,
    page_numbers: uniqueValues(results.flatMap((result) => result.page_numbers)).sort(
      (left, right) => left - right,
    ),
    headings: uniqueValues(results.flatMap((result) => result.headings)),
    images: uniqueValues(results.flatMap((result) => result.images)),
    doc_refs: uniqueValues(results.flatMap((result) => result.doc_refs)),
  };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function extractSearchTerms(query: string): string[] {
  return uniqueValues(
    query
      .split(/\s+/)
      .map((term) => term.replace(/^["'([{]+|["')}\],.:;!?]+$/g, "").trim())
      .filter((term) => term.length > 1)
      .map((term) => term.toLocaleLowerCase()),
  ).slice(0, MAX_HIGHLIGHT_TERMS);
}

export function buildHighlightedTextSegments(
  text: string,
  query: string,
): HighlightedTextSegment[] {
  const terms = extractSearchTerms(query);
  if (!text || terms.length === 0) {
    return [{ text, highlighted: false }];
  }

  const matcher = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  const segments: HighlightedTextSegment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(matcher)) {
    const matchText = match[0];
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push({ text: text.slice(lastIndex, index), highlighted: false });
    }
    segments.push({ text: matchText, highlighted: true });
    lastIndex = index + matchText.length;
  }

  if (lastIndex < text.length) {
    segments.push({ text: text.slice(lastIndex), highlighted: false });
  }

  return segments.length > 0 ? segments : [{ text, highlighted: false }];
}
