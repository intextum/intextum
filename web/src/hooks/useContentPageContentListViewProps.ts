import {
  buildContentPageAllFilesViewProps,
  type BuildContentPageAllFilesViewPropsOptions,
} from "@/lib/content-page";

export function useContentPageContentListViewProps({
  ...options
}: BuildContentPageAllFilesViewPropsOptions) {
  return buildContentPageAllFilesViewProps(options);
}
