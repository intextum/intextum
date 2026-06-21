import { FolderTree, Regex, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Toggle } from "@/components/ui/toggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ContentEnrichmentReviewStatus, ContentItemKind } from "@/dataProvider";
import type { FilterChip } from "@/lib/content-enrichment";
import type { FieldFilterLeaf, FieldFilterPredicate } from "@/lib/field-filters";

import { FieldConditionsEditor } from "./FieldConditionsEditor";
import { FilterBuilderMenu } from "./FilterBuilderMenu";
import type { ContentListFilterChip } from "./useContentListFilters";

const SEARCH_OPTION_TOGGLE_CLASS =
  "h-7 min-w-7 rounded-sm px-0 text-muted-foreground hover:bg-muted hover:text-foreground aria-[pressed=true]:border-primary aria-[pressed=true]:bg-primary aria-[pressed=true]:text-primary-foreground aria-[pressed=true]:shadow-sm aria-[pressed=true]:ring-1 aria-[pressed=true]:ring-primary/30 aria-[pressed=true]:hover:bg-primary/90";

interface ContentListFilterBarProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  total: number;
  isLoading: boolean;
  nameFilter: string;
  nameRegex: boolean;
  searchPath: boolean;
  contentKindFilter: ContentItemKind | "";
  documentClassFilter: string;
  extractionSchemaFilter: string;
  extractionFieldFilter: string;
  fieldPredicates: FieldFilterPredicate[];
  extensionFilter: string;
  statusFilter: string;
  staleOnly: boolean;
  reviewStatusFilter: ContentEnrichmentReviewStatus | "";
  activeFilterChips: ContentListFilterChip[];
  documentClassChips: FilterChip<string>[];
  extractionSchemaChips: FilterChip<string>[];
  fieldLeaves: FieldFilterLeaf[];
  extractionValueChips: FilterChip<string>[];
  onNameFilterChange: (value: string) => void;
  onNameRegexChange: (value: boolean) => void;
  onSearchPathChange: (value: boolean) => void;
  onContentKindFilterChange: (value: ContentItemKind | "") => void;
  onDocumentClassFilterChange: (value: string) => void;
  onExtractionSchemaFilterChange: (value: string) => void;
  onSetExtractionFieldFocus: (value: string) => void;
  onAddFieldCondition: (predicate: FieldFilterPredicate) => void;
  onUpdateFieldCondition: (index: number, patch: Partial<FieldFilterPredicate>) => void;
  onRemoveFieldCondition: (index: number) => void;
  onExtensionFilterChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onReviewStatusFilterChange: (value: ContentEnrichmentReviewStatus | "") => void;
  onToggleStaleOnly: () => void;
}

function chipLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  chip: ContentListFilterChip,
): string {
  switch (chip.kind) {
    case "name":
      return `${t("filter_chip_name")}: ${chip.value}`;
    case "content_kind":
      return `${t("filter_chip_content_kind")}: ${t(`content_kind_${chip.value}`)}`;
    case "document_class":
      return `${t("filter_chip_document_class")}: ${chip.value}`;
    case "extraction_schema":
      return `${t("filter_chip_extraction_schema")}: ${chip.value}`;
    case "extension":
      return `${t("filter_chip_extension")}: .${chip.value}`;
    case "status":
      return `${t("filter_chip_status")}: ${chip.value}`;
    case "review_status":
      return `${t("filter_chip_review_status")}: ${t(`review_status_${chip.value}`)}`;
    case "stale_enrichment":
      return t("stale_filter");
  }
}

