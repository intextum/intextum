import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fieldFilterInputType,
  operatorInputCount,
  operatorLabelKey,
  operatorsForDtype,
  type FieldFilterOperator,
  type FieldFilterPredicate,
} from "@/lib/field-filters";

interface FieldConditionControlsProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  predicate: FieldFilterPredicate;
  onChange: (patch: Partial<FieldFilterPredicate>) => void;
  onValueFocus?: () => void;
  onSubmit?: () => void;
  autoFocusValue?: boolean;
}

/** Shared operator picker + typed value input(s) for one field predicate. */
export function FieldConditionControls({
  t,
  predicate,
  onChange,
  onValueFocus,
  onSubmit,
  autoFocusValue,
}: FieldConditionControlsProps) {
  const operators = operatorsForDtype(predicate.dtype);
  const inputs = operatorInputCount(predicate.op);
  const inputType = fieldFilterInputType(predicate.dtype);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onSubmit?.();
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <Select
        value={predicate.op}
        onValueChange={(value) => onChange({ op: value as FieldFilterOperator })}
      >
        <SelectTrigger className="h-7 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {operators.map((op) => (
            <SelectItem key={op} value={op}>
              {t(operatorLabelKey(op, predicate.dtype))}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {inputs > 0 && (
        <div className={inputs === 2 ? "grid grid-cols-2 gap-2" : ""}>
          <Input
            type={inputType}
            className="h-7 text-xs"
            placeholder={t("field_conditions_value")}
            value={predicate.value}
            autoFocus={autoFocusValue}
            onFocus={onValueFocus}
            onKeyDown={handleKeyDown}
            onChange={(event) => onChange({ value: event.target.value })}
          />
          {inputs === 2 && (
            <Input
              type={inputType}
              className="h-7 text-xs"
              placeholder={t("field_conditions_value2")}
              value={predicate.value2}
              onFocus={onValueFocus}
              onKeyDown={handleKeyDown}
              onChange={(event) => onChange({ value2: event.target.value })}
            />
          )}
        </div>
      )}
    </div>
  );
}
