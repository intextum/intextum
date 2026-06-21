import { useTranslate } from "@/lib/app-context";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DocumentClassBadge } from "@/components/DocumentClassBadge";
import { type ContentItemInfo } from "@/dataProvider";
import { getFileProcessingModeTranslationKey } from "@/lib/content-processing";
import {
  formatDate,
  formatDuration,
  getContentItemDisplayName,
  getContentItemIcon,
  getContentRelationshipHint,
} from "@/lib/content-utils";

interface RecentFilesTableProps {
  files: ContentItemInfo[];
  onFileClick: (file: ContentItemInfo) => void;
}

export const RecentFilesTable = ({ files, onFileClick }: RecentFilesTableProps) => {
  const translate = useTranslate();

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{translate("custom.pages.dashboard.table.name")}</TableHead>
            <TableHead>{translate("custom.pages.dashboard.table.path")}</TableHead>
            <TableHead>{translate("custom.pages.dashboard.table.worker")}</TableHead>
            <TableHead className="text-right">
              {translate("custom.pages.dashboard.table.duration")}
            </TableHead>
            <TableHead className="text-right">
              {translate("custom.pages.dashboard.table.indexed_at")}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {files.map((file) => {
            const processingModeLabelKey = getFileProcessingModeTranslationKey(
              file.processing_mode,
            );
            const relationshipHint = getContentRelationshipHint(file, translate);

            return (
              <TableRow key={file.id} className="cursor-pointer" onClick={() => onFileClick(file)}>
                <TableCell className="whitespace-normal py-3 font-medium">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="shrink-0">{getContentItemIcon(file.kind, file.extension)}</div>
                    <div className="min-w-0">
                      <span
                        className="block max-w-[150px] truncate md:max-w-[300px]"
                        title={getContentItemDisplayName(file)}
                      >
                        {getContentItemDisplayName(file)}
                      </span>
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        <DocumentClassBadge
                          classification={file.document_classification}
                          classificationLifecycle={
                            file.document_enrichment?.classification_lifecycle
                          }
                          extractionLifecycle={file.document_enrichment?.extraction_lifecycle}
                          className="w-fit"
                        />
                        {processingModeLabelKey &&
                          file.processing_mode?.mode !== "full" &&
                          file.status === "COMPLETED" && (
                            <Badge variant="secondary" className="text-[10px]">
                              {translate(processingModeLabelKey)}
                            </Badge>
                          )}
                      </div>
                      {relationshipHint && (
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          {relationshipHint}
                        </div>
                      )}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs font-mono whitespace-normal">
                  <div className="truncate max-w-[100px] md:max-w-[250px]" title={file.path}>
                    {file.path}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs font-mono whitespace-normal">
                  {file.processed_by || "-"}
                </TableCell>
                <TableCell className="text-right text-muted-foreground text-sm">
                  {formatDuration(file.processing_duration_ms)}
                </TableCell>
                <TableCell className="text-right text-muted-foreground text-sm">
                  {formatDate(file.processed_at || file.modified_at)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
};
