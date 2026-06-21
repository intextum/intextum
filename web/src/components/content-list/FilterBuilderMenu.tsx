import { useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Filter,
  FileType2,
  Layers,
  ListChecks,
  ShieldCheck,
  Sparkles,
  Tag,
  Type,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ContentEnrichmentReviewStatus, ContentItemKind } from "@/dataProvider";
import type { FilterChip } from "@/lib/content-enrichment";
import {
  isFieldFilterComplete,
  makeFieldFilterPredicate,
  segmentsToLabel,
  type FieldFilterLeaf,
  type FieldFilterPredicate,
} from "@/lib/field-filters";

import { FieldConditionControls } from "./FieldConditionControls";

const STATUS_OPTIONS = ["QUEUED", "PROCESSING", "RETRYING", "COMPLETED", "FAILED", "REVOKED"];
const EXTENSION_OPTIONS = ["pdf", "docx", "doc", "txt", "md", "xlsx", "xls", "png", "jpg", "mp4"];
const CONTENT_KIND_OPTIONS: ContentItemKind[] = ["file", "email_message", "attachment"];
const REVIEW_STATUS_OPTIONS: ContentEnrichmentReviewStatus[] = [
  "unreviewed",
  "accepted",
  "corrected",
  "dismissed",
];

type BuilderPage =
  | "root"
  | "document_class"
  | "extraction_schema"
  | "extraction_field"
  | "field_value"
  | "status"
  | "review_status"
  | "content_kind"
  | "extension";

interface FilterBuilderMenuProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  advancedActiveCount: number;
  documentClassChips: FilterChip<string>[];
  extractionSchemaChips: FilterChip<string>[];
  fieldLeaves: FieldFilterLeaf[];
  documentClassFilter: string;
  extractionSchemaFilter: string;
  statusFilter: string;
  reviewStatusFilter: ContentEnrichmentReviewStatus | "";
  contentKindFilter: ContentItemKind | "";
  extensionFilter: string;
  staleOnly: boolean;
  onDocumentClassFilterChange: (value: string) => void;
  onExtractionSchemaFilterChange: (value: string) => void;
  onAddFieldCondition: (predicate: FieldFilterPredicate) => void;
  onStatusFilterChange: (value: string) => void;
  onReviewStatusFilterChange: (value: ContentEnrichmentReviewStatus | "") => void;
  onContentKindFilterChange: (value: ContentItemKind | "") => void;
  onExtensionFilterChange: (value: string) => void;
  onToggleStaleOnly: () => void;
}

function countSuffix(count: number | null): string {
  return count !== null ? ` (${count})` : "";
}

