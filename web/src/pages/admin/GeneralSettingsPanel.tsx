import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useNotify, useTranslate } from "@/lib/app-context";
import { generalSettingsApi } from "@/dataProvider";

export function GeneralSettingsPanel() {
  const translate = useTranslate();
  const notify = useNotify();

  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const settingsQuery = useQuery({
    queryKey: ["admin", "general-settings"],
    queryFn: generalSettingsApi.get,
  });
  const { data, isLoading, error, refetch } = settingsQuery;

  useEffect(() => {
    if (data) {
      setPublicBaseUrl(data.public_base_url ?? "");
    }
  }, [data]);

  useEffect(() => {
    if (error) {
      notify(translate("custom.pages.admin.general.failed_to_load"), { type: "error" });
    }
  }, [error, notify, translate]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await generalSettingsApi.update({ public_base_url: publicBaseUrl.trim() || null });
      await refetch();
      notify(translate("custom.pages.admin.general.saved"), { type: "info" });
    } catch {
      notify(translate("custom.pages.admin.general.save_failed"), { type: "error" });
    } finally {
      setSaving(false);
    }
  };

  const savedValue = data?.public_base_url ?? "";
  const configDefault = data?.config_public_base_url ?? null;
  const dirty = publicBaseUrl.trim() !== savedValue;
  const showConfigHint = Boolean(configDefault) && publicBaseUrl.trim() === "";

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-muted-foreground" />
            <h3 className="text-lg font-medium">{translate("custom.pages.admin.general.title")}</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            {translate("custom.pages.admin.general.description")}
          </p>
        </div>
        <Separator />
        <div className="max-w-xl space-y-2">
          <Label htmlFor="public-base-url">
            {translate("custom.pages.admin.general.public_url_label")}
          </Label>
          <Input
            id="public-base-url"
            type="url"
            inputMode="url"
            placeholder={configDefault ?? "https://dms.example.org"}
            value={publicBaseUrl}
            onChange={(event) => setPublicBaseUrl(event.target.value)}
            disabled={isLoading}
            autoComplete="off"
          />
          <p className="text-sm text-muted-foreground">
            {translate("custom.pages.admin.general.public_url_help")}
          </p>
          {showConfigHint ? (
            <p className="text-sm text-muted-foreground">
              {translate("custom.pages.admin.general.config_default_hint", {
                url: configDefault,
              })}
            </p>
          ) : null}
          <div className="pt-2">
            <Button onClick={handleSave} disabled={saving || isLoading || !dirty}>
              {saving
                ? translate("custom.pages.admin.general.saving")
                : translate("custom.pages.admin.general.save")}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
