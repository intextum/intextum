import { Images } from "lucide-react";
import { useTranslate } from "@/lib/app-context";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { contentApi, type ExtractedAsset } from "@/dataProvider";

interface MediaGalleryProps {
  figures: ExtractedAsset[];
  tables: ExtractedAsset[];
  onSelect?: (asset: ExtractedAsset) => void;
}

export const MediaGallery = ({ figures, tables, onSelect }: MediaGalleryProps) => {
  const translate = useTranslate();

  const hasMedia = figures.length > 0 || tables.length > 0;

  if (!hasMedia) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center p-8 text-muted-foreground">
        <Images className="h-12 w-12 opacity-20 mb-2" />
        <p className="text-sm">{translate("custom.content.media.no_media")}</p>
      </div>
    );
  }

  return (
    <Tabs defaultValue="figures" className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <div className="px-4 pt-2">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="figures" className="gap-2">
            {translate("custom.content.media.figures_title")}
            <Badge
              variant="secondary"
              className="h-4 px-1 text-[10px] min-w-[1.25rem] justify-center"
            >
              {figures.length}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="tables" className="gap-2">
            {translate("custom.content.media.tables_title")}
            <Badge
              variant="secondary"
              className="h-4 px-1 text-[10px] min-w-[1.25rem] justify-center"
            >
              {tables.length}
            </Badge>
          </TabsTrigger>
        </TabsList>
      </div>

      <div className="mt-2 min-h-0 flex-1 overflow-hidden">
        <TabsContent value="figures" className="m-0 h-full min-h-0 overflow-hidden">
          <ScrollArea className="h-full min-h-0">
            <div className="p-4 grid grid-cols-2 gap-4">
              {figures.map((asset) => (
                <Tooltip key={asset.path}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onSelect?.(asset)}
                      className="group relative aspect-square bg-muted rounded-lg border hover:border-muted-foreground/30 transition-all overflow-hidden shadow-sm hover:shadow-md"
                    >
                      <img
                        src={contentApi.getExtractedAssetUrl(asset.path)}
                        alt={asset.name}
                        className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
                      />
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-visible:opacity-100 transition-opacity">
                        <p className="text-white text-[10px] truncate font-medium">{asset.name}</p>
                      </div>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p className="text-xs">{asset.name}</p>
                  </TooltipContent>
                </Tooltip>
              ))}
              {figures.length === 0 && (
                <div className="col-span-2 py-12 text-center text-sm text-muted-foreground">
                  {translate("custom.content.media.no_figures")}
                </div>
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="tables" className="m-0 h-full min-h-0 overflow-hidden">
          <ScrollArea className="h-full min-h-0">
            <div className="p-4 space-y-6">
              {tables.map((asset) => (
                <button
                  key={asset.path}
                  onClick={() => onSelect?.(asset)}
                  className="group relative aspect-video bg-muted rounded-lg border hover:border-muted-foreground/30 transition-all overflow-hidden shadow-sm hover:shadow-md w-full text-left"
                >
                  <div className="absolute inset-0 flex items-center justify-center bg-muted/50 group-hover:bg-muted/30 transition-colors">
                    <img
                      src={contentApi.getExtractedAssetUrl(asset.path)}
                      alt={asset.name}
                      className="max-w-full max-h-full object-contain"
                    />
                  </div>
                  <div className="absolute inset-x-0 bottom-0 bg-black/70 p-2 backdrop-blur-sm">
                    <span className="text-white text-xs truncate block font-medium">
                      {asset.name}
                    </span>
                  </div>
                </button>
              ))}
              {tables.length === 0 && (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  {translate("custom.content.media.no_tables")}
                </div>
              )}
            </div>
          </ScrollArea>
        </TabsContent>
      </div>
    </Tabs>
  );
};