export function FilterBuilderMenu({
  t,
  advancedActiveCount,
  documentClassChips,
  extractionSchemaChips,
  fieldLeaves,
  documentClassFilter,
  extractionSchemaFilter,
  statusFilter,
  reviewStatusFilter,
  contentKindFilter,
  extensionFilter,
  staleOnly,
  onDocumentClassFilterChange,
  onExtractionSchemaFilterChange,
  onAddFieldCondition,
  onStatusFilterChange,
  onReviewStatusFilterChange,
  onContentKindFilterChange,
  onExtensionFilterChange,
  onToggleStaleOnly,
}: FilterBuilderMenuProps) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<BuilderPage>("root");
  const [pending, setPending] = useState<FieldFilterPredicate | null>(null);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setPage("root");
      setPending(null);
    }
  };

  const goToRoot = () => {
    setPage("root");
    setPending(null);
  };

  const startCondition = (leaf: FieldFilterLeaf) => {
    setPending(makeFieldFilterPredicate(leaf.segments, leaf.dtype));
    setPage("field_value");
  };

  const commitPending = () => {
    if (pending && isFieldFilterComplete(pending)) {
      onAddFieldCondition(pending);
      goToRoot();
    }
  };

  const renderBack = (titleKey: string, target: BuilderPage = "root") => (
    <div className="flex items-center gap-2 border-b px-2 py-1.5">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-6 gap-1 px-1.5 text-xs text-muted-foreground"
        onClick={() => setPage(target)}
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        {t("filter_builder_back")}
      </Button>
      <span className="text-xs font-medium">{t(titleKey)}</span>
    </div>
  );

  const renderValueItems = (
    chips: FilterChip<string>[],
    activeValue: string,
    onSelect: (value: string) => void,
  ) =>
    chips.length === 0 ? (
      <CommandEmpty>{t("filter_builder_no_options")}</CommandEmpty>
    ) : (
      chips.map((chip) => (
        <CommandItem
          key={chip.value}
          value={chip.value}
          onSelect={() => {
            onSelect(chip.value === activeValue ? "" : chip.value);
            goToRoot();
          }}
          className="justify-between gap-2"
        >
          <span className="truncate">{chip.value}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {chip.active ? "✓" : ""}
            {countSuffix(chip.count)}
          </span>
        </CommandItem>
      ))
    );

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="gap-2">
          <Filter className="h-3.5 w-3.5" />
          {t("filter_bar_add_filter")}
          {advancedActiveCount > 0 && (
            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
              {advancedActiveCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[320px] max-w-[95vw] p-0">
        <Command>
          {page === "root" && (
            <>
              <CommandInput placeholder={t("filter_builder_search")} />
              <CommandList>
                <CommandEmpty>{t("filter_builder_no_options")}</CommandEmpty>
                <CommandGroup heading={t("filter_bar_group_classification")}>
                  <CommandItem value="document_class" onSelect={() => setPage("document_class")}>
                    <Tag className="text-muted-foreground" />
                    <span>{t("filter_chip_document_class")}</span>
                    <div className="ml-auto flex items-center gap-2">
                      {documentClassFilter && (
                        <span className="max-w-[120px] truncate text-xs text-muted-foreground">
                          {documentClassFilter}
                        </span>
                      )}
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  </CommandItem>
                  <CommandItem
                    value="extraction_schema"
                    onSelect={() => setPage("extraction_schema")}
                  >
                    <Layers className="text-muted-foreground" />
                    <span>{t("filter_chip_extraction_schema")}</span>
                    <div className="ml-auto flex items-center gap-2">
                      {extractionSchemaFilter && (
                        <span className="max-w-[120px] truncate font-mono text-xs text-muted-foreground">
                          {extractionSchemaFilter}
                        </span>
                      )}
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  </CommandItem>
                  <CommandItem
                    value="extraction_field"
                    onSelect={() => setPage("extraction_field")}
                  >
                    <Sparkles className="text-muted-foreground" />
                    <span>{t("filter_chip_extraction_field")}</span>
                    <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
                  </CommandItem>
                </CommandGroup>
                <CommandSeparator />
                <CommandGroup heading={t("filter_bar_group_other")}>
                  <CommandItem value="status" onSelect={() => setPage("status")}>
                    <ListChecks className="text-muted-foreground" />
                    <span>{t("filter_chip_status")}</span>
                    <div className="ml-auto flex items-center gap-2">
                      {statusFilter && (
                        <span className="text-xs text-muted-foreground">{statusFilter}</span>
                      )}
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  </CommandItem>
                  <CommandItem value="review_status" onSelect={() => setPage("review_status")}>
                    <ShieldCheck className="text-muted-foreground" />
                    <span>{t("filter_chip_review_status")}</span>
                    <div className="ml-auto flex items-center gap-2">
                      {reviewStatusFilter && (
                        <span className="text-xs text-muted-foreground">
                          {t(`review_status_${reviewStatusFilter}`)}
                        </span>
                      )}
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  </CommandItem>
                  <CommandItem value="content_kind" onSelect={() => setPage("content_kind")}>
                    <Type className="text-muted-foreground" />
                    <span>{t("filter_chip_content_kind")}</span>
                    <div className="ml-auto flex items-center gap-2">
                      {contentKindFilter && (
                        <span className="text-xs text-muted-foreground">
                          {t(`content_kind_${contentKindFilter}`)}
                        </span>
                      )}
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  </CommandItem>
                  <CommandItem value="extension" onSelect={() => setPage("extension")}>
                    <FileType2 className="text-muted-foreground" />
                    <span>{t("filter_chip_extension")}</span>
                    <div className="ml-auto flex items-center gap-2">
                      {extensionFilter && (
                        <span className="text-xs text-muted-foreground">.{extensionFilter}</span>
                      )}
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  </CommandItem>
                  <CommandItem
                    value="stale"
                    onSelect={() => {
                      onToggleStaleOnly();
                      handleOpenChange(false);
                    }}
                  >
                    <Sparkles className="text-muted-foreground" />
                    <span>{t("stale_filter")}</span>
                    {staleOnly && <span className="ml-auto text-xs text-muted-foreground">✓</span>}
                  </CommandItem>
                </CommandGroup>
              </CommandList>
            </>
          )}

          {page === "document_class" && (
            <>
              {renderBack("filter_chip_document_class")}
              <CommandInput placeholder={t("document_class_filter")} />
              <CommandList>
                {renderValueItems(
                  documentClassChips,
                  documentClassFilter,
                  onDocumentClassFilterChange,
                )}
              </CommandList>
            </>
          )}

          {page === "extraction_schema" && (
            <>
              {renderBack("filter_chip_extraction_schema")}
              <CommandInput placeholder={t("extraction_schema_filter")} />
              <CommandList>
                {renderValueItems(
                  extractionSchemaChips,
                  extractionSchemaFilter,
                  onExtractionSchemaFilterChange,
                )}
              </CommandList>
            </>
          )}

          {page === "extraction_field" && (
            <>
              {renderBack("filter_chip_extraction_field")}
              <CommandInput placeholder={t("extraction_field_filter")} />
              <CommandList>
                {fieldLeaves.length === 0 ? (
                  <CommandEmpty>{t("filter_builder_no_options")}</CommandEmpty>
                ) : (
                  fieldLeaves.map((leaf) => (
                    <CommandItem
                      key={leaf.label}
                      value={leaf.label}
                      onSelect={() => startCondition(leaf)}
                      className="items-center justify-between gap-2"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate font-mono text-xs">{leaf.label}</span>
                        <span className="shrink-0 rounded-full border px-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {leaf.dtype}
                        </span>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {countSuffix(leaf.count)}
                      </span>
                    </CommandItem>
                  ))
                )}
              </CommandList>
            </>
          )}

          {page === "field_value" && pending && (
            <>
              {renderBack("filter_chip_extraction_field", "extraction_field")}
              <div className="space-y-3 p-3">
                <p className="truncate font-mono text-xs text-foreground">
                  {segmentsToLabel(pending.segments)}
                </p>
                <FieldConditionControls
                  t={t}
                  predicate={pending}
                  onChange={(patch) => setPending((current) => current && { ...current, ...patch })}
                  onSubmit={commitPending}
                  autoFocusValue
                />
                <Button
                  type="button"
                  size="sm"
                  className="h-7 w-full text-xs"
                  disabled={!isFieldFilterComplete(pending)}
                  onClick={commitPending}
                >
                  {t("field_conditions_add")}
                </Button>
              </div>
            </>
          )}

          {page === "status" && (
            <>
              {renderBack("filter_chip_status")}
              <CommandList>
                <CommandItem
                  value="__all__"
                  onSelect={() => {
                    onStatusFilterChange("");
                    goToRoot();
                  }}
                >
                  {t("all_statuses")}
                  {!statusFilter && (
                    <span className="ml-auto text-xs text-muted-foreground">✓</span>
                  )}
                </CommandItem>
                {STATUS_OPTIONS.map((status) => (
                  <CommandItem
                    key={status}
                    value={status}
                    onSelect={() => {
                      onStatusFilterChange(status === statusFilter ? "" : status);
                      goToRoot();
                    }}
                  >
                    {status}
                    {status === statusFilter && (
                      <span className="ml-auto text-xs text-muted-foreground">✓</span>
                    )}
                  </CommandItem>
                ))}
              </CommandList>
            </>
          )}

          {page === "review_status" && (
            <>
              {renderBack("filter_chip_review_status")}
              <CommandList>
                <CommandItem
                  value="__all__"
                  onSelect={() => {
                    onReviewStatusFilterChange("");
                    goToRoot();
                  }}
                >
                  {t("all_review_statuses")}
                  {!reviewStatusFilter && (
                    <span className="ml-auto text-xs text-muted-foreground">✓</span>
                  )}
                </CommandItem>
                {REVIEW_STATUS_OPTIONS.map((status) => (
                  <CommandItem
                    key={status}
                    value={status}
                    onSelect={() => {
                      onReviewStatusFilterChange(status === reviewStatusFilter ? "" : status);
                      goToRoot();
                    }}
                  >
                    {t(`review_status_${status}`)}
                    {status === reviewStatusFilter && (
                      <span className="ml-auto text-xs text-muted-foreground">✓</span>
                    )}
                  </CommandItem>
                ))}
              </CommandList>
            </>
          )}

          {page === "content_kind" && (
            <>
              {renderBack("filter_chip_content_kind")}
              <CommandList>
                <CommandItem
                  value="__all__"
                  onSelect={() => {
                    onContentKindFilterChange("");
                    goToRoot();
                  }}
                >
                  {t("all_content_kinds")}
                  {!contentKindFilter && (
                    <span className="ml-auto text-xs text-muted-foreground">✓</span>
                  )}
                </CommandItem>
                {CONTENT_KIND_OPTIONS.map((kind) => (
                  <CommandItem
                    key={kind}
                    value={kind}
                    onSelect={() => {
                      onContentKindFilterChange(kind === contentKindFilter ? "" : kind);
                      goToRoot();
                    }}
                  >
                    {t(`content_kind_${kind}`)}
                    {kind === contentKindFilter && (
                      <span className="ml-auto text-xs text-muted-foreground">✓</span>
                    )}
                  </CommandItem>
                ))}
              </CommandList>
            </>
          )}

          {page === "extension" && (
            <>
              {renderBack("filter_chip_extension")}
              <CommandInput placeholder={t("extension_filter")} />
              <CommandList>
                <CommandItem
                  value="__all__"
                  onSelect={() => {
                    onExtensionFilterChange("");
                    goToRoot();
                  }}
                >
                  {t("all_extensions")}
                  {!extensionFilter && (
                    <span className="ml-auto text-xs text-muted-foreground">✓</span>
                  )}
                </CommandItem>
                {EXTENSION_OPTIONS.map((ext) => (
                  <CommandItem
                    key={ext}
                    value={ext}
                    onSelect={() => {
                      onExtensionFilterChange(ext === extensionFilter ? "" : ext);
                      goToRoot();
                    }}
                  >
                    .{ext}
                    {ext === extensionFilter && (
                      <span className="ml-auto text-xs text-muted-foreground">✓</span>
                    )}
                  </CommandItem>
                ))}
              </CommandList>
            </>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}
