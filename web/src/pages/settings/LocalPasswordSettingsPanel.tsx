import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { authApi } from "@/dataProvider";
import { useNotify, useTranslate } from "@/lib/app-context";

export function LocalPasswordSettingsPanel() {
  const translate = useTranslate();
  const notify = useNotify();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      notify(translate("custom.pages.settings.auth.password_update_success"), { type: "success" });
    } catch {
      notify(translate("custom.pages.settings.auth.password_update_failed"), { type: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-muted-foreground" />
          <h3 className="text-lg font-medium">{translate("custom.pages.settings.auth.title")}</h3>
        </div>
        <p className="text-sm text-muted-foreground">
          {translate("custom.pages.settings.auth.description")}
        </p>
      </div>
      <Separator />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="settings-current-password">
            {translate("custom.pages.settings.auth.current_password")}
          </Label>
          <Input
            id="settings-current-password"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-new-password">
            {translate("custom.pages.settings.auth.new_password")}
          </Label>
          <Input
            id="settings-new-password"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </div>
        <div className="md:col-span-2">
          <Button
            onClick={() => void handleSubmit()}
            disabled={submitting || !currentPassword || !newPassword}
          >
            {submitting
              ? translate("custom.pages.settings.auth.updating_password")
              : translate("custom.pages.settings.auth.update_password")}
          </Button>
        </div>
      </div>
    </section>
  );
}
