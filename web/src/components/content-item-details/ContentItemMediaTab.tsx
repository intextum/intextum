import { TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { MediaGallery } from "./MediaGallery";
import { type ExtractedAssetsResponse, type ExtractedAsset } from "@/dataProvider";

interface ContentItemMediaTabProps {
  extractedData: ExtractedAssetsResponse | null;
  extractedLoading: boolean;
  onSelectAsset: (asset: ExtractedAsset) => void;
  value?: string;
  embedded?: boolean;
}

export const ContentItemMediaTab = ({
  extractedData,
  extractedLoading,
  onSelectAsset,
  value = "media",
  embedded = false,
}: ContentItemMediaTabProps) => {
  const content = (
    <>
      {extractedLoading ? (
        <div className="h-full flex items-center justify-center p-8">
          <Skeleton className="h-48 w-full rounded-lg" />
        </div>
      ) : (
        <MediaGallery
          figures={extractedData?.figures || []}
          tables={extractedData?.tables || []}
          onSelect={onSelectAsset}
        />
      )}
    </>
  );

  if (embedded) {
    return <div className="flex h-full min-h-0 flex-1 overflow-hidden">{content}</div>;
  }

  return (
    <TabsContent value={value} className="m-0 h-full min-h-0 overflow-hidden">
      {content}
    </TabsContent>
  );
};
