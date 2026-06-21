import { lazy, Suspense } from "react";
import { useTranslate } from "@/lib/app-context";
import { Eye, Music, File as FileIcon, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DoclingPreview } from "./DoclingPreview";
import { TextPreview } from "./TextPreview";
import { AudioTranscriptPreview } from "./AudioTranscriptPreview";
import { ExcelPreview } from "./ExcelPreview";
import { DocxPreview } from "./DocxPreview";
import { MarkdownPreview } from "./MarkdownPreview";
import { type ContentItemInfo } from "@/dataProvider";
import { getPreviewType, isExcelFile, isDocxFile, isMarkdownFile } from "@/lib/content-utils";

const PdfPreview = lazy(async () => {
  const module = await import("./PdfPreview");
  return { default: module.PdfPreview };
});

interface ContentItemPreviewProps {
  file: ContentItemInfo;
  doclingAvailable: boolean | null;
  activePreview: "parsed" | "original";
  previewError: boolean;
  previewUrl: string;
  highlightRefs?: string;
  docData?: unknown; // Shared doc data when already loaded by parent
  pdfToolbarTarget?: HTMLElement | null;
  useExternalPdfToolbar?: boolean;
  pdfPagesInitiallyOpen?: boolean;
  pdfPagesOpenStorageKey?: string;
  onPreviewError: (error: boolean) => void;
}

export const ContentItemPreview = ({
  file,
  doclingAvailable,
  activePreview,
  previewError,
  previewUrl,
  highlightRefs,
  docData,
  pdfToolbarTarget,
  useExternalPdfToolbar = false,
  pdfPagesInitiallyOpen = true,
  pdfPagesOpenStorageKey,
  onPreviewError,
}: ContentItemPreviewProps) => {
  const translate = useTranslate();
  const previewType = getPreviewType(file.extension);
  const isExcel = isExcelFile(file.extension);
  const isDocx = isDocxFile(file.extension);
  const isMarkdown = isMarkdownFile(file.extension);

  return (
    <main className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden border-b bg-background xl:border-b-0 xl:border-r">
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {isExcel ? (
          <ExcelPreview url={previewUrl} onError={onPreviewError} />
        ) : isDocx ? (
          <DocxPreview url={previewUrl} onError={onPreviewError} />
        ) : doclingAvailable &&
          activePreview === "parsed" &&
          (previewType === "pdf" || previewType === "document" || previewType === "image") ? (
          <DoclingPreview
            filePath={file.path}
            highlightItems={highlightRefs}
            initialDocData={docData}
          />
        ) : doclingAvailable && activePreview === "parsed" && previewType === "audio" ? (
          <AudioTranscriptPreview
            key={`${file.path}:${file.processed_at ?? ""}`}
            filePath={file.path}
            previewUrl={previewUrl}
          />
        ) : previewError ? (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-4">
            <Eye className="h-12 w-12 opacity-20" />
            <p>{translate("custom.content.preview.not_available")}</p>
          </div>
        ) : activePreview === "original" && previewType === "document" ? (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-6 p-12 text-center">
            <div className="p-6 bg-muted/30 rounded-2xl border border-dashed">
              <FileIcon className="h-16 w-16 opacity-20 mb-4 mx-auto" />
              <h3 className="text-lg font-medium text-foreground mb-2">
                {translate("custom.content.preview.no_native_preview", {
                  extension: file.extension?.toUpperCase() || "this",
                })}
              </h3>
              <p className="text-sm max-w-xs mx-auto mb-6">
                {translate("custom.content.preview.download_to_view")}
              </p>
              <Button
                onClick={() => window.open(previewUrl, "_blank")}
                className="shadow-lg hover:shadow-xl transition-all"
              >
                <Download className="h-4 w-4 mr-2" />
                {translate("custom.content.actions.download_original")}
              </Button>
            </div>
          </div>
        ) : previewType === "pdf" ? (
          <Suspense
            fallback={
              <PdfPreviewFallback label={translate("custom.content.preview.pdf_loading")} />
            }
          >
            <PdfPreview
              key={previewUrl}
              url={previewUrl}
              toolbarPortalTarget={pdfToolbarTarget}
              useExternalToolbar={useExternalPdfToolbar}
              pagesInitiallyOpen={pdfPagesInitiallyOpen}
              pagesOpenStorageKey={pdfPagesOpenStorageKey}
              onError={onPreviewError}
            />
          </Suspense>
        ) : previewType === "image" ? (
          <div className="flex h-full min-h-0 items-center justify-center overflow-hidden p-8">
            <img
              src={previewUrl}
              alt={file.name}
              className="max-h-full max-w-full object-contain shadow-lg"
              onError={() => onPreviewError(true)}
            />
          </div>
        ) : previewType === "video" ? (
          <div className="h-full flex items-center justify-center p-4 bg-black/5">
            <video
              src={previewUrl}
              controls
              className="max-w-full max-h-full rounded shadow-lg"
              onError={() => onPreviewError(true)}
            >
              Your browser does not support the video tag.
            </video>
          </div>
        ) : previewType === "audio" ? (
          <div className="h-full flex items-center justify-center p-8 bg-black/5">
            <div className="w-full max-w-md p-6 bg-background rounded-xl shadow-lg border flex flex-col items-center gap-4">
              <div className="p-4 bg-primary/10 rounded-full">
                <Music className="h-8 w-8 text-primary" />
              </div>
              <p className="text-sm font-medium truncate w-full text-center">{file.name}</p>
              <audio
                src={previewUrl}
                controls
                className="w-full"
                onError={() => onPreviewError(true)}
              >
                Your browser does not support the audio tag.
              </audio>
            </div>
          </div>
        ) : previewType === "text" && isMarkdown ? (
          <MarkdownPreview url={previewUrl} onError={() => onPreviewError(true)} />
        ) : previewType === "text" ? (
          <TextPreview url={previewUrl} onError={() => onPreviewError(true)} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-4">
            <FileIcon className="h-12 w-12 opacity-20" />
            <p>{translate("custom.content.preview.no_preview", { extension: file.extension })}</p>
          </div>
        )}
      </div>
    </main>
  );
};

const PdfPreviewFallback = ({ label }: { label: string }) => (
  <div className="flex h-full min-h-0 items-center justify-center bg-muted/20 text-sm text-muted-foreground">
    {label}
  </div>
);
