import { type ComponentProps } from "react";

import { ContentListView } from "@/components/ContentListView";

interface ContentPageContentProps {
  allFilesViewProps: ComponentProps<typeof ContentListView>;
}

export function ContentPageContent({ allFilesViewProps }: ContentPageContentProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1">
        <ContentListView {...allFilesViewProps} />
      </div>
    </div>
  );
}
