import { Info, Mail, Paperclip } from "lucide-react";
import type { ContentItemInfo } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { RailRow } from "./RailRow";

interface AttachmentSectionProps {
  file: ContentItemInfo;
}

export const AttachmentSection = ({ file }: AttachmentSectionProps) => {
  const translate = useTranslate();
  const details = file.attachment_details;
  if (!details) return null;

  return (
    <div className="divide-y rounded-md border bg-background/40 px-3 py-1">
      {details.disposition ? (
        <RailRow
          icon={Info}
          label={translate("custom.content.details.attachment_disposition")}
          value={details.disposition}
        />
      ) : null}
      <RailRow
        icon={Paperclip}
        label={translate("custom.content.details.inline_attachment")}
        value={details.is_inline ? translate("ra.boolean.true") : translate("ra.boolean.false")}
      />
      {details.email_message_content_item_id ? (
        <RailRow
          icon={Mail}
          label={translate("custom.content.details.parent_email")}
          value={details.email_message_content_item_id}
        />
      ) : null}
      {details.content_id_header ? (
        <RailRow
          icon={Info}
          label={translate("custom.content.details.content_id_header")}
          value={details.content_id_header}
        />
      ) : null}
    </div>
  );
};
