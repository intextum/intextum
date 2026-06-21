import { Calendar, Clock, File, HardDrive, Info } from "lucide-react";
import type { ContentItemInfo } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { formatDate, formatDuration } from "@/lib/content-utils";
import { getFileProcessingModeTranslationKey } from "@/lib/content-processing";

interface FileInfoSectionProps {
  file: ContentItemInfo;
}

const Row = ({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) => (
  <div className="flex items-baseline justify-between gap-3 py-1.5 text-xs">
    <span className="inline-flex shrink-0 items-center gap-1.5 text-muted-foreground">
      <Icon className="h-3 w-3" />
      {label}
    </span>
    <span className="min-w-0 break-words text-right font-mono text-[11px]">{value}</span>
  </div>
);

export const FileInfoSection = ({ file }: FileInfoSectionProps) => {
  const translate = useTranslate();
  const processingModeKey = getFileProcessingModeTranslationKey(file.processing_mode);

  return (
    <div className="divide-y rounded-md border bg-background/40">
      <div className="px-3 py-1">
        <Row
          icon={HardDrive}
          label={translate("custom.content.details.size")}
          value={file.size_human}
        />
        <Row
          icon={File}
          label={translate("custom.content.details.type")}
          value={translate(`custom.content.details.kind_${file.kind}`, {
            defaultValue: file.extension ?? file.kind ?? "-",
          })}
        />
        {file.mime_type ? (
          <Row
            icon={Info}
            label={translate("custom.content.details.mime_type")}
            value={file.mime_type}
          />
        ) : null}
      </div>
      <div className="px-3 py-1">
        <Row
          icon={Calendar}
          label={translate("custom.content.details.modified")}
          value={formatDate(file.modified_at)}
        />
        {file.processed_at ? (
          <Row
            icon={Clock}
            label={translate("custom.content.details.processed_at")}
            value={formatDate(file.processed_at)}
          />
        ) : null}
        {file.processing_duration_ms != null ? (
          <Row
            icon={Clock}
            label={translate("custom.content.details.duration")}
            value={formatDuration(file.processing_duration_ms)}
          />
        ) : null}
        {processingModeKey ? (
          <Row
            icon={Info}
            label={translate("custom.content.details.processing_mode")}
            value={translate(processingModeKey)}
          />
        ) : null}
      </div>
    </div>
  );
};
