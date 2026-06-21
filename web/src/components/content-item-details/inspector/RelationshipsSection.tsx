import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ContentItemInfo } from "@/dataProvider";
import { useTranslate } from "@/lib/app-context";

interface RelationshipsSectionProps {
  file: ContentItemInfo;
  onOpenRelatedItem?: (path: string) => void | Promise<void>;
}

export const RelationshipsSection = ({ file, onOpenRelatedItem }: RelationshipsSectionProps) => {
  const translate = useTranslate();
  const parent = file.parent_item;
  const children = file.child_items ?? [];

  const relationKindLabel = (kind: string) =>
    translate(`custom.content.details.kind_${kind}`, { defaultValue: kind });

  return (
    <div className="space-y-3">
      {parent ? (
        <div className="space-y-1">
          <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {translate("custom.content.details.parent_item")}
          </div>
          <RelationLine
            displayName={parent.display_name}
            path={parent.path}
            kindLabel={relationKindLabel(parent.kind)}
            onOpen={onOpenRelatedItem ? () => void onOpenRelatedItem(parent.path) : undefined}
            openLabel={translate("custom.content.details.open_related_item")}
          />
        </div>
      ) : null}

      {children.length > 0 ? (
        <div className="space-y-1">
          <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {translate("custom.content.details.child_items")}
          </div>
          <div className="space-y-1.5">
            {children.map((item) => (
              <RelationLine
                key={item.id}
                displayName={item.display_name}
                path={item.path}
                kindLabel={relationKindLabel(item.kind)}
                onOpen={onOpenRelatedItem ? () => void onOpenRelatedItem(item.path) : undefined}
                openLabel={translate("custom.content.details.open_related_item")}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

interface RelationLineProps {
  displayName: string;
  path: string;
  kindLabel: string;
  onOpen?: () => void;
  openLabel: string;
}

const RelationLine = ({ displayName, path, kindLabel, onOpen, openLabel }: RelationLineProps) => (
  <div className="flex items-center justify-between gap-2 rounded-md border bg-background/40 px-2.5 py-1.5">
    <div className="min-w-0 flex-1">
      <div className="truncate text-xs font-medium">{displayName}</div>
      <div className="truncate font-mono text-[10px] text-muted-foreground">{path}</div>
    </div>
    <div className="flex shrink-0 items-center gap-1.5">
      <Badge variant="outline" className="text-[10px]">
        {kindLabel}
      </Badge>
      {onOpen ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-[10px]"
          onClick={onOpen}
        >
          {openLabel}
        </Button>
      ) : null}
    </div>
  </div>
);
