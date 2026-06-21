import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  FileText,
  Folder,
  FolderPlus,
  List,
  Loader2,
  Plus,
  Search,
} from "lucide-react";
import { useNotify } from "@/lib/app-context";
import {
  contentApi,
  searchApi,
  type ContentItemInfo,
  type FolderInfo,
  type SearchResult,
} from "@/dataProvider";
import { reportClientError } from "@/lib/report-client-error";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ContentItemStatusBadge } from "@/components/content-item-details/ContentItemStatusBadge";
import { ContentItemDetailsDialog } from "@/components/ContentItemDetailsDialog";
import { Input } from "@/components/ui/input";

const MAX_FOLDER_FILES = 300;
const ALL_FILES_PAGE_SIZE = 50;

type PickerItem = { type: "folder"; value: FolderInfo } | { type: "file"; value: ContentItemInfo };

interface ChatContextPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAddPaths: (paths: string[]) => void;
  translate: (key: string, options?: unknown) => string;
}

const getParentPath = (path: string): string => {
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 1) return "";
  return parts.slice(0, -1).join("/");
};

const formatPathName = (path: string): string => path.split("/").filter(Boolean).pop() || path;

export const ChatContextPickerDialog = ({
  open,
  onOpenChange,
  onAddPaths,
  translate,
}: ChatContextPickerDialogProps) => {
  const notify = useNotify();

  // Browse tab state
  const [currentPath, setCurrentPath] = useState("");
  const [folders, setFolders] = useState<FolderInfo[]>([]);
  const [files, setFiles] = useState<ContentItemInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isAddingFolder, setIsAddingFolder] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Search tab state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // All files tab state
  const [allFiles, setAllFiles] = useState<ContentItemInfo[]>([]);
  const [allFilesTotal, setAllFilesTotal] = useState(0);
  const [allFilesHasMore, setAllFilesHasMore] = useState(false);
  const [allFilesLoading, setAllFilesLoading] = useState(false);
  const [allFilesLoadingMore, setAllFilesLoadingMore] = useState(false);
  const [allFilesFilter, setAllFilesFilter] = useState("");
  const [allFilesDebouncedFilter, setAllFilesDebouncedFilter] = useState("");
  const allFilesSentinelRef = useRef<HTMLDivElement>(null);

  // Details dialog state
  const [detailsFile, setDetailsFile] = useState<ContentItemInfo | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [loadingDetailsPath, setLoadingDetailsPath] = useState<string | null>(null);

  // Tab state
  const [activeTab, setActiveTab] = useState("browse");

  const breadcrumbPaths = useMemo(() => {
    const parts = currentPath.split("/").filter(Boolean);
    return parts.map((_, index) => parts.slice(0, index + 1).join("/"));
  }, [currentPath]);

  const loadDirectory = useCallback(
    async (path: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await contentApi.listDirectory(path);
        setFolders(response.folders);
        setFiles(response.files);
      } catch (loadError) {
        reportClientError(loadError, undefined, { routeName: "chat:context-picker:list" });
        setError(translate("custom.pages.chat.context.picker.load_failed"));
        setFolders([]);
        setFiles([]);
      } finally {
        setIsLoading(false);
      }
    },
    [translate],
  );

  useEffect(() => {
    if (!open) return;
    setCurrentPath("");
    setSearchQuery("");
    setSearchResults([]);
    setSearchError(null);
    setHasSearched(false);
    setAllFiles([]);
    setAllFilesFilter("");
    setAllFilesDebouncedFilter("");
    setActiveTab("browse");
    void loadDirectory("");
  }, [open, loadDirectory]);

  useEffect(() => {
    if (!open) return;
    void loadDirectory(currentPath);
  }, [currentPath, open, loadDirectory]);

  // Debounced search
  useEffect(() => {
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }

    if (!searchQuery.trim()) {
      setSearchResults([]);
      setSearchError(null);
      setHasSearched(false);
      return;
    }

    searchTimerRef.current = setTimeout(async () => {
      setIsSearching(true);
      setSearchError(null);
      try {
        const response = await searchApi.search(searchQuery.trim(), { limit: 20 });
        // Deduplicate by file_path
        const seen = new Set<string>();
        const deduped: SearchResult[] = [];
        for (const result of response.results) {
          if (!seen.has(result.file_path)) {
            seen.add(result.file_path);
            deduped.push(result);
          }
        }
        setSearchResults(deduped);
        setHasSearched(true);
      } catch (err) {
        reportClientError(err, undefined, { routeName: "chat:context-picker:search" });
        setSearchError(translate("custom.pages.chat.context.picker.search_error"));
        setSearchResults([]);
        setHasSearched(true);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
    };
  }, [searchQuery, translate]);

  // Debounce content-list name filter
  useEffect(() => {
    const timer = setTimeout(() => setAllFilesDebouncedFilter(allFilesFilter), 300);
    return () => clearTimeout(timer);
  }, [allFilesFilter]);

  // Fetch all files when tab is active
  useEffect(() => {
    if (activeTab !== "all" || !open) return;
    let cancelled = false;

    const fetchData = async () => {
      setAllFilesLoading(true);
      try {
        const res = await contentApi.listAll({
          limit: ALL_FILES_PAGE_SIZE,
          offset: 0,
          name: allFilesDebouncedFilter || undefined,
          status: "COMPLETED",
        });
        if (cancelled) return;
        setAllFiles(res.files);
        setAllFilesTotal(res.total);
        setAllFilesHasMore(res.has_more);
      } catch {
        if (cancelled) return;
        setAllFiles([]);
        setAllFilesTotal(0);
        setAllFilesHasMore(false);
      } finally {
        if (!cancelled) setAllFilesLoading(false);
      }
    };

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [activeTab, open, allFilesDebouncedFilter]);

  // Load more content-list items (infinite scroll)
  const loadMoreAllFiles = useCallback(() => {
    if (allFilesLoading || allFilesLoadingMore || !allFilesHasMore) return;
    setAllFilesLoadingMore(true);

    contentApi
      .listAll({
        limit: ALL_FILES_PAGE_SIZE,
        offset: allFiles.length,
        name: allFilesDebouncedFilter || undefined,
        status: "COMPLETED",
      })
      .then((res) => {
        setAllFiles((prev) => [...prev, ...res.files]);
        setAllFilesHasMore(res.has_more);
        setAllFilesTotal(res.total);
      })
      .finally(() => setAllFilesLoadingMore(false));
  }, [
    allFilesLoading,
    allFilesLoadingMore,
    allFilesHasMore,
    allFiles.length,
    allFilesDebouncedFilter,
  ]);

  // IntersectionObserver for content-list infinite scroll
  useEffect(() => {
    const sentinel = allFilesSentinelRef.current;
    if (!sentinel || activeTab !== "all") return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMoreAllFiles();
      },
      { rootMargin: "200px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMoreAllFiles, activeTab]);

  const handleAddFile = useCallback(
    (filePath: string) => {
      onAddPaths([filePath]);
    },
    [onAddPaths],
  );

  const collectFolderFiles = useCallback(async (folderPath: string) => {
    const queue: string[] = [folderPath];
    const collected: string[] = [];

    while (queue.length > 0 && collected.length < MAX_FOLDER_FILES) {
      const path = queue.shift();
      if (!path) continue;
      const response = await contentApi.listDirectory(path);

      for (const file of response.files) {
        if (collected.length >= MAX_FOLDER_FILES) break;
        collected.push(file.path);
      }

      for (const folder of response.folders) {
        queue.push(folder.path);
      }
    }

    return {
      paths: collected,
      truncated: queue.length > 0,
    };
  }, []);

  const handleAddFolder = useCallback(
    async (folderPath: string) => {
      setIsAddingFolder(folderPath);
      try {
        const result = await collectFolderFiles(folderPath);
        if (result.paths.length === 0) {
          notify(translate("custom.pages.chat.context.picker.empty_folder"), {
            type: "warning",
          });
          return;
        }

        onAddPaths(result.paths);
        if (result.truncated) {
          notify(
            translate("custom.pages.chat.context.picker.folder_truncated", {
              count: MAX_FOLDER_FILES,
            }),
            { type: "warning" },
          );
        }
      } catch (addError) {
        reportClientError(addError, undefined, { routeName: "chat:context-picker:add-folder" });
        notify(translate("custom.pages.chat.context.picker.add_folder_failed"), {
          type: "error",
        });
      } finally {
        setIsAddingFolder(null);
      }
    },
    [collectFolderFiles, notify, onAddPaths, translate],
  );

  const handleOpenDetails = useCallback(
    async (filePath: string) => {
      setLoadingDetailsPath(filePath);
      try {
        const fileInfo = await contentApi.getDetails(filePath);
        setDetailsFile(fileInfo);
        setDetailsOpen(true);
      } catch (err) {
        reportClientError(err, undefined, { routeName: "chat:context-picker:details" });
        notify(translate("custom.pages.search.failed_to_load_details"), { type: "error" });
      } finally {
        setLoadingDetailsPath(null);
      }
    },
    [notify, translate],
  );

  const isFileIndexed = (file: ContentItemInfo) => file.status === "COMPLETED";

  const items: PickerItem[] = [
    ...folders.map((folder) => ({ type: "folder" as const, value: folder })),
    ...files.map((file) => ({ type: "file" as const, value: file })),
  ];

  const renderFileRow = (file: ContentItemInfo) => {
    const indexed = isFileIndexed(file);
    const loading = loadingDetailsPath === file.path;

    return (
      <div
        key={file.path}
        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md border border-transparent px-2 py-1 hover:border-border hover:bg-muted/40"
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span
            className={`min-w-0 truncate text-sm ${!indexed ? "text-muted-foreground" : ""}`}
            title={file.path}
          >
            {file.name}
          </span>
          {file.status && (
            <span className="shrink-0">
              <ContentItemStatusBadge status={file.status} />
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => handleOpenDetails(file.path)}
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Eye className="h-3.5 w-3.5" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{translate("custom.pages.chat.context.picker.details")}</TooltipContent>
          </Tooltip>
          {indexed ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => handleAddFile(file.path)}
              className="shrink-0"
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              {translate("custom.pages.chat.context.picker.add_file")}
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button type="button" variant="outline" size="sm" className="shrink-0" disabled>
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    {translate("custom.pages.chat.context.picker.add_file")}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {translate("custom.pages.chat.context.picker.not_indexed")}
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>
    );
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.chat.context.picker.title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.chat.context.picker.description")}
            </DialogDescription>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-3 mb-3">
              <TabsTrigger value="browse">
                <Folder className="mr-1.5 h-3.5 w-3.5" />
                {translate("custom.pages.chat.context.picker.tab_browse")}
              </TabsTrigger>
              <TabsTrigger value="all">
                <List className="mr-1.5 h-3.5 w-3.5" />
                {translate("custom.pages.chat.context.picker.tab_all")}
              </TabsTrigger>
              <TabsTrigger value="search">
                <Search className="mr-1.5 h-3.5 w-3.5" />
                {translate("custom.pages.chat.context.picker.tab_search")}
              </TabsTrigger>
            </TabsList>

            {/* Browse Tab */}
            <TabsContent value="browse" className="mt-0">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!currentPath}
                    onClick={() => setCurrentPath(getParentPath(currentPath))}
                  >
                    <ChevronLeft className="mr-1.5 h-3.5 w-3.5" />
                    {translate("custom.pages.chat.context.picker.back")}
                  </Button>
                  <div className="flex min-w-0 flex-wrap items-center gap-1 text-xs text-muted-foreground">
                    <button
                      type="button"
                      className="rounded px-1.5 py-0.5 hover:bg-muted"
                      onClick={() => setCurrentPath("")}
                    >
                      {translate("custom.pages.chat.context.picker.root")}
                    </button>
                    {breadcrumbPaths.map((path) => (
                      <span key={path} className="inline-flex items-center gap-1">
                        <ChevronRight className="h-3 w-3" />
                        <button
                          type="button"
                          className="rounded px-1.5 py-0.5 hover:bg-muted"
                          onClick={() => setCurrentPath(path)}
                        >
                          {formatPathName(path)}
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                <div className="rounded-md border">
                  <ScrollArea className="h-[360px]">
                    <div className="p-2">
                      {isLoading && (
                        <div className="space-y-2">
                          {Array.from({ length: 8 }).map((_, index) => (
                            <Skeleton key={index} className="h-9 w-full" />
                          ))}
                        </div>
                      )}

                      {!isLoading && error && (
                        <p className="px-2 py-6 text-sm text-destructive">{error}</p>
                      )}

                      {!isLoading && !error && items.length === 0 && (
                        <p className="px-2 py-6 text-sm text-muted-foreground">
                          {translate("custom.pages.chat.context.picker.empty_directory")}
                        </p>
                      )}

                      {!isLoading && !error && items.length > 0 && (
                        <div className="space-y-1">
                          {items.map((item) => {
                            if (item.type === "folder") {
                              const folder = item.value;
                              const adding = isAddingFolder === folder.path;
                              return (
                                <div
                                  key={folder.path}
                                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md border border-transparent px-2 py-1 hover:border-border hover:bg-muted/40"
                                >
                                  <button
                                    type="button"
                                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                                    onClick={() => setCurrentPath(folder.path)}
                                  >
                                    <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
                                    <span className="min-w-0 truncate text-sm" title={folder.path}>
                                      {folder.name}
                                    </span>
                                  </button>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="shrink-0"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      void handleAddFolder(folder.path);
                                    }}
                                    disabled={adding}
                                  >
                                    {adding ? (
                                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <FolderPlus className="mr-1.5 h-3.5 w-3.5" />
                                    )}
                                    {translate("custom.pages.chat.context.picker.add_folder")}
                                  </Button>
                                </div>
                              );
                            }

                            return renderFileRow(item.value);
                          })}
                        </div>
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </TabsContent>

            {/* All Files Tab */}
            <TabsContent value="all" className="mt-0">
              <div className="space-y-3">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder={translate("custom.pages.chat.context.picker.all_name_filter")}
                    value={allFilesFilter}
                    onChange={(e) => setAllFilesFilter(e.target.value)}
                    className="pl-9"
                  />
                </div>

                <div className="rounded-md border">
                  <ScrollArea className="h-[360px]">
                    <div className="p-2">
                      {allFilesLoading && (
                        <div className="space-y-2">
                          {Array.from({ length: 8 }).map((_, index) => (
                            <Skeleton key={index} className="h-9 w-full" />
                          ))}
                        </div>
                      )}

                      {!allFilesLoading && allFiles.length === 0 && (
                        <p className="px-2 py-6 text-sm text-muted-foreground text-center">
                          {translate("custom.pages.chat.context.picker.all_no_files")}
                        </p>
                      )}

                      {!allFilesLoading && allFiles.length > 0 && (
                        <div className="space-y-1">
                          {allFiles.map((file) => {
                            const loading = loadingDetailsPath === file.path;
                            const folderPath = file.path.split("/").slice(0, -1).join("/");

                            return (
                              <div
                                key={file.path}
                                className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-2 rounded-md border border-transparent px-2 py-1.5 hover:border-border hover:bg-muted/40"
                              >
                                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                                <div className="flex-1 min-w-0">
                                  <span
                                    className="block min-w-0 truncate text-sm"
                                    title={file.path}
                                  >
                                    {file.name}
                                  </span>
                                  {folderPath && (
                                    <p className="min-w-0 truncate text-xs text-muted-foreground">
                                      {folderPath}
                                    </p>
                                  )}
                                </div>
                                <div className="flex items-center gap-1 shrink-0">
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7"
                                        onClick={() => handleOpenDetails(file.path)}
                                        disabled={loading}
                                      >
                                        {loading ? (
                                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                        ) : (
                                          <Eye className="h-3.5 w-3.5" />
                                        )}
                                      </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                      {translate("custom.pages.chat.context.picker.details")}
                                    </TooltipContent>
                                  </Tooltip>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="shrink-0"
                                    onClick={() => handleAddFile(file.path)}
                                  >
                                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                                    {translate("custom.pages.chat.context.picker.add_file")}
                                  </Button>
                                </div>
                              </div>
                            );
                          })}

                          <div ref={allFilesSentinelRef} className="h-1" />
                          {allFilesLoadingMore && (
                            <div className="flex justify-center py-2">
                              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                              <span className="ml-2 text-xs text-muted-foreground">
                                {translate("custom.pages.chat.context.picker.all_loading_more")}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {!allFilesLoading && allFiles.length > 0 && (
                        <p className="text-xs text-muted-foreground text-center mt-2">
                          {allFiles.length} / {allFilesTotal}
                        </p>
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </TabsContent>

            {/* Search Tab */}
            <TabsContent value="search" className="mt-0">
              <div className="space-y-3">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder={translate("custom.pages.chat.context.picker.search_placeholder")}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>

                <div className="rounded-md border">
                  <ScrollArea className="h-[360px]">
                    <div className="p-2">
                      {isSearching && (
                        <div className="space-y-2">
                          {Array.from({ length: 5 }).map((_, index) => (
                            <Skeleton key={index} className="h-16 w-full" />
                          ))}
                        </div>
                      )}

                      {!isSearching && searchError && (
                        <p className="px-2 py-6 text-sm text-destructive">{searchError}</p>
                      )}

                      {!isSearching &&
                        !searchError &&
                        hasSearched &&
                        searchResults.length === 0 && (
                          <p className="px-2 py-6 text-sm text-muted-foreground">
                            {translate("custom.pages.chat.context.picker.search_no_results")}
                          </p>
                        )}

                      {!isSearching && !searchError && !hasSearched && (
                        <p className="px-2 py-6 text-sm text-muted-foreground text-center">
                          {translate("custom.pages.chat.context.picker.search_placeholder")}
                        </p>
                      )}

                      {!isSearching && !searchError && searchResults.length > 0 && (
                        <div className="space-y-1">
                          {searchResults.map((result) => {
                            const fileName = result.file_path.split("/").pop() || result.file_path;
                            const folderPath = result.file_path.split("/").slice(0, -1).join("/");
                            const loading = loadingDetailsPath === result.file_path;

                            return (
                              <div
                                key={result.file_path}
                                className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-2 rounded-md border border-transparent px-2 py-1.5 hover:border-border hover:bg-muted/40"
                              >
                                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                                <div className="flex-1 min-w-0">
                                  <div className="flex min-w-0 items-center gap-2">
                                    <span
                                      className="min-w-0 truncate text-sm font-medium"
                                      title={result.file_path}
                                    >
                                      {fileName}
                                    </span>
                                    <Badge score={result.score} />
                                  </div>
                                  {folderPath && (
                                    <p className="min-w-0 truncate text-xs text-muted-foreground">
                                      {folderPath}
                                    </p>
                                  )}
                                  {result.text && (
                                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                                      {result.text}
                                    </p>
                                  )}
                                </div>
                                <div className="flex items-center gap-1 shrink-0">
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7"
                                        onClick={() => handleOpenDetails(result.file_path)}
                                        disabled={loading}
                                      >
                                        {loading ? (
                                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                        ) : (
                                          <Eye className="h-3.5 w-3.5" />
                                        )}
                                      </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                      {translate("custom.pages.chat.context.picker.details")}
                                    </TooltipContent>
                                  </Tooltip>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="shrink-0"
                                    onClick={() => handleAddFile(result.file_path)}
                                  >
                                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                                    {translate("custom.pages.chat.context.picker.add_file")}
                                  </Button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      <ContentItemDetailsDialog
        file={detailsFile}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
      />
    </>
  );
};

const Badge = ({ score }: { score: number }) => (
  <span className="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
    {Math.round(score * 100)}%
  </span>
);
