import { useCallback, useState } from "react";
import { contentApi, type ContentItemInfo } from "@/dataProvider";
import { reportClientError } from "@/lib/report-client-error";

type TranslateFn = (key: string, options?: unknown) => string;
type NotifyFn = (
  message: string,
  options?: { type?: "info" | "success" | "warning" | "error" },
) => void;

export function useChatSourceDetails({
  notify,
  translate,
}: {
  notify: NotifyFn;
  translate: TranslateFn;
}) {
  const [selectedFile, setSelectedFile] = useState<ContentItemInfo | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [highlightRefs, setHighlightRefs] = useState<string[] | undefined>(undefined);

  const handleSourceClick = useCallback(
    async (filePath: string, docRefs?: string[]) => {
      try {
        const fileInfo = await contentApi.getDetails(filePath);
        setSelectedFile(fileInfo);
        setHighlightRefs(docRefs);
        setDetailsOpen(true);
      } catch (error) {
        reportClientError(error, undefined, { routeName: "chat:source-details" });
        notify(translate("custom.pages.search.failed_to_load_details"), { type: "error" });
      }
    },
    [notify, translate],
  );

  return {
    detailsOpen,
    handleSourceClick,
    highlightRefs,
    selectedFile,
    setDetailsOpen,
  };
}
