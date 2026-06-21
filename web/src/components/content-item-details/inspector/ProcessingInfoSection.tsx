import { Calendar, Clock, HardDrive, Pencil } from "lucide-react";
import type { ContentItemInfo } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { formatDate, formatDuration } from "@/lib/content-utils";
import { getFileProcessingModeTranslationKey } from "@/lib/content-processing";
import { RailRow } from "./RailRow";

interface ProcessingInfoSectionProps {
  file: ContentItemInfo;
}

export const ProcessingInfoSection = ({ file }: ProcessingInfoSectionProps) => {
  const translate = useTranslate();
  const processingModeKey = getFileProcessingModeTranslationKey(file.processing_mode);

  if (
    !file.processed_at &&
    !file.processed_by &&
    file.processing_duration_ms == null &&
    !processingModeKey
  ) {
    return null;
  }

  return (
    <div className="divide-y rounded-md border bg-background/40 px-3 py-1">
      {processingModeKey ? (
        <RailRow
          icon={Pencil}
          label={translate("custom.content.details.processing_mode")}
          value={translate(processingModeKey)}
        />
      ) : null}
      {file.processed_at ? (
        <RailRow
          icon={Calendar}
          label={translate("custom.content.details.processed_at")}
          value={formatDate(file.processed_at)}
        />
      ) : null}
      {file.processed_by ? (
        <RailRow
          icon={HardDrive}
          label={translate("custom.content.details.worker")}
          value={file.processed_by}
        />
      ) : null}
      {file.processing_duration_ms != null ? (
        <RailRow
          icon={Clock}
          label={translate("custom.content.details.duration")}
          value={formatDuration(file.processing_duration_ms)}
        />
      ) : null}
    </div>
  );
};
