import { useTranslate } from "@/lib/app-context";
import { Badge } from "@/components/ui/badge";
import { contentApi, type ChunkInfo } from "@/dataProvider";
import { cn } from "@/lib/utils";

interface ChunkItemProps {
  chunk: ChunkInfo;
  rootPath?: string;
  highlighted?: boolean;
}

export const ChunkItem = ({ chunk, rootPath, highlighted = false }: ChunkItemProps) => {
  const translate = useTranslate();
  const getImageUrl = (img: string) => {
    if (img.startsWith("http") || img.startsWith("data:")) return img;

    // If we have a root path (file_id) and the image path doesn't start with it, prepend it
    if (rootPath && !img.startsWith(rootPath)) {
      // Remove leading slash if present to avoid double slashes
      const cleanImg = img.startsWith("/") ? img.substring(1) : img;
      return contentApi.getExtractedAssetUrl(`${rootPath}/${cleanImg}`);
    }

    return contentApi.getExtractedAssetUrl(img);
  };

  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap gap-2">
        {chunk.page_numbers.length > 0 && (
          <Badge variant="secondary" className="text-[10px] h-4">
            P{chunk.page_numbers.join(", ")}
          </Badge>
        )}
        <Badge variant="outline" className="text-[10px] h-4">
          {translate("custom.content.chunks.words", { count: chunk.word_count })}
        </Badge>
        {chunk.doc_refs?.length > 0 && (
          <Badge variant="outline" className="text-[10px] h-4 font-mono">
            {translate("custom.content.chunks.refs", { count: chunk.doc_refs.length })}
          </Badge>
        )}
      </div>
      {chunk.headings.length > 0 && (
        <div className="text-muted-foreground text-[11px] font-medium leading-tight">
          {chunk.headings.join(" > ")}
        </div>
      )}
      <p
        className={cn(
          "text-muted-foreground whitespace-pre-wrap break-words rounded p-2 text-[11px] font-mono leading-relaxed transition-colors duration-500",
          highlighted ? "bg-primary/10 ring-1 ring-primary/20" : "bg-muted/50",
        )}
      >
        {chunk.text || translate("custom.content.preview.no_text")}
      </p>
      {chunk.images.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {chunk.images.map((img, i) => (
            <div key={i} className="relative group">
              <img
                src={getImageUrl(img)}
                alt={`Chunk image ${i}`}
                className="h-16 w-16 object-cover rounded border bg-background"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
