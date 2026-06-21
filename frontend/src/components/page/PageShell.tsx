import type { ReactNode } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface PageShellProps {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  scroll?: boolean;
}

export function PageShell({
  children,
  className,
  contentClassName,
  scroll = true,
}: PageShellProps) {
  const content = (
    <div className={cn("mx-auto w-full max-w-7xl space-y-6 p-4 md:p-6", contentClassName)}>
      {children}
    </div>
  );

  if (!scroll) {
    return <div className={cn("h-full bg-background", className)}>{content}</div>;
  }

  return <ScrollArea className={cn("h-full bg-background", className)}>{content}</ScrollArea>;
}
