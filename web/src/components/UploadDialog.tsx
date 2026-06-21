import { useState, useCallback } from "react";
import { useTranslate, useNotify } from "@/lib/app-context";
import { useDropzone } from "react-dropzone";
import { Upload, X, CheckCircle, XCircle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { contentApi } from "@/dataProvider";

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPath: string;
  onSuccess: () => void;
}

type FileStatus = "pending" | "uploading" | "done" | "error";

interface TrackedFile {
  file: File;
  status: FileStatus;
  error?: string;
}

export const UploadDialog = ({ open, onOpenChange, currentPath, onSuccess }: UploadDialogProps) => {
  const translate = useTranslate();
  const notify = useNotify();
  const [files, setFiles] = useState<TrackedFile[]>([]);
  const [uploading, setUploading] = useState(false);

  const onDrop = useCallback((accepted: File[]) => {
    setFiles((prev) => [
      ...prev,
      ...accepted.map((file) => ({ file, status: "pending" as FileStatus })),
    ]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (files.length === 0) return;
    setUploading(true);

    let successCount = 0;
    for (let i = 0; i < files.length; i++) {
      const tracked = files[i];
      if (tracked.status === "done") {
        successCount++;
        continue;
      }

      setFiles((prev) => prev.map((f, idx) => (idx === i ? { ...f, status: "uploading" } : f)));

      try {
        await contentApi.upload(currentPath, tracked.file);
        setFiles((prev) => prev.map((f, idx) => (idx === i ? { ...f, status: "done" } : f)));
        successCount++;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setFiles((prev) =>
          prev.map((f, idx) => (idx === i ? { ...f, status: "error", error: message } : f)),
        );
        notify(translate("custom.content.upload.failed", { name: tracked.file.name }), {
          type: "error",
        });
      }
    }

    if (successCount > 0) {
      notify(translate("custom.content.upload.success", { count: successCount }), {
        type: "success",
      });
      onSuccess();
    }

    setUploading(false);

    // Close if all succeeded
    if (successCount === files.length) {
      setFiles([]);
      onOpenChange(false);
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && !uploading) {
      setFiles([]);
    }
    if (!uploading) {
      onOpenChange(nextOpen);
    }
  };

  const displayPath = currentPath || "/";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{translate("custom.content.upload.title")}</DialogTitle>
          <DialogDescription>
            {translate("custom.content.upload.description", {
              directory: displayPath,
            })}
          </DialogDescription>
        </DialogHeader>

        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            isDragActive
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-muted-foreground/50"
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {isDragActive
              ? translate("custom.content.upload.dropzone_active")
              : translate("custom.content.upload.dropzone")}
          </p>
        </div>

        {files.length > 0 && (
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {files.map((tracked, i) => (
              <div
                key={`${tracked.file.name}-${i}`}
                className="flex items-center gap-2 text-sm px-2 py-1 rounded bg-muted/50"
              >
                {tracked.status === "pending" && <div className="h-4 w-4 shrink-0" />}
                {tracked.status === "uploading" && (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                )}
                {tracked.status === "done" && (
                  <CheckCircle className="h-4 w-4 shrink-0 text-green-600" />
                )}
                {tracked.status === "error" && (
                  <XCircle className="h-4 w-4 shrink-0 text-red-500" />
                )}
                <span className="truncate flex-1">{tracked.file.name}</span>
                {tracked.status === "pending" && !uploading && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(i);
                    }}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={uploading || files.length === 0 || files.every((f) => f.status === "done")}
          >
            {uploading
              ? translate("custom.content.upload.uploading")
              : translate("custom.content.upload.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