export function ContentListFilterBar({
  t,
  total,
  isLoading,
  nameFilter,
  nameRegex,
  searchPath,
  contentKindFilter,
  documentClassFilter,
  extractionSchemaFilter,
  extractionFieldFilter,
  fieldPredicates,
  extensionFilter,
  statusFilter,
  staleOnly,
  reviewStatusFilter,
  activeFilterChips,
  documentClassChips,
  extractionSchemaChips,
  fieldLeaves,
  extractionValueChips,
  onNameFilterChange,
  onNameRegexChange,
  onSearchPathChange,
  onContentKindFilterChange,
  onDocumentClassFilterChange,
  onExtractionSchemaFilterChange,
  onSetExtractionFieldFocus,
  onAddFieldCondition,
  onUpdateFieldCondition,
  onRemoveFieldCondition,
  onExtensionFilterChange,
  onStatusFilterChange,
  onReviewStatusFilterChange,
  onToggleStaleOnly,
}: ContentListFilterBarProps) {
  const advancedActiveCount =
    activeFilterChips.filter((chip) => chip.kind !== "name").length + fieldPredicates.length;
  const hasActiveRow = activeFilterChips.length > 0 || fieldPredicates.length > 0;

  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card/70 p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] max-w-sm flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            data-shortcut-search="true"
            placeholder={t("name_filter")}
            value={nameFilter}
            onChange={(event) => onNameFilterChange(event.target.value)}
            className="pl-8 pr-20"
          />
          <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <Toggle
                  pressed={nameRegex}
                  onPressedChange={onNameRegexChange}
                  variant="outline"
                  size="sm"
                  aria-label={t("name_regex_toggle")}
                  className={SEARCH_OPTION_TOGGLE_CLASS}
                >
                  <Regex className="h-3.5 w-3.5" />
                </Toggle>
              </TooltipTrigger>
              <TooltipContent>{t("name_regex_toggle_tooltip")}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Toggle
                  pressed={searchPath}
                  onPressedChange={onSearchPathChange}
                  variant="outline"
                  size="sm"
                  aria-label={t("search_path_toggle")}
                  className={SEARCH_OPTION_TOGGLE_CLASS}
                >
                  <FolderTree className="h-3.5 w-3.5" />
                </Toggle>
              </TooltipTrigger>
              <TooltipContent>{t("search_path_toggle_tooltip")}</TooltipContent>
            </Tooltip>
          </div>
        </div>

        <FilterBuilderMenu
          t={t}
          advancedActiveCount={advancedActiveCount}
          documentClassChips={documentClassChips}
          extractionSchemaChips={extractionSchemaChips}
          fieldLeaves={fieldLeaves}
          documentClassFilter={documentClassFilter}
          extractionSchemaFilter={extractionSchemaFilter}
          statusFilter={statusFilter}
          reviewStatusFilter={reviewStatusFilter}
          contentKindFilter={contentKindFilter}
          extensionFilter={extensionFilter}
          staleOnly={staleOnly}
          onDocumentClassFilterChange={onDocumentClassFilterChange}
          onExtractionSchemaFilterChange={onExtractionSchemaFilterChange}
          onAddFieldCondition={onAddFieldCondition}
          onStatusFilterChange={onStatusFilterChange}
          onReviewStatusFilterChange={onReviewStatusFilterChange}
          onContentKindFilterChange={onContentKindFilterChange}
          onExtensionFilterChange={onExtensionFilterChange}
          onToggleStaleOnly={onToggleStaleOnly}
        />

        {!isLoading && (
          <span className="ml-auto text-sm text-muted-foreground">
            {t("filter_bar_total_files", { count: total })}
          </span>
        )}
      </div>

      {hasActiveRow && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t("filter_bar_active")}
          </span>
          {activeFilterChips.map((chip) => (
            <Badge
              key={`${chip.kind}-${chip.value}`}
              variant="secondary"
              className="gap-1 pr-1 text-[11px]"
            >
              <span className="truncate max-w-[220px]">{chipLabel(t, chip)}</span>
              <button
                type="button"
                aria-label={t("filter_bar_remove_filter")}
                className="rounded-sm p-0.5 hover:bg-muted-foreground/20"
                onClick={(event) => {
                  event.stopPropagation();
                  chip.remove();
                }}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {fieldPredicates.length > 0 && (
            <FieldConditionsEditor
              t={t}
              predicates={fieldPredicates}
              focusField={extractionFieldFilter}
              fieldLeaves={fieldLeaves}
              valueChips={extractionValueChips}
              onAddCondition={onAddFieldCondition}
              onUpdateCondition={onUpdateFieldCondition}
              onRemoveCondition={onRemoveFieldCondition}
              onSetFocusField={onSetExtractionFieldFocus}
            />
          )}
        </div>
      )}
    </div>
  );
}
