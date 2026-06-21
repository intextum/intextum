import { Languages, Palette } from "lucide-react";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocales, useLocaleState, useTranslate } from "@/lib/app-context";
import { useTheme } from "next-themes";

export function UserPreferencesSettingsPanel() {
  const translate = useTranslate();
  const languages = useLocales();
  const [locale, setLocale] = useLocaleState();
  const { theme = "system", setTheme } = useTheme();

  return (
    <section className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">
          {translate("custom.pages.settings.preferences.title")}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {translate("custom.pages.settings.preferences.description")}
        </p>
      </div>

      <div className="rounded-lg border">
        <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <Palette className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div>
              <Label htmlFor="settings-theme">
                {translate("custom.pages.settings.preferences.theme_label")}
              </Label>
              <p className="mt-1 text-sm text-muted-foreground">
                {translate("custom.pages.settings.preferences.theme_description")}
              </p>
            </div>
          </div>
          <Select value={theme} onValueChange={setTheme}>
            <SelectTrigger id="settings-theme" className="w-full sm:w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="light">
                {translate("custom.pages.settings.preferences.theme_light")}
              </SelectItem>
              <SelectItem value="dark">
                {translate("custom.pages.settings.preferences.theme_dark")}
              </SelectItem>
              <SelectItem value="system">
                {translate("custom.pages.settings.preferences.theme_system")}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <Languages className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div>
              <Label htmlFor="settings-language">
                {translate("custom.pages.settings.preferences.language_label")}
              </Label>
              <p className="mt-1 text-sm text-muted-foreground">
                {translate("custom.pages.settings.preferences.language_description")}
              </p>
            </div>
          </div>
          <Select value={locale} onValueChange={setLocale} disabled={languages.length <= 1}>
            <SelectTrigger id="settings-language" className="w-full sm:w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {languages.map((language) => (
                <SelectItem key={language.locale} value={language.locale}>
                  {language.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </section>
  );
}
