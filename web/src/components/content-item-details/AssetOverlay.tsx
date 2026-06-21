import { useTranslate } from "@/lib/app-context";
import { Images, Table2, Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { contentApi, type ExtractedAsset } from "@/dataProvider";

interface AssetOverlayProps {
  asset: ExtractedAsset | null;
  onClose: () => void;
}

const formatClassification = (value: string): string =>
  value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

export const AssetOverlay = ({ asset, onClose }: AssetOverlayProps) => {
  const translate = useTranslate();

  if (!asset) return null;
  const assetUrl = contentApi.getExtractedAssetUrl(asset.path);
  const classification = asset.classification?.trim();
  const description = asset.description?.trim();

  return (
    <Dialog open={Boolean(asset)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex h-[min(90vh,860px)] w-[min(96vw,1100px)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(96vw,1100px)]">
        <DialogHeader className="border-b px-5 py-4 pr-12 text-left">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 space-y-1">
              <DialogTitle className="flex min-w-0 items-center gap-2 text-sm">
                {asset.type === "figure" ? (
                  <Images className="h-4 w-4 shrink-0" />
                ) : (
                  <Table2 className="h-4 w-4 shrink-0" />
                )}
                <span className="truncate">{asset.name}</span>
                {classification ? (
                  <Badge variant="secondary" className="shrink-0 font-normal">
                    {formatClassification(classification)}
                  </Badge>
                ) : null}
              </DialogTitle>
              <DialogDescription className="truncate font-mono text-xs">
                {asset.path}
              </DialogDescription>
              {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() => window.open(assetUrl, "_blank")}
            >
              <Download className="mr-2 h-3.5 w-3.5" />
              {translate("custom.content.actions.download")}
            </Button>
          </div>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 items-center justify-center bg-muted/20 p-5">
          <img
            src={assetUrl}
            alt={description || asset.name}
            className="max-h-full max-w-full rounded-md object-contain shadow-2xl"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};
