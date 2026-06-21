import type { ReactNode } from "react";

interface RailRowProps {
  icon?: React.ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
}

export const RailRow = ({ icon: Icon, label, value }: RailRowProps) => (
  <div className="flex items-baseline justify-between gap-3 py-1.5 text-xs">
    <span className="inline-flex shrink-0 items-center gap-1.5 text-muted-foreground">
      {Icon ? <Icon className="h-3 w-3" /> : null}
      {label}
    </span>
    <span className="min-w-0 break-words text-right font-mono text-[11px]">{value}</span>
  </div>
);
