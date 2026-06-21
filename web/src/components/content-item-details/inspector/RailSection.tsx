import { useEffect, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export interface RailSectionProps {
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  badge?: ReactNode;
  trailing?: ReactNode;
  defaultOpen?: boolean;
  forceOpen?: boolean;
  storageKey?: string;
  children: ReactNode;
}

const readStoredOpen = (storageKey: string | undefined, fallback: boolean): boolean => {
  if (!storageKey || typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (raw === "1") return true;
    if (raw === "0") return false;
  } catch {
    // ignore
  }
  return fallback;
};

export const RailSection = ({
  id,
  icon: Icon,
  title,
  badge,
  trailing,
  defaultOpen = false,
  forceOpen = false,
  storageKey,
  children,
}: RailSectionProps) => {
  const initialOpen = forceOpen || readStoredOpen(storageKey, defaultOpen);
  const [open, setOpen] = useState(initialOpen);
  const [mounted, setMounted] = useState(initialOpen);
  const effectiveOpen = forceOpen || open;

  const handleOpenChange = (next: boolean) => {
    if (forceOpen) return;
    if (next) setMounted(true);
    setOpen(next);
  };

  useEffect(() => {
    if (!storageKey || typeof window === "undefined") return;
    try {
      window.localStorage.setItem(storageKey, open ? "1" : "0");
    } catch {
      // ignore
    }
  }, [open, storageKey]);

  return (
    <Collapsible
      open={effectiveOpen}
      onOpenChange={handleOpenChange}
      className="border-b last:border-b-0"
      id={id}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <CollapsibleTrigger
          disabled={forceOpen}
          className={cn(
            "group flex min-w-0 flex-1 items-center gap-2 rounded-sm text-left",
            forceOpen ? "cursor-default" : "hover:text-foreground",
          )}
        >
          {!forceOpen ? (
            <ChevronRight
              className={cn(
                "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
                effectiveOpen ? "rotate-90" : "",
              )}
            />
          ) : (
            <span className="h-3.5 w-3.5 shrink-0" />
          )}
          <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {title}
          </span>
          {badge}
        </CollapsibleTrigger>
        {trailing ? <div className="shrink-0">{trailing}</div> : null}
      </div>
      <CollapsibleContent className="px-3 pb-3">{mounted ? children : null}</CollapsibleContent>
    </Collapsible>
  );
};
