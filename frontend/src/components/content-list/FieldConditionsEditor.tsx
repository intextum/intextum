import { useState } from "react";
import { Plus, SlidersHorizontal, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { FilterChip } from "@/lib/content-enrichment";
import {
  isTopLevelScalarPath,
  makeFieldFilterPredicate,
  operatorInputCount,
  segmentsToLabel,
  topLevelField,
  type FieldFilterLeaf,
  type FieldFilterPredicate,
} from "@/lib/field-filters";

import { FieldConditionControls } from "./FieldConditionControls";

interface FieldConditionsEditorProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  predicates: FieldFilterPredicate[];
  focusField: string;
  fieldLeaves: FieldFilterLeaf[];
  valueChips: FilterChip<string>[];
  onAddCondition: (predicate: FieldFilterPredicate) => void;
  onUpdateCondition: (index: number, patch: Partial<FieldFilterPredicate>) => void;
  onRemoveCondition: (index: number) => void;
  onSetFocusField: (field: string) => void;
}

export function FieldConditionsEditor({
  t,
  predicates,
  focusField,
  fieldLeaves,
  valueChips,
  onAddCondition,
  onUpdateCondition,
  onRemoveCondition,
  onSetFocusField,
}: FieldConditionsEditorProps) {
  const [addOpen, setAddOpen] = useState(false);

  const handlePickLeaf = (leaf: FieldFilterLeaf) => {
    onAddCondition(makeFieldFilterPredicate(leaf.segments, leaf.dtype));
    onSetFocusField(topLevelField(leaf.segments));
    setAddOpen(false);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="secondary" size="sm" className="h-6 gap-1 px-2 text-[11px]">
          <SlidersHorizontal className="h-3 w-3" />
          {t("field_conditions_count", { count: predicates.length })}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[380px] max-w-[95vw] space-y-3 p-3">
        <p className="text-xs font-medium text-muted-foreground">{t("field_conditions_title")}</p>

        {predicates.length === 0 && (
          <p className="text-xs text-muted-foreground">{t("field_conditions_empty")}</p>
        )}

        <div className="space-y-3">
          {predicates.map((predicate, index) => {
            const inputs = operatorInputCount(predicate.op);
            const label = segmentsToLabel(predicate.segments);
            const fieldName = topLevelField(predicate.segments);
            const showSuggestions =
              isTopLevelScalarPath(predicate.segments) &&
              fieldName === focusField &&
              valueChips.length > 0 &&
              inputs > 0;
            return (
              <div key={`${label}-${index}`} className="space-y-1.5 rounded-md border p-2">
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">{label}</span>
                  <button
                    type="button"
                    aria-label={t("filter_bar_remove_filter")}
                    className="rounded-sm p-1 text-muted-foreground hover:bg-muted"
                    onClick={() => onRemoveCondition(index)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                <FieldConditionControls
                  t={t}
                  predicate={predicate}
                  onChange={(patch) => onUpdateCondition(index, patch)}
                  onValueFocus={() => onSetFocusField(fieldName)}
                />

                {showSuggestions && (
                  <div className="flex flex-wrap gap-1">
                    {valueChips.map((chip) => (
                      <Badge
                        key={chip.value}
                        variant="outline"
                        className="cursor-pointer gap-1 text-[11px] font-normal"
                        onClick={() => onUpdateCondition(index, { value: chip.value })}
                      >
                        <span className="max-w-[140px] truncate">{chip.value}</span>
                        {chip.count !== null && (
                          <span className="text-muted-foreground">{chip.count}</span>
                        )}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <Popover open={addOpen} onOpenChange={setAddOpen}>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="h-7 w-full gap-2 text-xs">
              <Plus className="h-3.5 w-3.5" />
              {t("field_conditions_add")}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-[280px] p-0">
            <Command>
              <CommandInput placeholder={t("field_conditions_pick_field")} />
              <CommandList>
                <CommandEmpty>{t("filter_builder_no_options")}</CommandEmpty>
                {fieldLeaves.map((leaf) => (
                  <CommandItem
                    key={leaf.label}
                    value={leaf.label}
                    onSelect={() => handlePickLeaf(leaf)}
                    className="justify-between gap-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-mono text-xs">{leaf.label}</span>
                      <span className="shrink-0 rounded-full border px-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                        {leaf.dtype}
                      </span>
                    </div>
                    {leaf.count !== null && (
                      <span className="shrink-0 text-xs text-muted-foreground">{leaf.count}</span>
                    )}
                  </CommandItem>
                ))}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </PopoverContent>
    </Popover>
  );
}
