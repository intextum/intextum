import { useCallback, useEffect, useState } from "react";
import { ChevronRight, FolderPlus, Loader2, Plus } from "lucide-react";
import { useNotify } from "@/lib/app-context";
import { contentApi, type ContentItemInfo, type FolderInfo } from "@/dataProvider";
import { reportClientError } from "@/lib/report-client-error";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ContentListView } from "@/components/ContentListView";
import { ContentItemDetailsDialog } from "@/components/ContentItemDetailsDialog";

const MAX_FOLDER_FILES = 300;

interface ChatContextPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAddPaths: (paths: string[]) => void;
  translate: (key: string, options?: unknown) => string;
}

const formatPathName = (path: string): string => path.split("/").filter(Boolean).pop() || path;

export const ChatContextPickerDialog = ({
  open,
  onOpenChange,
  onAddPaths,
  translate,
}: ChatContextPickerDialogProps) => {
  const notify = useNotify();

  const [currentPath, setCurrentPath] = useState("");
  const [isAddingFolder, setIsAddingFolder] = useState<string | null>(null);

  // Details dialog state
  const [detailsFile, setDetailsFile] = useState<ContentItemInfo | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setCurrentPath("");
    }
  }, [open]);

  const breadcrumbPaths = currentPath
    .split("/")
    .filter(Boolean)
    .map((_, index, parts) => parts.slice(0, index + 1).join("/"));

  const handleAddFile = useCallback(
    (filePath: string) => {
      onAddPaths([filePath]);
    },
    [onAddPaths],
  );

  const collectFolderFiles = useCallback(async (folderPath: string) => {
    const queue: string[] = [folderPath];
    const collected: string[] = [];

    while (queue.length > 0 && collected.length < MAX_FOLDER_FILES) {
      const path = queue.shift();
      if (!path) continue;
      const response = await contentApi.listDirectory(path);

      for (const file of response.files) {
        if (collected.length >= MAX_FOLDER_FILES) break;
        collected.push(file.path);
      }

      for (const folder of response.folders) {
        queue.push(folder.path);
      }
    }

    return {
      paths: collected,
      truncated: queue.length > 0,
    };
  }, []);

  const handleAddFolder = useCallback(
    async (folderPath: string) => {
      setIsAddingFolder(folderPath);
      try {
        const result = await collectFolderFiles(folderPath);
        if (result.paths.length === 0) {
          notify(translate("custom.pages.chat.context.picker.empty_folder"), {
            type: "warning",
          });
          return;
        }

        onAddPaths(result.paths);
        if (result.truncated) {
          notify(
            translate("custom.pages.chat.context.picker.folder_truncated", {
              count: MAX_FOLDER_FILES,
            }),
            { type: "warning" },
          );
        }
      } catch (addError) {
        reportClientError(addError, undefined, { routeName: "chat:context-picker:add-folder" });
        notify(translate("custom.pages.chat.context.picker.add_folder_failed"), {
          type: "error",
        });
      } finally {
        setIsAddingFolder(null);
      }
    },
    [collectFolderFiles, notify, onAddPaths, translate],
  );

  const renderFileActions = useCallback(
    (file: ContentItemInfo) => {
      const indexed = file.status === "COMPLETED";
      if (!indexed) {
        return (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button type="button" variant="outline" size="icon" className="h-7 w-7" disabled>
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {translate("custom.pages.chat.context.picker.not_indexed")}
            </TooltipContent>
          </Tooltip>
        );
      }
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => handleAddFile(file.path)}
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{translate("custom.pages.chat.context.picker.add_file")}</TooltipContent>
        </Tooltip>
      );
    },
    [handleAddFile, translate],
  );

  const renderFolderActions = useCallback(
    (folder: FolderInfo) => {
      const adding = isAddingFolder === folder.path;
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => void handleAddFolder(folder.path)}
              disabled={adding}
            >
              {adding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FolderPlus className="h-3.5 w-3.5" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {translate("custom.pages.chat.context.picker.add_folder")}
          </TooltipContent>
        </Tooltip>
      );
    },
    [handleAddFolder, isAddingFolder, translate],
  );

  const handleFileClick = useCallback((file: ContentItemInfo) => {
    setDetailsFile(file);
    setDetailsOpen(true);
  }, []);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.chat.context.picker.title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.chat.context.picker.description")}
            </DialogDescription>
          </DialogHeader>

          {/* Breadcrumb: browse folders, or search/filter across the subtree below. */}
          <div className="flex min-w-0 flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <button
              type="button"
              className="rounded px-1.5 py-0.5 hover:bg-muted"
              onClick={() => setCurrentPath("")}
            >
              {translate("custom.pages.chat.context.picker.root")}
            </button>
            {breadcrumbPaths.map((path) => (
              <span key={path} className="inline-flex items-center gap-1">
                <ChevronRight className="h-3 w-3" />
                <button
                  type="button"
                  className="rounded px-1.5 py-0.5 hover:bg-muted"
                  onClick={() => setCurrentPath(path)}
                >
                  {formatPathName(path)}
                </button>
              </span>
            ))}
          </div>

          <div className="h-[60vh] overflow-y-auto pr-1">
            <ContentListView
              currentPath={currentPath}
              onNavigate={setCurrentPath}
              onFileClick={handleFileClick}
              renderFileActions={renderFileActions}
              renderFolderActions={renderFolderActions}
              renderSelectionBar={({ selectedPaths, clearSelection }) => (
                <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
                  <span className="mr-1 text-sm text-muted-foreground">
                    {translate("custom.pages.chat.context.picker.selected_count", {
                      count: selectedPaths.length,
                    })}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => {
                      onAddPaths(selectedPaths);
                      clearSelection();
                    }}
                  >
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    {translate("custom.pages.chat.context.picker.add_selected")}
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={clearSelection}>
                    {translate("custom.pages.chat.context.picker.clear_selection")}
                  </Button>
                </div>
              )}
            />
          </div>
        </DialogContent>
      </Dialog>

      <ContentItemDetailsDialog
        file={detailsFile}
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
      />
    </>
  );
};
