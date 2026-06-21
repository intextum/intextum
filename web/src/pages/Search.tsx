/**
 * Semantic search page.
 */
import { useState, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router";
import { useNotify, useTranslate } from "@/lib/app-context";
import {
  Search,
  FileText,
  X,
  Sparkles,
  File,
  Image,
  Film,
  Filter,
  Mail,
  Paperclip,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/page/EmptyState";
import { LoadingState } from "@/components/page/LoadingState";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import { PageToolbar } from "@/components/page/PageToolbar";
import {
  searchApi,
  contentApi,
  type SearchResponse,
  type SearchResult,
  type ContentItemInfo,
} from "@/dataProvider";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import { ContentItemDetailsDialog } from "@/components/ContentItemDetailsDialog";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { reportClientError } from "@/lib/report-client-error";
import { recordRecentSearchQuery } from "@/lib/recent-searches";
import { groupSearchResults } from "@/lib/search-results";

export const SearchPage = () => {
  const notify = useNotify();
  const translate = useTranslate();
  const [searchParams] = useSearchParams();
  useDocumentTitle(translate("custom.pages.search.title"));

  const FILE_TYPES = [
    { value: "all", label: translate("custom.pages.search.extensions.all"), icon: File },
    { value: ".pdf", label: translate("custom.pages.search.extensions.pdf"), icon: FileText },
    { value: ".docx", label: translate("custom.pages.search.extensions.docx"), icon: FileText },
    { value: ".txt", label: translate("custom.pages.search.extensions.txt"), icon: FileText },
    { value: ".md", label: translate("custom.pages.search.extensions.md"), icon: FileText },
    { value: ".png", label: translate("custom.pages.search.extensions.png"), icon: Image },
    { value: ".jpg", label: translate("custom.pages.search.extensions.jpg"), icon: Image },
    { value: ".mp4", label: translate("custom.pages.search.extensions.mp4"), icon: Film },
  ];
  const CONTENT_KINDS = [
    { value: "all", label: translate("custom.pages.search.content_kinds.all"), icon: Filter },
    { value: "file", label: translate("custom.pages.search.content_kinds.file"), icon: FileText },
    {
      value: "email_message",
      label: translate("custom.pages.search.content_kinds.email_message"),
      icon: Mail,
    },
    {
      value: "attachment",
      label: translate("custom.pages.search.content_kinds.attachment"),
      icon: Paperclip,
    },
  ] as const;

  const [query, setQuery] = useState("");
  const [contentKind, setContentKind] = useState("all");
  const [fileType, setFileType] = useState("all");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const DEFAULT_SCORE_THRESHOLD = 0.2;
  const groupedResults = useMemo(
    () => (response ? groupSearchResults(response.results) : []),
    [response],
  );

  // Preview state
  const [selectedFile, setSelectedFile] = useState<ContentItemInfo | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [highlightRefs, setHighlightRefs] = useState<string[] | undefined>(undefined);

  const runSearch = useCallback(
    async (rawQuery: string) => {
      const trimmedQuery = rawQuery.trim();
      if (!trimmedQuery) {
        notify(translate("custom.pages.search.enter_query"), { type: "warning" });
        return;
      }

      setQuery(trimmedQuery);
      recordRecentSearchQuery(trimmedQuery);
      setIsLoading(true);
      try {
        const data = await searchApi.search(trimmedQuery, {
          limit: 20,
          content_kind:
            contentKind !== "all"
              ? (contentKind as "file" | "email_message" | "attachment")
              : undefined,
          extension: fileType !== "all" ? fileType : undefined,
          score_threshold: DEFAULT_SCORE_THRESHOLD,
        });
        setResponse(data);
      } catch (error) {
        reportClientError(error, undefined, { routeName: "search:query" });
        notify(translate("custom.pages.search.search_failed"), { type: "error" });
      } finally {
        setIsLoading(false);
      }
    },
    [contentKind, fileType, notify, translate],
  );

  const handleSearch = useCallback(async () => {
    if (!query.trim()) {
      notify(translate("custom.pages.search.enter_query"), { type: "warning" });
      return;
    }

    await runSearch(query);
  }, [notify, query, runSearch, translate]);

  useEffect(() => {
    const queryParam = searchParams.get("q")?.trim() ?? "";
    if (!queryParam || response?.query === queryParam) {
      return;
    }
    const searchTimer = window.setTimeout(() => {
      void runSearch(queryParam);
    }, 0);
    return () => window.clearTimeout(searchTimer);
  }, [response?.query, runSearch, searchParams]);

  const handleClear = useCallback(() => {
    setQuery("");
    setResponse(null);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        void handleSearch();
      }
    },
    [handleSearch],
  );

  const handleResultClick = useCallback(
    async (result: SearchResult) => {
      try {
        // Fetch full content details to open the dialog
        const fileInfo = await contentApi.getDetails(result.file_path);
        setSelectedFile(fileInfo);
        setHighlightRefs(result.doc_refs);
        setDetailsOpen(true);
      } catch (error) {
        reportClientError(error, undefined, { routeName: "search:open-details" });
        notify(translate("custom.pages.search.failed_to_load_details"), { type: "error" });
      }
    },
    [notify, translate],
  );

  return (
    <PageShell>
      <PageHeader
        icon={Sparkles}
        title={translate("custom.pages.search.title")}
        description={translate("custom.pages.search.ready_desc")}
      />

      <PageToolbar className="items-stretch md:items-center">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            data-shortcut-search="true"
            placeholder={translate("custom.pages.search.placeholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="bg-background pl-9 pr-9"
          />
          {query && (
            <Button
              variant="ghost"
              size="sm"
              className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0"
              onClick={handleClear}
              aria-label={translate("ra.action.clear_input_value")}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Select value={contentKind} onValueChange={setContentKind}>
            <SelectTrigger className="bg-background sm:w-[190px]">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Filter className="h-3.5 w-3.5" />
                <SelectValue />
              </div>
            </SelectTrigger>
            <SelectContent>
              {CONTENT_KINDS.map((kind) => (
                <SelectItem key={kind.value} value={kind.value}>
                  <div className="flex items-center gap-2">
                    <kind.icon className="h-3.5 w-3.5" />
                    {kind.label}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={fileType} onValueChange={setFileType}>
            <SelectTrigger className="bg-background sm:w-[150px]">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Filter className="h-3.5 w-3.5" />
                <SelectValue />
              </div>
            </SelectTrigger>
            <SelectContent>
              {FILE_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  <div className="flex items-center gap-2">
                    <type.icon className="h-3.5 w-3.5" />
                    {type.label}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button onClick={() => void handleSearch()} disabled={isLoading}>
            <Search className="mr-2 h-4 w-4" />
            {translate("custom.search")}
          </Button>
        </div>
      </PageToolbar>

      <div>
        {isLoading && <LoadingState rows={3} className="max-w-5xl" />}

        {!isLoading && response && (
          <div className="space-y-6 max-w-5xl">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                {translate("custom.pages.search.results_found", {
                  total: response.has_more ? `${response.total}+` : response.total,
                  plural: response.total !== 1 ? "s" : "",
                  query: response.query,
                })}
              </p>
            </div>

            <Separator />

            {response.results.length === 0 ? (
              <EmptyState
                icon={Search}
                title={translate("custom.pages.search.no_results")}
                description={translate("custom.pages.search.no_results_desc")}
              />
            ) : (
              <div className="space-y-4">
                {groupedResults.map((group, idx) => (
                  <SearchResultCard
                    key={group.id}
                    result={group.bestResult}
                    matches={group.results}
                    query={response.query}
                    rank={idx + 1}
                    onClick={handleResultClick}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {!isLoading && !response && (
          <EmptyState
            icon={Search}
            title={translate("custom.pages.search.ready")}
            description={translate("custom.pages.search.ready_desc")}
            className="py-20"
          />
        )}
      </div>

      <ContentItemDetailsDialog
        file={selectedFile}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        initialHighlightRefs={highlightRefs}
      />
    </PageShell>
  );
};
