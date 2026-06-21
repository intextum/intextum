import { useState, useEffect } from "react";
import { useTranslate } from "@/lib/app-context";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";

interface TextPreviewProps {
  url: string;
  onError: () => void;
}

export const TextPreview = ({ url, onError }: TextPreviewProps) => {
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
          text.length > 50000
            ? text.substring(0, 50000) + "\n\n... " + translate("custom.content.preview.truncated")
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
    <ScrollArea className="h-full w-full bg-muted/20">
      <pre className="p-6 text-xs font-mono whitespace-pre-wrap break-words">{content}</pre>
    </ScrollArea>
  );
};
