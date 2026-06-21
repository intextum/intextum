import { useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTranslate } from "@/lib/app-context";
import { coerceObjectListItemDraft, formatObjectListChildValue } from "@/lib/document-data-values";
import { cn } from "@/lib/utils";
import { EvidenceChip } from "./EvidenceChip";
import {
  allDocRefs,
  childFieldName,
  collectListSuggestions,
  collectObjectListSuggestions,
  emptyObjectListItem,
  fieldCandidates,
  fieldLabel,
  formatConfidence,
  formatValue,
  hasDisplayValue,
  listContainsValue,
  listItemEvidenceDocRefs,
  listItemCandidate,
  mergeListValues,
  mergeObjectListValues,
  normalizeListValue,
  normalizeObjectListValue,
  numericConfidence,
  objectChildFields,
  objectListContainsValue,
  objectListItemCandidate,
  objectListItemEvidenceDocRefs,
  valuesEqual,
  type FieldBucket,
} from "./document-data-panel-utils";

const COLLAPSED_LIST_ITEM_COUNT = 3;

export interface DocumentDataFieldRowProps {
  fieldKey: string;
  rawValue: unknown;
  aiValue: unknown;
  meta: Record<string, unknown> | undefined;
  needsReview: boolean;
  bucket: FieldBucket;
  disabled: boolean;
  saving: boolean;
  onSave: (key: string, value: unknown) => void;
  onNavigateToEvidence?: (docRefs: string[], label: string) => void;
}

