import { Fragment } from "react";
import { Files, FolderPlus, Home, RefreshCw, Upload } from "lucide-react";
import { useTranslate } from "@/lib/app-context";

import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page/PageHeader";
import { BreadcrumbPortal } from "@/components/app/BreadcrumbPortal";
import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  buildContentPageHeaderActions,
  buildContentPageHeaderBreadcrumbItems,
  buildContentPageHeaderState,
} from "@/lib/content-page";

interface ContentPageHeaderProps {
  titleKey: string;
  currentPath: string;
  isImmutable: boolean;
  pathParts: string[];
  breadcrumbPaths: string[];
  onNavigate: (path: string) => void;
  onOpenUpload: () => void;
  onOpenCreateDirectory: () => void;
  onRefresh: () => void;
}

export function ContentPageHeader({
  titleKey,
  currentPath,
  isImmutable,
  pathParts,
  breadcrumbPaths,
  onNavigate,
  onOpenUpload,
  onOpenCreateDirectory,
  onRefresh,
}: ContentPageHeaderProps) {
  const translate = useTranslate();
  const headerState = buildContentPageHeaderState({
    currentPath,
    isImmutable,
  });
  const breadcrumbItems = buildContentPageHeaderBreadcrumbItems({
    pathParts,
    breadcrumbPaths,
  });
  const headerActions = buildContentPageHeaderActions({
    currentPath,
    isImmutable,
  });

  const actions = (
    <>
      {headerActions.includes("upload") ? (
        <Button size="sm" onClick={onOpenUpload}>
          <Upload className="mr-2 h-4 w-4" />
          {translate("custom.content.upload.button")}
        </Button>
      ) : null}
      {headerActions.includes("mkdir") ? (
        <Button variant="outline" size="sm" onClick={onOpenCreateDirectory}>
          <FolderPlus className="mr-2 h-4 w-4" />
          {translate("custom.content.mkdir.button")}
        </Button>
      ) : null}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="outline" size="sm" onClick={onRefresh}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{translate("custom.refresh")}</TooltipContent>
      </Tooltip>
    </>
  );

  return (
    <>
      {headerState.showTitle ? (
        <PageHeader
          icon={Files}
          title={translate(titleKey)}
          description={translate("custom.content.description")}
          actions={actions}
        />
      ) : null}

      {headerState.showBrowseBreadcrumbs ? (
        <BreadcrumbPortal>
          <Breadcrumb>
            <BreadcrumbList className="min-w-0 flex-nowrap overflow-hidden">
              {breadcrumbItems.map((item, index) => (
                <Fragment key={item.key}>
                  {index > 0 ? <BreadcrumbSeparator /> : null}
                  <BreadcrumbItem className={item.isEllipsis ? "shrink-0" : "min-w-0"}>
                    {item.isEllipsis ? <BreadcrumbEllipsis className="size-6" /> : null}
                    {!item.isEllipsis && item.isCurrent ? (
                      <BreadcrumbPage className="max-w-[16rem] truncate sm:max-w-[24rem]">
                        {item.isRoot ? translate(item.label) : item.label}
                      </BreadcrumbPage>
                    ) : null}
                    {!item.isEllipsis && !item.isCurrent ? (
                      <BreadcrumbLink
                        onClick={() => onNavigate(item.path)}
                        className={
                          item.isRoot
                            ? "flex shrink-0 cursor-pointer items-center gap-1"
                            : "block max-w-[10rem] cursor-pointer truncate sm:max-w-[14rem]"
                        }
                      >
                        {item.isRoot ? <Home className="h-3 w-3" /> : null}
                        {item.isRoot ? translate(item.label) : item.label}
                      </BreadcrumbLink>
                    ) : null}
                  </BreadcrumbItem>
                </Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        </BreadcrumbPortal>
      ) : null}
    </>
  );
}
