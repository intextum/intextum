import type { ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  Ban,
  CheckCircle,
  ChevronRight,
  Clock,
  Folder,
  Loader2,
  Play,
  RotateCw,
  XCircle,
} from "lucide-react";
import { useTranslate } from "@/lib/app-context";

import { DocumentClassBadge } from "@/components/DocumentClassBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ContentItemInfo, FolderInfo } from "@/dataProvider";
import { buildContentListRowModel } from "@/lib/content-list-row";
import {
  formatDate,
  formatSize,
  getContentItemDisplayName,
  getContentItemIcon,
} from "@/lib/content-utils";
import { buildHighlightedTextSegments } from "@/lib/search-results";

import type { SortBy, SortOrder } from "./types";
import type { ContentSearchMeta } from "./useContentListSemanticListing";

function RelevanceBadge({ score }: { score: number }) {
  return (
    <Badge
      variant="outline"
      className="shrink-0 border-primary/30 bg-primary/10 px-1.5 py-0 text-[10px] font-medium text-primary"
    >
      {Math.round(score * 100)}%
    </Badge>
  );
}

function MatchSnippet({ snippet, query }: { snippet: string; query: string }) {
  const trimmed = snippet.trim();
  if (!trimmed) {
    return null;
  }
  const segments = buildHighlightedTextSegments(trimmed, query);
  return (
    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
      {segments.map((segment, index) =>
        segment.highlighted ? (
          <mark key={index} className="rounded-sm bg-primary/20 px-0.5 text-foreground">
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </p>
  );
}

const STATUS_ICON_MAP: Record<
  string,
  { icon: ReactNode; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  QUEUED: { icon: <Clock className="h-3 w-3" />, variant: "secondary" },
  PROCESSING: { icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "default" },
  RETRYING: { icon: <RotateCw className="h-3 w-3 animate-spin" />, variant: "secondary" },
  COMPLETED: { icon: <CheckCircle className="h-3 w-3" />, variant: "outline" },
  FAILED: { icon: <XCircle className="h-3 w-3" />, variant: "destructive" },
  REVOKED: { icon: <Ban className="h-3 w-3" />, variant: "secondary" },
};

function StatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  const entry = STATUS_ICON_MAP[status];
  if (!entry) return null;
  return (
    <Badge variant={entry.variant} className="gap-1 px-1.5 py-0 text-[10px]">
      {entry.icon}
      {status}
    </Badge>
  );
}

function ReviewStateBadge({
  needsReview,
  t,
}: {
  needsReview: boolean;
  t: (key: string) => string;
}) {
  if (needsReview) {
    return (
      <Badge
        variant="outline"
        className="border-amber-300 bg-amber-50 text-[10px] text-amber-900 dark:border-amber-700/70 dark:bg-amber-950/30 dark:text-amber-100"
      >
        {t("needs_review_badge")}
      </Badge>
    );
  }
  return null;
}

function SortIndicator({
  col,
  activeCol,
  order,
}: {
  col: SortBy;
  activeCol: SortBy;
  order: SortOrder;
}) {
  if (activeCol !== col) return null;
  return order === "asc" ? (
    <ArrowUp className="ml-1 inline h-3 w-3" />
  ) : (
    <ArrowDown className="ml-1 inline h-3 w-3" />
  );
}

interface ContentListTableProps {
  t: (key: string) => string;
  processTooltip: string;
  files: ContentItemInfo[];
  folders?: FolderInfo[];
  /** Per-row semantic match metadata, keyed by content item id; smart mode only. */
  searchMeta?: ReadonlyMap<string, ContentSearchMeta>;
  /** Active semantic query, used to highlight snippet terms. */
  searchQuery?: string;
  isLoading: boolean;
  sortBy: SortBy;
  sortOrder: SortOrder;
  onToggleSort: (col: SortBy) => void;
  onFileClick?: (file: ContentItemInfo) => void;
  onFolderClick?: (path: string) => void;
  onProcess?: (path: string) => void;
  /** Custom trailing actions for a file row (replaces the default process button). */
  renderFileActions?: (file: ContentItemInfo) => ReactNode;
  /** Custom trailing actions for a folder row. */
  renderFolderActions?: (folder: FolderInfo) => ReactNode;
  selectedFilePaths?: ReadonlySet<string>;
  onToggleFileSelection?: (path: string, selected: boolean) => void;
  onToggleVisibleFileSelection?: (selected: boolean) => void;
}

export function ContentListTable({
  t,
  processTooltip,
  files,
  folders = [],
  searchMeta,
  searchQuery = "",
  isLoading,
  sortBy,
  sortOrder,
  onToggleSort,
  onFileClick,
  onFolderClick,
  onProcess,
  renderFileActions,
  renderFolderActions,
  selectedFilePaths,
  onToggleFileSelection,
  onToggleVisibleFileSelection,
}: ContentListTableProps) {
  const translate = useTranslate();
  const selectionEnabled = Boolean(onToggleFileSelection);
  const selectedVisibleCount = selectedFilePaths
    ? files.filter((file) => selectedFilePaths.has(file.path)).length
    : 0;
  const visibleSelectionChecked =
    files.length > 0 && selectedVisibleCount === files.length
      ? true
      : selectedVisibleCount > 0
        ? "indeterminate"
        : false;

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (files.length === 0 && folders.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        <p className="text-sm font-medium">{t("no_files")}</p>
        <p className="mt-1 text-xs">{t("no_files_hint")}</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="divide-y md:hidden">
        {folders.map((folder) => (
          <div
            key={`folder-card-${folder.id}`}
            role="button"
            tabIndex={0}
            className="flex w-full items-start gap-3 p-3 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50"
            onClick={() => onFolderClick?.(folder.path)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onFolderClick?.(folder.path);
              }
            }}
          >
            <Folder className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">
                {folder.display_name || folder.name}
              </span>
              <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>
                  {translate("custom.content.details.items", { count: folder.item_count ?? 0 })}
                </span>
                <span>{formatDate(folder.modified_at)}</span>
              </span>
            </span>
            {renderFolderActions ? (
              <span className="shrink-0" onClick={(event) => event.stopPropagation()}>
                {renderFolderActions(folder)}
              </span>
            ) : (
              <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            )}
          </div>
        ))}
        {selectionEnabled && files.length > 0 && (
          <div className="flex items-center gap-3 p-3 text-sm text-muted-foreground">
            <Checkbox
              checked={visibleSelectionChecked}
              aria-label={t("select_all_loaded")}
              onCheckedChange={(value) => onToggleVisibleFileSelection?.(value === true)}
            />
            <span>{t("select_all_loaded")}</span>
          </div>
        )}
        {files.map((file) => {
          const selected = selectedFilePaths?.has(file.path) ?? false;
          const rowModel = buildContentListRowModel(file);
          const meta = searchMeta?.get(file.id);

          return (
            <div
              key={`file-card-${file.id}`}
              role="button"
              tabIndex={0}
              data-state={selected ? "selected" : undefined}
              className="flex cursor-pointer items-start gap-3 p-3 outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 data-[state=selected]:bg-muted"
              onClick={() => onFileClick?.(file)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onFileClick?.(file);
                }
              }}
            >
              {selectionEnabled && (
                <Checkbox
                  checked={selected}
                  aria-label={t("select_row")}
                  className="mt-0.5"
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={(event) => event.stopPropagation()}
                  onCheckedChange={(value) => onToggleFileSelection?.(file.path, value === true)}
                />
              )}
              <span className="mt-0.5 shrink-0">
                {getContentItemIcon(file.kind, file.extension)}
              </span>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {getContentItemDisplayName(file)}
                    </div>
                    {rowModel.folderPath && (
                      <div className="truncate text-xs text-muted-foreground">
                        {rowModel.folderPath}
                      </div>
                    )}
                    {meta && <MatchSnippet snippet={meta.snippet} query={searchQuery} />}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {meta && <RelevanceBadge score={meta.score} />}
                    <StatusBadge status={rowModel.visibleStatus ?? undefined} />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <span>{formatSize(file.size_bytes)}</span>
                  <span>{formatDate(file.modified_at)}</span>
                  <Badge variant="outline" className="px-1.5 py-0 font-mono text-[10px]">
                    {translate(`custom.content.details.kind_${file.kind}`, {
                      defaultValue: file.extension || file.kind || "file",
                    })}
                  </Badge>
                </div>
                {(rowModel.showDocumentClassBadge || rowModel.showNeedsReviewBadge) && (
                  <div className="flex flex-wrap items-center gap-1">
                    {rowModel.showDocumentClassBadge && (
                      <DocumentClassBadge
                        classification={file.document_classification}
                        classificationLifecycle={file.document_enrichment?.classification_lifecycle}
                        extractionLifecycle={file.document_enrichment?.extraction_lifecycle}
                        className="w-fit"
                      />
                    )}
                    {rowModel.showNeedsReviewBadge && (
                      <ReviewStateBadge needsReview={rowModel.showNeedsReviewBadge} t={t} />
                    )}
                  </div>
                )}
              </div>
              {renderFileActions ? (
                <span className="shrink-0" onClick={(event) => event.stopPropagation()}>
                  {renderFileActions(file)}
                </span>
              ) : (
                onProcess &&
                !rowModel.isProcessing && (
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 shrink-0"
                    aria-label={processTooltip}
                    onClick={(event) => {
                      event.stopPropagation();
                      onProcess(file.path);
                    }}
                  >
                    <Play className="h-3.5 w-3.5" />
                  </Button>
                )
              )}
            </div>
          );
        })}
      </div>
      <div className="hidden md:block">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              {selectionEnabled && (
                <TableHead className="w-[44px]">
                  <Checkbox
                    checked={visibleSelectionChecked}
                    disabled={files.length === 0}
                    aria-label={t("select_all_loaded")}
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                    onCheckedChange={(value) => onToggleVisibleFileSelection?.(value === true)}
                  />
                </TableHead>
              )}
              <TableHead
                className="cursor-pointer select-none"
                onClick={() => onToggleSort("name")}
              >
                {t("col_name")}
                <SortIndicator col="name" activeCol={sortBy} order={sortOrder} />
              </TableHead>
              <TableHead
                className="w-[100px] cursor-pointer select-none"
                onClick={() => onToggleSort("size")}
              >
                {t("col_size")}
                <SortIndicator col="size" activeCol={sortBy} order={sortOrder} />
              </TableHead>
              <TableHead
                className="w-[160px] cursor-pointer select-none"
                onClick={() => onToggleSort("modified")}
              >
                {t("col_modified")}
                <SortIndicator col="modified" activeCol={sortBy} order={sortOrder} />
              </TableHead>
              <TableHead
                className="w-[100px] cursor-pointer select-none"
                onClick={() => onToggleSort("extension")}
              >
                {t("col_type")}
                <SortIndicator col="extension" activeCol={sortBy} order={sortOrder} />
              </TableHead>
              <TableHead className="w-[120px]">{t("col_status")}</TableHead>
              <TableHead className="w-[60px]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {folders.map((folder) => (
              <TableRow
                key={`folder-${folder.id}`}
                className="group cursor-pointer transition-colors hover:bg-muted/50"
                onClick={() => onFolderClick?.(folder.path)}
              >
                {selectionEnabled && <TableCell />}
                <TableCell className="min-w-0 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="block min-w-0 flex-1 truncate text-sm font-medium">
                      {folder.display_name || folder.name}
                    </span>
                    <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100" />
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {translate("custom.content.details.items", { count: folder.item_count ?? 0 })}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatDate(folder.modified_at)}
                </TableCell>
                <TableCell>
                  <Badge
                    variant="secondary"
                    className="px-1.5 py-0 text-[10px] uppercase tracking-wider"
                  >
                    {translate("custom.content.details.kind_folder")}
                  </Badge>
                </TableCell>
                <TableCell />
                <TableCell className="text-right">
                  {renderFolderActions && (
                    <span onClick={(event) => event.stopPropagation()}>
                      {renderFolderActions(folder)}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {files.map((file) => {
              const selected = selectedFilePaths?.has(file.path) ?? false;
              const rowModel = buildContentListRowModel(file);
              const meta = searchMeta?.get(file.id);

              return (
                <TableRow
                  key={file.id}
                  data-state={selected ? "selected" : undefined}
                  className="group cursor-pointer transition-colors hover:bg-muted/50"
                  onClick={() => onFileClick?.(file)}
                >
                  {selectionEnabled && (
                    <TableCell>
                      <Checkbox
                        checked={selected}
                        aria-label={t("select_row")}
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                        onCheckedChange={(value) =>
                          onToggleFileSelection?.(file.path, value === true)
                        }
                      />
                    </TableCell>
                  )}
                  <TableCell className="min-w-0 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="shrink-0">
                        {getContentItemIcon(file.kind, file.extension)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="min-w-0 flex-1 truncate text-sm">
                            {getContentItemDisplayName(file)}
                          </span>
                          {meta && <RelevanceBadge score={meta.score} />}
                        </div>
                        {meta && <MatchSnippet snippet={meta.snippet} query={searchQuery} />}
                        {(rowModel.folderPath ||
                          rowModel.showDocumentClassBadge ||
                          rowModel.showNeedsReviewBadge) && (
                          <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1">
                            {rowModel.folderPath && (
                              <span className="min-w-0 max-w-full truncate text-xs text-muted-foreground">
                                {rowModel.folderPath}
                              </span>
                            )}
                            {rowModel.showDocumentClassBadge && (
                              <DocumentClassBadge
                                classification={file.document_classification}
                                classificationLifecycle={
                                  file.document_enrichment?.classification_lifecycle
                                }
                                extractionLifecycle={file.document_enrichment?.extraction_lifecycle}
                                className="w-fit"
                              />
                            )}
                            {rowModel.showNeedsReviewBadge && (
                              <ReviewStateBadge needsReview={rowModel.showNeedsReviewBadge} t={t} />
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatSize(file.size_bytes)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(file.modified_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="px-1.5 py-0 font-mono text-[10px]">
                      {translate(`custom.content.details.kind_${file.kind}`, {
                        defaultValue: file.extension || file.kind || "file",
                      })}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={rowModel.visibleStatus ?? undefined} />
                  </TableCell>
                  <TableCell className="text-right">
                    {renderFileActions ? (
                      <span onClick={(event) => event.stopPropagation()}>
                        {renderFileActions(file)}
                      </span>
                    ) : (
                      onProcess &&
                      !rowModel.isProcessing && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                              onClick={(event) => {
                                event.stopPropagation();
                                onProcess(file.path);
                              }}
                            >
                              <Play className="h-3.5 w-3.5" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>{processTooltip}</p>
                          </TooltipContent>
                        </Tooltip>
                      )
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
