import { useCallback, useState } from "react";
import { Download, FileText, LoaderCircle } from "lucide-react";
import { useNotify } from "@/lib/app-context";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { exportsApi } from "@/dataProvider";
import {
  buildDocxExportPayload,
  downloadBlob,
  downloadMarkdownExportDocument,
  type ExportDocument,
} from "@/lib/chat-export";
import { reportClientError } from "@/lib/report-client-error";

interface ResponseExportMenuProps {
  document: ExportDocument;
  triggerLabel?: string;
  translate: (key: string, options?: unknown) => string;
}

export const ResponseExportMenu = ({
  document,
  triggerLabel,
  translate,
}: ResponseExportMenuProps) => {
  const notify = useNotify();
  const [isExportingDocx, setIsExportingDocx] = useState(false);
  const resolvedTriggerLabel = triggerLabel ?? translate("custom.exports.trigger");

  const handleMarkdownExport = useCallback(() => {
    try {
      downloadMarkdownExportDocument(document);
    } catch (error) {
      reportClientError(error, undefined, { routeName: "chat:export:markdown" });
      notify(
        translate("custom.exports.markdown_failed", {
          _: "Failed to export Markdown.",
        }),
        { type: "error" },
      );
    }
  }, [document, notify, translate]);

  const handleDocxExport = useCallback(async () => {
    setIsExportingDocx(true);
    try {
      const blob = await exportsApi.exportDocx(await buildDocxExportPayload(document));
      downloadBlob(`${document.filenameBase}.docx`, blob);
    } catch (error) {
      reportClientError(error, undefined, { routeName: "chat:export:docx" });
      notify(
        translate("custom.exports.docx_failed", {
          _: "Failed to export Word document.",
        }),
        { type: "error" },
      );
    } finally {
      setIsExportingDocx(false);
    }
  }, [document, notify, translate]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          title={resolvedTriggerLabel}
          aria-label={resolvedTriggerLabel}
        >
          {isExportingDocx ? <LoaderCircle className="animate-spin" /> : <Download />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => handleMarkdownExport()}>
          <FileText />
          {translate("custom.exports.markdown")}
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={isExportingDocx}
          onSelect={() => {
            void handleDocxExport();
          }}
        >
          {isExportingDocx ? <LoaderCircle className="animate-spin" /> : <Download />}
          {translate("custom.exports.docx")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
