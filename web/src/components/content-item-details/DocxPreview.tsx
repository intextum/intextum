import { useState, useEffect, useRef } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { reportClientError } from "@/lib/report-client-error";

interface DocxPreviewProps {
  url: string;
  onError: (error: boolean) => void;
}

export const DocxPreview = ({ url, onError }: DocxPreviewProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDocx = async () => {
      if (!containerRef.current) return;
      try {
        setLoading(true);
        const { renderAsync } = await import("docx-preview");
        const response = await fetch(url);
        if (!response.ok) throw new Error("Failed to fetch file");

        const arrayBuffer = await response.arrayBuffer();
        containerRef.current.innerHTML = "";
        await renderAsync(arrayBuffer, containerRef.current, undefined, {
          className: "docx-preview-wrapper",
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: true,
        });
      } catch (error) {
        reportClientError(error, undefined, { routeName: "preview:docx" });
        onError(true);
      } finally {
        setLoading(false);
      }
    };

    loadDocx();
  }, [url, onError]);

  return (
    <div className="h-full w-full bg-background overflow-auto">
      {loading && <Skeleton className="w-full h-full" />}
      <div ref={containerRef} className={loading ? "hidden" : ""} />
      <style>{`
                .docx-preview-wrapper {
                    padding: 16px;
                    background: hsl(var(--background));
                }
                .docx-preview-wrapper .docx-wrapper {
                    background: hsl(var(--background));
                }
                .docx-preview-wrapper .docx-wrapper > section.docx {
                    box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
                    margin-bottom: 16px;
                }
            `}</style>
    </div>
  );
};
