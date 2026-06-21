import { useState } from "react";
import {
  AlertCircle,
  Cog,
  Database,
  Image,
  Info,
  Link2,
  ListChecks,
  Mail,
  MessageSquare,
  Paperclip,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  type ContentItemInfo,
  type ContentReviewSubmitPayload,
  type ExtractedAsset,
  type ExtractedAssetsResponse,
} from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { cn } from "@/lib/utils";
import { ContentItemMediaTab } from "../ContentItemMediaTab";
import { AttachmentSection } from "./AttachmentSection";
import { ContentItemChatTab } from "./ContentItemChatTab";
import { DataPane } from "./DataPane";
import { EmailMessageSection } from "./EmailMessageSection";
import { FileInfoSection } from "./FileInfoSection";
import { ProcessingInfoSection } from "./ProcessingInfoSection";
import { RailSection } from "./RailSection";
import { RelationshipsSection } from "./RelationshipsSection";

export type InfoTab = "chat" | "data" | "info" | "media";

interface InfoPaneProps {
  file: ContentItemInfo;
  activeTab: InfoTab;
  onTabChange: (tab: InfoTab) => void;
  savingEnrichment: boolean;
  onSubmitReview?: (payload: ContentReviewSubmitPayload) => Promise<unknown>;
  onVerifyClass?: (classificationLabel: string) => Promise<unknown>;
  onNavigateToEvidence?: (docRefs: string[], label: string) => void;
  onOpenRelatedItem?: (path: string) => void | Promise<void>;
  extractedData: ExtractedAssetsResponse | null;
  extractedLoading: boolean;
  onSelectAsset: (asset: ExtractedAsset) => void;
  dataNeedsAttention: boolean;
  onRerunEnrichment?: () => void;
}

const SECTION_PREFIX = "rail.section.";

const initialTabsMounted = (tab: InfoTab): Record<InfoTab, boolean> => ({
  chat: tab === "chat",
  data: tab === "data",
  info: tab === "info",
  media: tab === "media",
});

