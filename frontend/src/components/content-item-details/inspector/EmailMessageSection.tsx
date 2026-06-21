import { Calendar, Info, Mail, Paperclip } from "lucide-react";
import type { ContentItemInfo } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { formatDate } from "@/lib/content-utils";
import { RailRow } from "./RailRow";

interface EmailMessageSectionProps {
  file: ContentItemInfo;
}

export const EmailMessageSection = ({ file }: EmailMessageSectionProps) => {
  const translate = useTranslate();
  const details = file.email_message_details;
  if (!details) return null;

  const sender =
    details.from_name && details.from_address
      ? `${details.from_name} <${details.from_address}>`
      : details.from_name || details.from_address || "-";

  return (
    <div className="divide-y rounded-md border bg-background/40 px-3 py-1">
      <RailRow
        icon={Info}
        label={translate("custom.content.details.subject")}
        value={details.subject || "-"}
      />
      {details.from_name || details.from_address ? (
        <RailRow icon={Mail} label={translate("custom.content.details.sender")} value={sender} />
      ) : null}
      {details.to_addresses.length > 0 ? (
        <RailRow
          icon={Mail}
          label={translate("custom.content.details.recipients")}
          value={details.to_addresses.join(", ")}
        />
      ) : null}
      {details.sent_at ? (
        <RailRow
          icon={Calendar}
          label={translate("custom.content.details.sent_at")}
          value={formatDate(details.sent_at)}
        />
      ) : null}
      {details.received_at ? (
        <RailRow
          icon={Calendar}
          label={translate("custom.content.details.received_at")}
          value={formatDate(details.received_at)}
        />
      ) : null}
      <RailRow
        icon={Paperclip}
        label={translate("custom.content.details.has_attachments")}
        value={
          details.has_attachments ? translate("ra.boolean.true") : translate("ra.boolean.false")
        }
      />
      {details.thread_id ? (
        <RailRow
          icon={Info}
          label={translate("custom.content.details.thread_id")}
          value={details.thread_id}
        />
      ) : null}
      {details.message_id_header ? (
        <RailRow
          icon={Info}
          label={translate("custom.content.details.message_id")}
          value={details.message_id_header}
        />
      ) : null}
    </div>
  );
};
