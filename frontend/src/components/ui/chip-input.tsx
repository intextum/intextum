import { useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface ChipInputProps {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  removeAriaLabel?: string;
  monoChips?: boolean;
  className?: string;
}

export function ChipInput({
  values,
  onChange,
  placeholder,
  removeAriaLabel = "Remove",
  monoChips = false,
  className,
}: ChipInputProps) {
  const [draft, setDraft] = useState("");

  const add = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) return;
    if (values.some((existing) => existing.toLowerCase() === trimmed.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...values, trimmed]);
    setDraft("");
  };

  const remove = (target: string) => {
    onChange(values.filter((entry) => entry.toLowerCase() !== target.toLowerCase()));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      add(draft);
    } else if (event.key === "Backspace" && !draft && values.length > 0) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-md border bg-background px-2 py-1.5",
        className,
      )}
    >
      {values.map((value) => (
        <Badge
          key={value}
          variant="secondary"
          className={cn("gap-1 pr-1 text-[11px]", monoChips ? "font-mono" : undefined)}
        >
          <span>{value}</span>
          <button
            type="button"
            aria-label={removeAriaLabel}
            className="rounded-sm p-0.5 hover:bg-muted-foreground/20"
            onClick={() => remove(value)}
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      ))}
      <Input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => add(draft)}
        placeholder={placeholder}
        className="h-7 min-w-[120px] flex-1 border-0 bg-transparent px-1 text-sm shadow-none focus-visible:ring-0"
      />
    </div>
  );
}