export const InfoPane = ({
  file,
  activeTab,
  onTabChange,
  savingEnrichment,
  onSubmitReview,
  onVerifyClass,
  onNavigateToEvidence,
  onOpenRelatedItem,
  extractedData,
  extractedLoading,
  onSelectAsset,
  dataNeedsAttention,
  onRerunEnrichment,
}: InfoPaneProps) => {
  const translate = useTranslate();
  const hasRelationships = Boolean(file.parent_item) || (file.child_items?.length ?? 0) > 0;
  const hasEmail = Boolean(file.email_message_details);
  const hasAttachment = Boolean(file.attachment_details);
  const hasProcessingInfo = Boolean(
    file.processed_at ||
    file.processed_by ||
    file.processing_duration_ms != null ||
    file.processing_mode,
  );
  const figureCount = extractedData?.figures?.length ?? 0;
  const tableCount = extractedData?.tables?.length ?? 0;
  const assetCount = figureCount + tableCount;
  const showMedia = file.kind !== "folder" && assetCount > 0;
  const showChat = file.kind !== "folder";
  const showData =
    file.kind !== "folder" &&
    (Boolean(file.capabilities?.supports_review) ||
      Boolean(file.document_classification) ||
      Boolean(file.document_extraction));

  const [tabsMounted, setTabsMounted] = useState<Record<InfoTab, boolean>>(() =>
    initialTabsMounted(activeTab),
  );
  if (!tabsMounted[activeTab]) {
    setTabsMounted({ ...tabsMounted, [activeTab]: true });
  }

  const selectTab = (next: string) => {
    onTabChange(next as InfoTab);
  };

  const DataIcon = file.document_classification ? Database : ListChecks;

  const countBadge = (count: number) =>
    count > 0 ? (
      <span className="ml-1 rounded bg-muted px-1 font-mono text-[10px] text-muted-foreground">
        {count}
      </span>
    ) : null;

  const attentionDot = (
    <span className="ml-1 inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
  );

  return (
    <Tabs
      value={activeTab}
      onValueChange={selectTab}
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
    >
      <div className="flex min-w-0 shrink-0 items-center border-b bg-background px-2 py-1">
        <div className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <TabsList
            variant="line"
            className="h-8 min-w-max justify-start gap-3 rounded-none border-b-0"
          >
            {showChat ? (
              <TabsTrigger value="chat" className="h-8 gap-1.5 px-1.5 text-xs">
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                {translate("custom.content.chat.title", { defaultValue: "Chat" })}
              </TabsTrigger>
            ) : null}
            {showData ? (
              <TabsTrigger
                value="data"
                className={cn(
                  "h-8 gap-1.5 px-1.5 text-xs",
                  dataNeedsAttention && "text-amber-900 dark:text-amber-200",
                )}
              >
                {dataNeedsAttention ? (
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                ) : (
                  <DataIcon className="h-3.5 w-3.5 shrink-0" />
                )}
                {translate("custom.content.details.document_data", {
                  defaultValue: "Data",
                })}
                {dataNeedsAttention ? attentionDot : null}
              </TabsTrigger>
            ) : null}
            <TabsTrigger value="info" className="h-8 gap-1.5 px-1.5 text-xs">
              <Info className="h-3.5 w-3.5 shrink-0" />
              {translate("custom.content.details.general_info")}
            </TabsTrigger>
            {showMedia ? (
              <TabsTrigger value="media" className="h-8 gap-1.5 px-1.5 text-xs">
                <Image className="h-3.5 w-3.5 shrink-0" />
                {translate("custom.content.tabs.media")}
                {countBadge(assetCount)}
              </TabsTrigger>
            ) : null}
          </TabsList>
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-muted/5">
        {showChat ? (
          <div hidden={activeTab !== "chat"} className="h-full">
            {tabsMounted.chat ? (
              <ContentItemChatTab
                file={file}
                onNavigateToEvidence={onNavigateToEvidence}
                onOpenRelatedItem={onOpenRelatedItem}
              />
            ) : null}
          </div>
        ) : null}
        {showData ? (
          <div hidden={activeTab !== "data"} className="h-full">
            {tabsMounted.data ? (
              <DataPane
                file={file}
                savingEnrichment={savingEnrichment}
                onSubmitReview={onSubmitReview}
                onVerifyClass={onVerifyClass}
                onNavigateToEvidence={onNavigateToEvidence}
                onRerunEnrichment={onRerunEnrichment}
              />
            ) : null}
          </div>
        ) : null}
        <div hidden={activeTab !== "info"} className="h-full">
          {tabsMounted.info ? (
            <ScrollArea className="h-full">
              <div className="flex flex-col">
                <RailSection
                  id="rail-section-file-info"
                  icon={Info}
                  title={translate("custom.content.details.general_info")}
                  forceOpen
                >
                  <FileInfoSection file={file} />
                </RailSection>

                {hasRelationships ? (
                  <RailSection
                    id="rail-section-relationships"
                    icon={Link2}
                    title={translate("custom.content.details.relationships")}
                    storageKey={`${SECTION_PREFIX}relationships`}
                  >
                    <RelationshipsSection file={file} onOpenRelatedItem={onOpenRelatedItem} />
                  </RailSection>
                ) : null}

                {hasEmail ? (
                  <RailSection
                    id="rail-section-email"
                    icon={Mail}
                    title={translate("custom.content.details.message_info")}
                    storageKey={`${SECTION_PREFIX}email`}
                  >
                    <EmailMessageSection file={file} />
                  </RailSection>
                ) : null}

                {hasAttachment ? (
                  <RailSection
                    id="rail-section-attachment"
                    icon={Paperclip}
                    title={translate("custom.content.details.attachment_info")}
                    storageKey={`${SECTION_PREFIX}attachment`}
                  >
                    <AttachmentSection file={file} />
                  </RailSection>
                ) : null}

                {hasProcessingInfo ? (
                  <RailSection
                    id="rail-section-processing"
                    icon={Cog}
                    title={translate("custom.content.details.processing_info")}
                    forceOpen
                  >
                    <ProcessingInfoSection file={file} />
                  </RailSection>
                ) : null}
              </div>
            </ScrollArea>
          ) : null}
        </div>
        {showMedia ? (
          <div hidden={activeTab !== "media"} className="h-full">
            {tabsMounted.media ? (
              <ContentItemMediaTab
                embedded
                extractedData={extractedData}
                extractedLoading={extractedLoading}
                onSelectAsset={onSelectAsset}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </Tabs>
  );
};
