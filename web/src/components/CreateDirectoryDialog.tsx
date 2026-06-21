import { useState } from "react";
import { useTranslate, useNotify } from "@/lib/app-context";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { contentApi } from "@/dataProvider";

interface CreateDirectoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPath: string;
  onSuccess: () => void;
}

export const CreateDirectoryDialog = ({
  open,
  onOpenChange,
  currentPath,
  onSuccess,
}: CreateDirectoryDialogProps) => {
  const translate = useTranslate();
  const notify = useNotify();
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const isValid =
    name.trim().length > 0 && !name.includes("/") && !name.includes("\\") && !name.startsWith(".");

  const handleSubmit = async () => {
    if (!isValid) return;
    setLoading(true);

    const fullPath = currentPath ? `${currentPath}/${name.trim()}` : name.trim();

    try {
      await contentApi.mkdir(fullPath);
      notify(translate("custom.content.mkdir.success"), { type: "success" });
      onSuccess();
      setName("");
      onOpenChange(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : translate("custom.content.mkdir.failed");
      notify(message, { type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setName("");
    }
    onOpenChange(nextOpen);
  };

  const displayPath = currentPath || "/";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{translate("custom.content.mkdir.title")}</DialogTitle>
          <DialogDescription>
            {translate("custom.content.mkdir.description", {
              directory: displayPath,
            })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="dir-name">{translate("custom.content.mkdir.name_label")}</Label>
          <Input
            id="dir-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={translate("custom.content.mkdir.name_placeholder")}
            onKeyDown={(e) => {
              if (e.key === "Enter" && isValid && !loading) {
                handleSubmit();
              }
            }}
            autoFocus
          />
        </div>

        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!isValid || loading}>
            {translate("custom.content.mkdir.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