export const DocumentDataFieldRow = ({
  fieldKey,
  rawValue,
  aiValue,
  meta,
  needsReview,
  bucket,
  disabled,
  saving,
  onSave,
  onNavigateToEvidence,
}: DocumentDataFieldRowProps) => {
  const translate = useTranslate();
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState(() => formatValue(rawValue));
  const [listDraft, setListDraft] = useState<string[]>(() => normalizeListValue(rawValue));
  const [objectListDraft, setObjectListDraft] = useState<Array<Record<string, unknown>>>(() =>
    normalizeObjectListValue(rawValue),
  );
  const dtype = typeof meta?.dtype === "string" ? meta.dtype : undefined;
  const isObjectList = dtype === "object_list";
  const isList = !isObjectList && (dtype === "list" || Array.isArray(rawValue));
  const objectListItems = normalizeObjectListValue(rawValue);
  const listItems = isList ? normalizeListValue(rawValue) : [];
  const extractedItemCount = isObjectList ? objectListItems.length : isList ? listItems.length : 0;
  const canCollapseExtractedItems = !editing && extractedItemCount > COLLAPSED_LIST_ITEM_COUNT;
  const visibleObjectListItems =
    canCollapseExtractedItems && !expanded
      ? objectListItems.slice(0, COLLAPSED_LIST_ITEM_COUNT)
      : objectListItems;
  const visibleListItems =
    canCollapseExtractedItems && !expanded
      ? listItems.slice(0, COLLAPSED_LIST_ITEM_COUNT)
      : listItems;
  const childFields = objectChildFields(meta);
  const childFieldByName = new Map(
    childFields
      .map((child) => {
        const name = childFieldName(child);
        return name ? ([name, child] as const) : null;
      })
      .filter((entry): entry is readonly [string, Record<string, unknown>] => entry !== null),
  );
  const isLong = typeof rawValue === "string" && rawValue.length > 64;
  const evidenceDocRefs = allDocRefs(meta?.evidence);
  const showCandidates = bucket === "attention";
  const candidates = showCandidates
    ? fieldCandidates(meta).filter((candidate) =>
        isObjectList
          ? !objectListContainsValue(rawValue, candidate.value)
          : isList
            ? !listContainsValue(rawValue, candidate.value)
            : !valuesEqual(candidate.value, rawValue),
      )
    : [];
  const confidence = numericConfidence(meta?.confidence);
  const hasValue = hasDisplayValue(rawValue);
  const aiHasValue = hasDisplayValue(aiValue);
  const showAiDiff = aiHasValue && !valuesEqual(rawValue, aiValue);
  const isComplexValue = isObjectList || isList;
  const canClickToEdit = !disabled && !editing && !isComplexValue;
  const listSuggestions = isList && editing ? collectListSuggestions(listDraft, aiValue, meta) : [];
  const objectListSuggestions =
    isObjectList && editing ? collectObjectListSuggestions(objectListDraft, aiValue, meta) : [];
  const shouldUseMultilineInput = (value: unknown) => {
    const formatted = formatValue(value);
    return formatted.length > 80 || formatted.includes("\n");
  };

  const startEdit = () => {
    setDraft(formatValue(rawValue));
    setListDraft(normalizeListValue(rawValue));
    setObjectListDraft(normalizeObjectListValue(rawValue));
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setDraft(formatValue(rawValue));
    setListDraft(normalizeListValue(rawValue));
    setObjectListDraft(normalizeObjectListValue(rawValue));
  };

  const commit = () => {
    let parsed: unknown = draft;
    if (isObjectList) {
      parsed = objectListDraft
        .map((item) => coerceObjectListItemDraft(item, childFields))
        .filter((item) => Object.keys(item).length > 0);
    } else if (isList) {
      parsed = listDraft.map((item) => item.trim()).filter(Boolean);
    } else if (typeof rawValue === "number") {
      const n = Number(draft);
      if (Number.isFinite(n)) parsed = n;
    } else if (typeof rawValue === "boolean") {
      parsed = draft === "true" || draft === "1";
    }
    onSave(fieldKey, parsed);
    setEditing(false);
  };

  const aiTooltipLabel = translate("custom.content.details.ai_value", { defaultValue: "AI" });
  const useAiLabel = translate("custom.content.details.use_ai_value", {
    defaultValue: "Use AI value",
  });

  return (
    <div
      id={`inspector-field-${fieldKey}`}
      className={cn(
        "group relative px-3 py-2",
        bucket === "attention" && "border-l-2 border-amber-400/80 pl-[10px]",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-sm font-medium text-foreground">
            {fieldLabel(fieldKey)}
          </span>
          {extractedItemCount > 0 ? (
            <Badge variant="outline" className="h-5 rounded px-1.5 text-[10px] font-normal">
              {translate("custom.content.details.list_item_count", {
                count: extractedItemCount,
                defaultValue: `${extractedItemCount} items`,
              })}
            </Badge>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
          {confidence !== null ? <span>{formatConfidence(confidence)}</span> : null}
          <EvidenceChip
            docRefs={evidenceDocRefs}
            label={fieldLabel(fieldKey)}
            onNavigate={onNavigateToEvidence}
          />
          {needsReview ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="outline"
                  className="h-5 gap-1 rounded px-1.5 text-[10px] font-medium uppercase border-amber-300/60 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/30 dark:text-amber-200"
                >
                  <AlertCircle className="h-2.5 w-2.5" />
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                {translate("custom.content.details.review_unreviewed")}
              </TooltipContent>
            </Tooltip>
          ) : null}
          {showAiDiff ? (
            <Tooltip>
              <TooltipTrigger asChild>
                {editing && !disabled ? (
                  <button
                    type="button"
                    className="inline-flex h-5 items-center gap-1 rounded border bg-blue-50 px-1.5 text-[10px] font-medium uppercase border-blue-200 text-blue-900 hover:bg-blue-100 disabled:opacity-50 dark:border-blue-800/40 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50"
                    onClick={() => {
                      setDraft(formatValue(aiValue));
                      setListDraft(normalizeListValue(aiValue));
                      setObjectListDraft(normalizeObjectListValue(aiValue));
                    }}
                    disabled={saving}
                    aria-label={useAiLabel}
                  >
                    <Sparkles className="h-2.5 w-2.5" />
                  </button>
                ) : (
                  <Badge
                    variant="outline"
                    className="h-5 gap-1 rounded px-1.5 text-[10px] font-medium uppercase border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-800/40 dark:bg-blue-950/40 dark:text-blue-200"
                  >
                    <Sparkles className="h-2.5 w-2.5" />
                  </Badge>
                )}
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <div className="text-[10px] uppercase tracking-wide opacity-70">
                  {aiTooltipLabel}
                </div>
                <div className="font-mono text-xs">{formatValue(aiValue)}</div>
                {editing && !disabled ? (
                  <div className="mt-1 text-[10px] opacity-70">{useAiLabel}</div>
                ) : null}
              </TooltipContent>
            </Tooltip>
          ) : null}
          {!editing && !disabled ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                  onClick={startEdit}
                  disabled={saving}
                  aria-label={translate("custom.content.details.edit_override")}
                >
                  <Pencil className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{translate("custom.content.details.edit_override")}</TooltipContent>
            </Tooltip>
          ) : null}
          {canCollapseExtractedItems ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={() => setExpanded((current) => !current)}
                  aria-expanded={expanded}
                  aria-label={
                    expanded
                      ? translate("custom.content.details.collapse_field")
                      : translate("custom.content.details.expand_field")
                  }
                >
                  {expanded ? (
                    <ChevronDown className="h-3 w-3" />
                  ) : (
                    <ChevronRight className="h-3 w-3" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {expanded
                  ? translate("custom.content.details.collapse_field")
                  : translate("custom.content.details.expand_field")}
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </div>

      {editing ? (
        <div className="mt-1.5 space-y-1.5">
          {isObjectList ? (
            <div className="space-y-2">
              {objectListDraft.map((item, itemIndex) => {
                const itemCandidate = objectListItemCandidate(meta, item);
                return (
                  <div
                    key={`${fieldKey}-object-${itemIndex}`}
                    className="space-y-2 rounded-md border p-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="truncate font-medium">
                          {fieldLabel(fieldKey)} {itemIndex + 1}
                        </span>
                        {itemCandidate?.confidence !== null &&
                        itemCandidate?.confidence !== undefined ? (
                          <span className="shrink-0 text-[10px]">
                            {formatConfidence(itemCandidate.confidence)}
                          </span>
                        ) : null}
                      </div>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            onClick={() =>
                              setObjectListDraft((current) =>
                                current.filter((_, index) => index !== itemIndex),
                              )
                            }
                            disabled={saving}
                            aria-label={translate("custom.content.details.remove_list_value")}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          {translate("custom.content.details.remove_list_value")}
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    {(childFields.length > 0
                      ? childFields
                      : Object.keys(item).map((name) => ({ name }))
                    ).map((child) => {
                      const name = childFieldName(child);
                      if (!name) return null;
                      const childDtype = "dtype" in child ? child.dtype : undefined;
                      const childInputValue = formatObjectListChildValue(item[name], childDtype);
                      const useMultilineChildInput =
                        childDtype === "list" || shouldUseMultilineInput(item[name]);
                      return (
                        <div key={`${fieldKey}-${itemIndex}-${name}`} className="space-y-1">
                          <span className="text-xs text-muted-foreground">{fieldLabel(name)}</span>
                          {useMultilineChildInput ? (
                            <Textarea
                              value={childInputValue}
                              onChange={(event) =>
                                setObjectListDraft((current) =>
                                  current.map((entry, index) =>
                                    index === itemIndex
                                      ? { ...entry, [name]: event.target.value }
                                      : entry,
                                  ),
                                )
                              }
                              className="min-h-[72px] resize-y font-mono text-xs leading-relaxed"
                              disabled={saving}
                            />
                          ) : (
                            <Input
                              value={childInputValue}
                              onChange={(event) =>
                                setObjectListDraft((current) =>
                                  current.map((entry, index) =>
                                    index === itemIndex
                                      ? { ...entry, [name]: event.target.value }
                                      : entry,
                                  ),
                                )
                              }
                              className="h-7 font-mono text-xs"
                              disabled={saving}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
              <div className="flex flex-wrap items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 gap-1 px-2 text-xs"
                  onClick={() =>
                    setObjectListDraft((current) => [...current, emptyObjectListItem(childFields)])
                  }
                  disabled={saving}
                >
                  <Plus className="h-3 w-3" />
                  {translate("custom.content.details.add_list_value")}
                </Button>
                {objectListSuggestions.length > 0 ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 gap-1 px-2 text-xs"
                        disabled={saving}
                      >
                        <Sparkles className="h-3 w-3 text-blue-600 dark:text-blue-300" />
                        {translate("custom.content.details.add_from_ai")}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="max-h-72 w-72 overflow-auto">
                      {objectListSuggestions.map((suggestion) => (
                        <DropdownMenuItem
                          key={JSON.stringify(suggestion.value)}
                          onSelect={() =>
                            setObjectListDraft((current) => [...current, suggestion.value])
                          }
                          disabled={saving}
                        >
                          <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
                            <span className="truncate">{suggestion.label}</span>
                            {suggestion.confidence !== null ? (
                              <span className="shrink-0 text-[10px] text-muted-foreground">
                                {formatConfidence(suggestion.confidence)}
                              </span>
                            ) : null}
                          </div>
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>
            </div>
          ) : isList ? (
            <div className="space-y-1">
              {listDraft.map((item, index) => {
                const itemCandidate = listItemCandidate(meta, item);
                return (
                  <div key={`${fieldKey}-list-${index}`} className="flex items-start gap-1">
                    {shouldUseMultilineInput(item) ? (
                      <Textarea
                        value={item}
                        onChange={(event) =>
                          setListDraft((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index ? event.target.value : entry,
                            ),
                          )
                        }
                        className="min-h-[72px] resize-y font-mono text-xs leading-relaxed"
                        disabled={saving}
                      />
                    ) : (
                      <Input
                        value={item}
                        onChange={(event) =>
                          setListDraft((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index ? event.target.value : entry,
                            ),
                          )
                        }
                        className="h-7 font-mono text-xs"
                        disabled={saving}
                      />
                    )}
                    {itemCandidate?.confidence !== null &&
                    itemCandidate?.confidence !== undefined ? (
                      <span className="min-w-9 shrink-0 pt-1.5 text-right text-[10px] text-muted-foreground">
                        {formatConfidence(itemCandidate.confidence)}
                      </span>
                    ) : null}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setListDraft((current) =>
                              current.filter((_, entryIndex) => entryIndex !== index),
                            )
                          }
                          disabled={saving}
                          aria-label={translate("custom.content.details.remove_list_value")}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {translate("custom.content.details.remove_list_value")}
                      </TooltipContent>
                    </Tooltip>
                  </div>
                );
              })}
              <div className="flex flex-wrap items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 gap-1 px-2 text-xs"
                  onClick={() => setListDraft((current) => [...current, ""])}
                  disabled={saving}
                >
                  <Plus className="h-3 w-3" />
                  {translate("custom.content.details.add_list_value")}
                </Button>
                {listSuggestions.length > 0 ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 gap-1 px-2 text-xs"
                        disabled={saving}
                      >
                        <Sparkles className="h-3 w-3 text-blue-600 dark:text-blue-300" />
                        {translate("custom.content.details.add_from_ai")}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="max-h-72 w-64 overflow-auto">
                      {listSuggestions.map((suggestion) => (
                        <DropdownMenuItem
                          key={suggestion.value}
                          onSelect={() => setListDraft((current) => [...current, suggestion.value])}
                          disabled={saving}
                        >
                          <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
                            <span className="truncate font-mono text-xs">{suggestion.label}</span>
                            {suggestion.confidence !== null ? (
                              <span className="shrink-0 text-[10px] text-muted-foreground">
                                {formatConfidence(suggestion.confidence)}
                              </span>
                            ) : null}
                          </div>
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>
            </div>
          ) : isLong || (typeof rawValue === "string" && rawValue.includes("\n")) ? (
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="min-h-[80px] font-mono text-xs"
              disabled={saving}
              autoFocus
            />
          ) : (
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="h-7 font-mono text-xs"
              disabled={saving}
              autoFocus
            />
          )}
          <div className="flex items-center justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 gap-1 px-2 text-xs"
              onClick={cancel}
              disabled={saving}
            >
              <X className="h-3 w-3" />
              {translate("custom.content.processing_config.cancel")}
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-6 gap-1 px-2 text-xs"
              onClick={commit}
              disabled={saving}
            >
              <Check className="h-3 w-3" />
              {translate("custom.content.details.apply_field_edit")}
            </Button>
          </div>
        </div>
      ) : (
        <div
          className={cn(
            "mt-1",
            canClickToEdit && "-mx-1 cursor-text rounded px-1 hover:bg-muted/40",
          )}
          role={canClickToEdit ? "button" : undefined}
          tabIndex={canClickToEdit ? 0 : undefined}
          onClick={canClickToEdit ? startEdit : undefined}
          onKeyDown={
            canClickToEdit
              ? (event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    startEdit();
                  }
                }
              : undefined
          }
          aria-label={
            canClickToEdit ? translate("custom.content.details.edit_override") : undefined
          }
        >
          {isObjectList && objectListItems.length > 0 ? (
            <div className="space-y-1">
              {visibleObjectListItems.map((item, index) => {
                const itemEvidenceDocRefs = objectListItemEvidenceDocRefs(meta, item, index);
                const itemCandidate = objectListItemCandidate(meta, item);
                return (
                  <div
                    key={`${fieldKey}-object-value-${index}`}
                    className="rounded border bg-muted/30 p-2"
                  >
                    <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      <div className="flex min-w-0 items-center gap-1.5">
                        <span className="shrink-0 font-medium tabular-nums">#{index + 1}</span>
                        <span className="truncate">{fieldLabel(fieldKey)}</span>
                        {itemCandidate?.confidence !== null &&
                        itemCandidate?.confidence !== undefined ? (
                          <span className="shrink-0 text-[10px]">
                            {formatConfidence(itemCandidate.confidence)}
                          </span>
                        ) : null}
                      </div>
                      <EvidenceChip
                        docRefs={itemEvidenceDocRefs}
                        label={`${fieldLabel(fieldKey)} ${index + 1}`}
                        onNavigate={onNavigateToEvidence}
                      />
                    </div>
                    <div className="grid gap-1">
                      {Object.entries(item).map(([name, value]) => (
                        <div
                          key={name}
                          className="grid grid-cols-[110px_minmax(0,1fr)] gap-2 text-xs"
                        >
                          <span className="truncate text-muted-foreground">{fieldLabel(name)}</span>
                          <span className="min-w-0 whitespace-pre-wrap break-words font-mono leading-relaxed">
                            {formatObjectListChildValue(value, childFieldByName.get(name)?.dtype)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : isList && listItems.length > 0 ? (
            <div className="space-y-1.5">
              {visibleListItems.map((item, index) => {
                const itemCandidate = listItemCandidate(meta, item);
                const itemEvidenceDocRefs = listItemEvidenceDocRefs(meta, item, index);
                return (
                  <div
                    key={`${fieldKey}-value-${index}`}
                    className="rounded border bg-muted/30 px-2 py-1.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 flex-1 items-start gap-2">
                        <span className="shrink-0 pt-0.5 font-sans text-[10px] text-muted-foreground tabular-nums">
                          #{index + 1}
                        </span>
                        <span className="min-w-0 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                          {formatValue(item)}
                        </span>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {itemCandidate?.confidence !== null &&
                        itemCandidate?.confidence !== undefined ? (
                          <span className="font-sans text-[10px] text-muted-foreground">
                            {formatConfidence(itemCandidate.confidence)}
                          </span>
                        ) : null}
                        <EvidenceChip
                          docRefs={itemEvidenceDocRefs}
                          label={`${fieldLabel(fieldKey)} ${index + 1}`}
                          onNavigate={onNavigateToEvidence}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="break-words font-mono text-xs">
              {hasValue ? formatValue(rawValue) : <span className="text-muted-foreground">-</span>}
            </div>
          )}
          {canCollapseExtractedItems ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-1 h-6 px-1.5 text-xs text-muted-foreground"
              onClick={() => setExpanded((current) => !current)}
              aria-expanded={expanded}
            >
              {expanded ? (
                <>
                  <ChevronDown className="mr-1 h-3 w-3" />
                  {translate("custom.content.details.show_fewer_items")}
                </>
              ) : (
                <>
                  <ChevronRight className="mr-1 h-3 w-3" />
                  {translate("custom.content.details.show_all_items", {
                    count: extractedItemCount,
                    defaultValue: `Show all ${extractedItemCount} items`,
                  })}
                </>
              )}
            </Button>
          ) : null}
        </div>
      )}

      {candidates.length > 0 && !editing ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">
            {translate("custom.content.details.candidate_values")}:
          </span>
          {candidates.slice(0, 4).map((candidate) => (
            <span key={candidate.label} className="inline-flex items-center gap-0.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-5 max-w-[160px] truncate px-1.5 text-[10px]"
                onClick={() =>
                  onSave(
                    fieldKey,
                    isObjectList
                      ? mergeObjectListValues(rawValue, candidate.value)
                      : isList
                        ? mergeListValues(rawValue, candidate.value)
                        : candidate.value,
                  )
                }
                disabled={disabled || saving}
                title={candidate.label}
              >
                <span className="truncate">{candidate.label}</span>
                {candidate.confidence !== null ? (
                  <span className="ml-1 text-muted-foreground">
                    {formatConfidence(candidate.confidence)}
                  </span>
                ) : null}
              </Button>
              <EvidenceChip
                docRefs={candidate.evidenceDocRefs}
                label={`${fieldLabel(fieldKey)} ${candidate.label}`}
                onNavigate={onNavigateToEvidence}
              />
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
};
