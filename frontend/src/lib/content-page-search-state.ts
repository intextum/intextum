import type { ContentItemInfo } from "@/dataProvider";

interface StartContentPageSelectedFileLoadOptions {
  selectedFilePath: string | null;
  currentSelectedFilePath: string | null;
  getDetails: (path: string) => Promise<ContentItemInfo>;
  onSelectFile: (file: ContentItemInfo) => void;
  onMissingFile: () => void;
}

export function startContentPageSelectedFileLoad({
  selectedFilePath,
  currentSelectedFilePath,
  getDetails,
  onSelectFile,
  onMissingFile,
}: StartContentPageSelectedFileLoadOptions): (() => void) | undefined {
  if (!selectedFilePath || currentSelectedFilePath === selectedFilePath) {
    return undefined;
  }

  let cancelled = false;

  void getDetails(selectedFilePath)
    .then((fileInfo) => {
      if (cancelled) {
        return;
      }
      onSelectFile(fileInfo);
    })
    .catch(() => {
      if (cancelled) {
        return;
      }
      onMissingFile();
    });

  return () => {
    cancelled = true;
  };
}
