import type { ComponentType, ReactNode } from "react";

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: ComponentType<{ className?: string }>;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  children,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 px-6 py-12 text-center",
        className,
      )}
    >
      {Icon ? (
        <div className="mb-4 rounded-full bg-background p-3 shadow-sm">
          <Icon className="h-7 w-7 text-muted-foreground" />
        </div>
      ) : null}
      <h3 className="text-sm font-medium">{title}</h3>
      {description ? (
        <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      ) : null}
      {actions ? (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{actions}</div>
      ) : null}
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}
