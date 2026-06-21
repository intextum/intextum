import { useEffect, useState } from "react";
import { MessageResponse } from "@/components/ai-elements/message";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTranslate } from "@/lib/app-context";

interface MarkdownPreviewProps {
  url: string;
  onError: () => void;
}

const MAX_PREVIEW_CHARS = 50000;

export const MarkdownPreview = ({ url, onError }: MarkdownPreviewProps) => {
  const translate = useTranslate();
  const [content, setContent] = useState<string | null>(null);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);

  const loading = loadedUrl !== url;

  useEffect(() => {
    let cancelled = false;

    fetch(url, { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load");
        return res.text();
      })
      .then((text) => {
        if (cancelled) {
          return;
        }
        setContent(
          text.length > MAX_PREVIEW_CHARS
            ? `${text.substring(0, MAX_PREVIEW_CHARS)}\n\n... ${translate(
                "custom.content.preview.truncated",
              )}`
            : text,
        );
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setContent(null);
        onError();
      })
      .finally(() => {
        if (!cancelled) {
          setLoadedUrl(url);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [url, onError, translate]);

  if (loading) return <Skeleton className="h-full w-full p-4" />;

  return (
    <Tabs defaultValue="rendered" className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center border-b px-3">
        <TabsList className="h-8 bg-muted/70">
          <TabsTrigger value="rendered" className="h-7 text-xs">
            {translate("custom.content.preview.markdown_rendered")}
          </TabsTrigger>
          <TabsTrigger value="source" className="h-7 text-xs">
            {translate("custom.content.preview.markdown_source")}
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="rendered" className="m-0 min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full w-full">
          <div className="mx-auto max-w-4xl px-8 py-7">
            <MessageResponse className="text-sm leading-7">{content ?? ""}</MessageResponse>
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="source" className="m-0 min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full w-full bg-muted/20">
          <pre className="p-6 font-mono text-xs whitespace-pre-wrap break-words">{content}</pre>
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
};
