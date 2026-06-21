import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

type AiSettingsSectionCardProps = {
  title: string;
  description: string;
  icon: ReactNode;
  isDirty: boolean;
  isSaving: boolean;
  isResetting: boolean;
  saveLabel: string;
  savingLabel: string;
  resetLabel: string;
  resettingLabel: string;
  onSave: () => void;
  onReset: () => void;
  children: ReactNode;
  showHeader?: boolean;
  showActions?: boolean;
};

export function AiSettingsSectionCard({
  title,
  description,
  icon,
  isDirty,
  isSaving,
  isResetting,
  saveLabel,
  savingLabel,
  resetLabel,
  resettingLabel,
  onSave,
  onReset,
  children,
  showHeader = true,
  showActions = true,
}: AiSettingsSectionCardProps) {
  const actionsDisabled = !isDirty || isSaving || isResetting;

  return (
    <section className="space-y-4">
      {showHeader ? (
        <>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              {icon}
              <h3 className="text-lg font-medium">{title}</h3>
            </div>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
          <Separator />
        </>
      ) : null}
      <div className="space-y-4">{children}</div>
      {showActions ? (
        <div className="flex flex-wrap justify-end gap-3 pt-2">
          <Button variant="outline" onClick={onReset} disabled={actionsDisabled}>
            {isResetting ? resettingLabel : resetLabel}
          </Button>
          <Button onClick={onSave} disabled={actionsDisabled}>
            {isSaving ? savingLabel : saveLabel}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
