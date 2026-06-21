const RECENT_SEARCH_QUERIES_KEY = "recent-search-queries";
const RECENT_SEARCH_QUERIES_EVENT = "app:recent-search-queries-changed";

export function readRecentSearchQueries(limit = 8): string[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(RECENT_SEARCH_QUERIES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string").slice(0, limit)
      : [];
  } catch {
    return [];
  }
}

export function recordRecentSearchQuery(query: string) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery || typeof window === "undefined") {
    return;
  }
  const nextQueries = [
    normalizedQuery,
    ...readRecentSearchQueries(12).filter(
      (item) => item.toLocaleLowerCase() !== normalizedQuery.toLocaleLowerCase(),
    ),
  ].slice(0, 12);
  window.localStorage.setItem(RECENT_SEARCH_QUERIES_KEY, JSON.stringify(nextQueries));
  window.dispatchEvent(new Event(RECENT_SEARCH_QUERIES_EVENT));
}

export function subscribeRecentSearchQueries(listener: () => void) {
  window.addEventListener(RECENT_SEARCH_QUERIES_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(RECENT_SEARCH_QUERIES_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
