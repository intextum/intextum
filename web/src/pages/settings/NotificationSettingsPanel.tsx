import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNotify, useTranslate } from "@/lib/app-context";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { notificationPreferencesApi, type NotificationPreferences } from "@/dataProvider";
import { defaultNotificationPreferences } from "@/lib/user-events";
import { queryKeys } from "@/lib/query-client";

interface PreferenceRowProps {
  checked: boolean;
  description: string;
  disabled: boolean;
  label: string;
  onCheckedChange: (checked: boolean) => void;
}

const PreferenceRow = ({
  checked,
  description,
  disabled,
  label,
  onCheckedChange,
}: PreferenceRowProps) => (
  <div className="flex items-start justify-between gap-4 py-3">
    <div className="space-y-1">
      <p className="text-sm font-medium leading-none">{label}</p>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
    <Switch checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
  </div>
);

export const NotificationSettingsPanel = () => {
  const translate = useTranslate();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const [savedPreferences, setSavedPreferences] = useState<NotificationPreferences>(
    defaultNotificationPreferences(),
  );
  const [draftPreferences, setDraftPreferences] = useState<NotificationPreferences>(
    defaultNotificationPreferences(),
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const hasUnsavedChanges = JSON.stringify(draftPreferences) !== JSON.stringify(savedPreferences);
  const actionsDisabled = loading || saving || !hasUnsavedChanges;

  useEffect(() => {
    let cancelled = false;

    notificationPreferencesApi
      .get()
      .then((loaded) => {
        if (!cancelled) {
          setSavedPreferences(loaded);
          setDraftPreferences(loaded);
        }
      })
      .catch(() => {
        if (!cancelled) {
          notify(translate("custom.pages.settings.notifications.load_failed"), { type: "error" });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [notify, translate]);

  const updateDraft = useCallback((nextPreferences: NotificationPreferences) => {
    setDraftPreferences(nextPreferences);
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const saved = await notificationPreferencesApi.update(draftPreferences);
      setSavedPreferences(saved);
      setDraftPreferences(saved);
      queryClient.setQueryData(queryKeys.settings.notificationPreferences, saved);
      notify(translate("custom.pages.settings.notifications.save_success"), {
        type: "success",
      });
    } catch {
      notify(translate("custom.pages.settings.notifications.save_failed"), { type: "error" });
    } finally {
      setSaving(false);
    }
  }, [draftPreferences, notify, queryClient, translate]);

  const handleReset = useCallback(() => {
    setDraftPreferences(savedPreferences);
    notify(translate("custom.pages.settings.notifications.reset_success"), {
      type: "info",
    });
  }, [notify, savedPreferences, translate]);

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-muted-foreground" />
          <h3 className="text-lg font-medium">
            {translate("custom.pages.settings.notifications.title")}
          </h3>
        </div>
        <p className="text-sm text-muted-foreground">
          {translate("custom.pages.settings.notifications.description")}
        </p>
      </div>
      <Separator />
      <div className="space-y-6">
        <div className="space-y-1">
          <h2 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
            {translate("custom.pages.settings.notifications.sections.chat")}
          </h2>
          <div className="divide-y">
            <PreferenceRow
              checked={draftPreferences.chat.completed}
              description={translate("custom.pages.settings.notifications.chat.completed_desc")}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.chat.completed")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  chat: { ...draftPreferences.chat, completed: checked },
                })
              }
            />
            <PreferenceRow
              checked={draftPreferences.chat.failed}
              description={translate("custom.pages.settings.notifications.chat.failed_desc")}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.chat.failed")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  chat: { ...draftPreferences.chat, failed: checked },
                })
              }
            />
            <PreferenceRow
              checked={draftPreferences.chat.cancelled}
              description={translate("custom.pages.settings.notifications.chat.cancelled_desc")}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.chat.cancelled")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  chat: { ...draftPreferences.chat, cancelled: checked },
                })
              }
            />
          </div>
        </div>

        <div className="space-y-1">
          <h2 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
            {translate("custom.pages.settings.notifications.sections.content_processing")}
          </h2>
          <div className="divide-y">
            <PreferenceRow
              checked={draftPreferences.content_processing.completed}
              description={translate(
                "custom.pages.settings.notifications.content_processing.completed_desc",
              )}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.content_processing.completed")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  content_processing: {
                    ...draftPreferences.content_processing,
                    completed: checked,
                  },
                })
              }
            />
            <PreferenceRow
              checked={draftPreferences.content_processing.failed}
              description={translate(
                "custom.pages.settings.notifications.content_processing.failed_desc",
              )}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.content_processing.failed")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  content_processing: {
                    ...draftPreferences.content_processing,
                    failed: checked,
                  },
                })
              }
            />
          </div>
        </div>

        <div className="space-y-1">
          <h2 className="text-sm font-semibold uppercase tracking-normal text-muted-foreground">
            {translate("custom.pages.settings.notifications.sections.research")}
          </h2>
          <div className="divide-y">
            <PreferenceRow
              checked={draftPreferences.research.completed}
              description={translate("custom.pages.settings.notifications.research.completed_desc")}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.research.completed")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  research: { ...draftPreferences.research, completed: checked },
                })
              }
            />
            <PreferenceRow
              checked={draftPreferences.research.failed}
              description={translate("custom.pages.settings.notifications.research.failed_desc")}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.research.failed")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  research: { ...draftPreferences.research, failed: checked },
                })
              }
            />
            <PreferenceRow
              checked={draftPreferences.research.cancelled}
              description={translate("custom.pages.settings.notifications.research.cancelled_desc")}
              disabled={loading || saving}
              label={translate("custom.pages.settings.notifications.research.cancelled")}
              onCheckedChange={(checked) =>
                updateDraft({
                  ...draftPreferences,
                  research: { ...draftPreferences.research, cancelled: checked },
                })
              }
            />
          </div>
        </div>
      </div>
      <div className="flex flex-wrap justify-end gap-3 pt-2">
        <Button variant="outline" onClick={handleReset} disabled={actionsDisabled}>
          {translate("custom.pages.settings.notifications.reset_button")}
        </Button>
        <Button onClick={() => void handleSave()} disabled={actionsDisabled}>
          {saving
            ? translate("custom.pages.settings.notifications.saving")
            : translate("custom.pages.settings.notifications.save_button")}
        </Button>
      </div>
    </section>
  );
};
