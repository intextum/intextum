import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface PageToolbarProps {
  children: ReactNode;
  className?: string;
}

export function PageToolbar({ children, className }: PageToolbarProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card/70 p-3 shadow-sm md:flex-row md:items-center md:justify-between",
        className,
      )}
    >
      {children}
    </div>
  );
}
