import { Fragment, useMemo } from "react";
import { Link } from "react-router";
import { Home } from "lucide-react";

import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import type { ContentItemInfo } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";
import { getContentItemDisplayName } from "@/lib/content-utils";

const contentFolderHref = (path: string) => {
  if (!path) {
    return "/content";
  }
  return `/content?path=${encodeURIComponent(path)}`;
};

const MAX_VISIBLE_FOLDER_BREADCRUMBS = 3;

interface ContentItemBreadcrumbProps {
  file?: ContentItemInfo | null;
  currentLabel?: string;
  tailLabel?: string;
}

export const ContentItemBreadcrumb = ({
  file,
  currentLabel,
  tailLabel,
}: ContentItemBreadcrumbProps) => {
  const translate = useTranslate();
  const model = useMemo(() => {
    if (!file) {
      return {
        folders: [],
        hasHiddenFolders: false,
        current:
          currentLabel ??
          translate("custom.content.details.full_view", { defaultValue: "Content details" }),
      };
    }

    const parts = file.path.split("/").filter(Boolean);
    const fileName = currentLabel ?? parts.at(-1) ?? getContentItemDisplayName(file);
    const folderParts = parts.slice(0, -1);
    const visibleFolderStartIndex =
      folderParts.length > MAX_VISIBLE_FOLDER_BREADCRUMBS
        ? folderParts.length - MAX_VISIBLE_FOLDER_BREADCRUMBS
        : 0;
    return {
      folders: folderParts
        .map((part, index) => ({
          key: folderParts.slice(0, index + 1).join("/"),
          label: part,
          href: contentFolderHref(folderParts.slice(0, index + 1).join("/")),
        }))
        .slice(visibleFolderStartIndex),
      hasHiddenFolders: visibleFolderStartIndex > 0,
      current: fileName,
    };
  }, [currentLabel, file, translate]);

  return (
    <Breadcrumb>
      <BreadcrumbList className="min-w-0 flex-nowrap overflow-hidden">
        <BreadcrumbItem className="shrink-0">
          <BreadcrumbLink asChild className="flex items-center gap-1">
            <Link to="/content">
              <Home className="h-3 w-3" />
              {translate("resources.content.name")}
            </Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        {model.hasHiddenFolders ? (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem className="shrink-0">
              <BreadcrumbEllipsis className="size-6" />
            </BreadcrumbItem>
          </>
        ) : null}
        {model.folders.map((folder) => (
          <Fragment key={folder.key}>
            <BreadcrumbSeparator />
            <BreadcrumbItem className="min-w-0">
              <BreadcrumbLink asChild>
                <Link to={folder.href} className="block max-w-[10rem] truncate sm:max-w-[14rem]">
                  {folder.label}
                </Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
          </Fragment>
        ))}
        <BreadcrumbSeparator />
        <BreadcrumbItem className="min-w-0">
          {tailLabel && file ? (
            <BreadcrumbLink asChild>
              <Link
                to={`/content/item/${encodeURIComponent(file.id)}`}
                className="max-w-[34rem] truncate"
              >
                {model.current}
              </Link>
            </BreadcrumbLink>
          ) : (
            <BreadcrumbPage className="max-w-[42rem] truncate">{model.current}</BreadcrumbPage>
          )}
        </BreadcrumbItem>
        {tailLabel ? (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem className="min-w-0">
              <BreadcrumbPage className="max-w-[18rem] truncate">{tailLabel}</BreadcrumbPage>
            </BreadcrumbItem>
          </>
        ) : null}
      </BreadcrumbList>
    </Breadcrumb>
  );
};
