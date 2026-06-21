import type { ComponentType, ReactNode } from "react";

import { cn } from "@/lib/utils";

interface PageHeaderProps {
  icon?: ComponentType<{ className?: string }>;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  icon: Icon,
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn("flex flex-col gap-4 md:flex-row md:items-start md:justify-between", className)}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex min-w-0 items-center gap-2">
          {Icon ? <Icon className="h-5 w-5 shrink-0 text-muted-foreground" /> : null}
          <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
        </div>
        {description ? (
          <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
