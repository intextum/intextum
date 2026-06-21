import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  Copy,
  Languages,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  X,
} from "lucide-react";

import { LoadingState } from "@/components/page/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useLocaleState, useNotify, useTranslate } from "@/lib/app-context";
import { queryKeys } from "@/lib/query-client";
import { reportClientError } from "@/lib/report-client-error";
import {
  chatPromptPresetsApi,
  type ChatPromptPresetListResponse,
  type ChatPromptPreset,
  type ChatPromptPresetAction,
  type ChatPromptPresetIcon,
  type ChatPromptPresetMode,
} from "@/dataProvider";
import {
  createPromptPresetId,
  localizedPresetText,
  normalizePromptPresetLocale,
  nextPromptPresetSortOrder,
  otherPromptPresetLocale,
  preferredPromptPresetLocale,
  type PromptPresetLocale,
  PROMPT_PRESET_ICONS,
  promptPresetLanguageBadge,
} from "@/lib/chat-prompt-presets";

const normalizeSortOrders = (presets: ChatPromptPreset[]): ChatPromptPreset[] =>
  presets.map((preset, index) => ({ ...preset, sort_order: (index + 1) * 10 }));

const localizedDefaults = (locale: PromptPresetLocale) =>
  locale === "de"
    ? {
        label: "Neues Preset",
        description: "Beschreibt dieses Preset.",
        prompt: "Prompt hier eintragen.",
      }
    : {
        label: "New preset",
        description: "Describe what this preset does.",
        prompt: "Write your prompt here.",
      };

const newPreset = (sortOrder: number, locale: PromptPresetLocale): ChatPromptPreset => {
  const defaults = localizedDefaults(locale);
  return {
    id: createPromptPresetId(defaults.label),
    enabled: true,
    sort_order: sortOrder,
    mode: "chat",
    label: { [locale]: defaults.label },
    description: { [locale]: defaults.description },
    prompt: { [locale]: defaults.prompt },
    icon: "sparkles",
    context: { min_files: 0, max_files: null },
    action: "fill",
  };
};

function snapshot(presets: ChatPromptPreset[]): string {
  return JSON.stringify(presets);
}

const localeLabel = (locale: PromptPresetLocale): string =>
  locale === "de" ? "Deutsch" : "English";

const removeLocale = (preset: ChatPromptPreset, locale: PromptPresetLocale): ChatPromptPreset => {
  const label = { ...preset.label };
  const description = { ...preset.description };
  const prompt = { ...preset.prompt };
  delete label[locale];
  delete description[locale];
  delete prompt[locale];
  return { ...preset, label, description, prompt };
};

export function ChatPromptPresetsPanel() {
  const translate = useTranslate();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const [locale] = useLocaleState();
  const activeLocale = normalizePromptPresetLocale(locale);
  const [presets, setPresets] = useState<ChatPromptPreset[]>([]);
  const [savedSnapshot, setSavedSnapshot] = useState("");
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingLocale, setEditingLocale] = useState<PromptPresetLocale>(activeLocale);
  const [translationOpen, setTranslationOpen] = useState(false);

  const dirty = snapshot(presets) !== savedSnapshot;
  const editingPreset = editingIndex === null ? null : (presets[editingIndex] ?? null);
  const translationLocale = otherPromptPresetLocale(editingLocale);
  const editingHasTranslation = Boolean(
    editingPreset &&
    (translationLocale in editingPreset.label ||
      translationLocale in editingPreset.description ||
      translationLocale in editingPreset.prompt),
  );

  const presetsQuery = useQuery({
    queryKey: queryKeys.admin.promptPresets,
    queryFn: chatPromptPresetsApi.getAdmin,
  });

  useEffect(() => {
    if (presetsQuery.data) {
      setPresets(presetsQuery.data.presets);
      setSavedSnapshot(snapshot(presetsQuery.data.presets));
    }
  }, [presetsQuery.dataUpdatedAt, presetsQuery.data]);

  useEffect(() => {
    if (presetsQuery.error) {
      reportClientError(presetsQuery.error, undefined, {
        routeName: "admin:prompt-presets:load",
      });
      notify(translate("custom.pages.admin.prompt_presets.load_failed"), { type: "error" });
    }
  }, [notify, presetsQuery.error, translate]);

  const applySavedPresets = (response: ChatPromptPresetListResponse) => {
    queryClient.setQueryData(queryKeys.admin.promptPresets, response);
    void queryClient.invalidateQueries({ queryKey: queryKeys.conversations.promptPresets });
    setPresets(response.presets);
    setSavedSnapshot(snapshot(response.presets));
  };

  const updateEditingPreset = useCallback(
    (updater: (preset: ChatPromptPreset) => ChatPromptPreset) => {
      if (editingIndex === null) {
        return;
      }
      setPresets((current) =>
        current.map((preset, index) => (index === editingIndex ? updater(preset) : preset)),
      );
    },
    [editingIndex],
  );

  const openEditor = (index: number, preset: ChatPromptPreset) => {
    setEditingLocale(preferredPromptPresetLocale(preset, locale));
    setTranslationOpen(false);
    setEditingIndex(index);
  };

  const addPreset = () => {
    setPresets((current) => {
      const next = [...current, newPreset(nextPromptPresetSortOrder(current), activeLocale)];
      setEditingLocale(activeLocale);
      setTranslationOpen(false);
      setEditingIndex(next.length - 1);
      return next;
    });
  };

  const duplicatePreset = (index: number) => {
    setPresets((current) => {
      const source = current[index];
      if (!source) {
        return current;
      }
      const sourceLabel = localizedPresetText(source.label, locale, source.id);
      const copyPreset = {
        ...source,
        id: createPromptPresetId(sourceLabel),
        enabled: false,
        sort_order: nextPromptPresetSortOrder(current),
        label: {
          ...source.label,
          [activeLocale]: translate("custom.pages.admin.prompt_presets.copy_label", {
            label: localizedPresetText(source.label, activeLocale, source.id),
          }),
        },
      };
      const next = [...current, copyPreset];
      setEditingLocale(preferredPromptPresetLocale(copyPreset, locale));
      setTranslationOpen(false);
      setEditingIndex(next.length - 1);
      return next;
    });
  };

  const deletePreset = (index: number) => {
    setPresets((current) =>
      normalizeSortOrders(current.filter((_, itemIndex) => itemIndex !== index)),
    );
    if (editingIndex === index) {
      setEditingIndex(null);
    }
  };

  const movePreset = (index: number, direction: -1 | 1) => {
    setPresets((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) {
        return current;
      }
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return normalizeSortOrders(next);
    });
  };

  const savePresets = async () => {
    setSaving(true);
    try {
      const response = await chatPromptPresetsApi.replaceAdmin(normalizeSortOrders(presets));
      applySavedPresets(response);
      notify(translate("custom.pages.admin.prompt_presets.save_success"), { type: "success" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "admin:prompt-presets:save" });
      notify(translate("custom.pages.admin.prompt_presets.save_failed"), { type: "error" });
    } finally {
      setSaving(false);
    }
  };

  const resetPresets = async () => {
    setResetting(true);
    try {
      const response = await chatPromptPresetsApi.resetAdmin();
      applySavedPresets(response);
      setEditingIndex(null);
      notify(translate("custom.pages.admin.prompt_presets.reset_success"), { type: "success" });
    } catch (error) {
      reportClientError(error, undefined, { routeName: "admin:prompt-presets:reset" });
      notify(translate("custom.pages.admin.prompt_presets.reset_failed"), { type: "error" });
    } finally {
      setResetting(false);
    }
  };

  const presetIdSet = useMemo(
    () =>
      presets.reduce<Record<string, number>>((acc, preset) => {
        acc[preset.id] = (acc[preset.id] ?? 0) + 1;
        return acc;
      }, {}),
    [presets],
  );

  if (presetsQuery.isLoading) {
    return <LoadingState />;
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-lg font-medium">
            {translate("custom.pages.admin.prompt_presets.title")}
          </h3>
          <p className="text-sm text-muted-foreground">
            {translate("custom.pages.admin.prompt_presets.description")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={resetPresets} disabled={saving || resetting}>
            <RotateCcw className="h-4 w-4" />
            {resetting
              ? translate("custom.pages.admin.prompt_presets.resetting")
              : translate("custom.pages.admin.prompt_presets.reset")}
          </Button>
          <Button variant="outline" onClick={addPreset} disabled={saving || resetting}>
            <Plus className="h-4 w-4" />
            {translate("custom.pages.admin.prompt_presets.add")}
          </Button>
          <Button onClick={savePresets} disabled={!dirty || saving || resetting}>
            <Save className="h-4 w-4" />
            {saving
              ? translate("custom.pages.admin.prompt_presets.saving")
              : translate("custom.pages.admin.prompt_presets.save")}
          </Button>
        </div>
      </div>
      <Separator />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{translate("custom.pages.admin.prompt_presets.table.label")}</TableHead>
              <TableHead>{translate("custom.pages.admin.prompt_presets.table.mode")}</TableHead>
              <TableHead>{translate("custom.pages.admin.prompt_presets.table.context")}</TableHead>
              <TableHead>{translate("custom.pages.admin.prompt_presets.table.action")}</TableHead>
              <TableHead className="w-44 text-right">
                {translate("custom.pages.admin.prompt_presets.table.actions")}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {presets.map((preset, index) => (
              <TableRow key={preset.id}>
                <TableCell>
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">
                        {localizedPresetText(preset.label, locale)}
                      </span>
                      <Badge variant="secondary">{promptPresetLanguageBadge(preset)}</Badge>
                      {!preset.enabled && (
                        <Badge variant="outline">
                          {translate("custom.pages.admin.prompt_presets.disabled")}
                        </Badge>
                      )}
                      {presetIdSet[preset.id] > 1 && (
                        <Badge variant="destructive">
                          {translate("custom.pages.admin.prompt_presets.duplicate_id")}
                        </Badge>
                      )}
                    </div>
                    <p className="max-w-xl truncate text-xs text-muted-foreground">
                      {localizedPresetText(preset.description, locale)}
                    </p>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{preset.mode}</Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {preset.context.max_files === null || preset.context.max_files === undefined
                    ? `>= ${preset.context.min_files}`
                    : `${preset.context.min_files}-${preset.context.max_files}`}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{preset.action}</Badge>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => movePreset(index, -1)}
                      disabled={index === 0}
                      title={translate("custom.pages.admin.prompt_presets.move_up")}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => movePreset(index, 1)}
                      disabled={index === presets.length - 1}
                      title={translate("custom.pages.admin.prompt_presets.move_down")}
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => duplicatePreset(index)}
                      title={translate("custom.pages.admin.prompt_presets.duplicate")}
                    >
                      <Copy />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => openEditor(index, preset)}
                      title={translate("custom.pages.admin.prompt_presets.edit")}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => deletePreset(index)}
                      title={translate("custom.pages.admin.prompt_presets.delete")}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Sheet open={editingPreset !== null} onOpenChange={(open) => !open && setEditingIndex(null)}>
        <SheetContent className="w-full gap-0 p-0 sm:max-w-[720px]" showCloseButton={false}>
          <SheetHeader className="border-b px-6 py-4">
            <SheetTitle>{translate("custom.pages.admin.prompt_presets.editor_title")}</SheetTitle>
            <SheetDescription>
              {translate("custom.pages.admin.prompt_presets.editor_description")}
            </SheetDescription>
          </SheetHeader>

          {editingPreset && (
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              <div className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="preset-id">ID</Label>
                    <Input
                      id="preset-id"
                      value={editingPreset.id}
                      onChange={(event) =>
                        updateEditingPreset((preset) => ({ ...preset, id: event.target.value }))
                      }
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-md border px-3 py-2">
                    <div>
                      <Label>{translate("custom.pages.admin.prompt_presets.enabled")}</Label>
                      <p className="text-xs text-muted-foreground">
                        {translate("custom.pages.admin.prompt_presets.enabled_hint")}
                      </p>
                    </div>
                    <Switch
                      checked={editingPreset.enabled}
                      onCheckedChange={(checked) =>
                        updateEditingPreset((preset) => ({ ...preset, enabled: checked }))
                      }
                    />
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.mode")}</Label>
                    <Select
                      value={editingPreset.mode}
                      onValueChange={(value: ChatPromptPresetMode) =>
                        updateEditingPreset((preset) => ({ ...preset, mode: value }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="chat">
                          {translate("custom.pages.chat.mode_chat")}
                        </SelectItem>
                        <SelectItem value="research">
                          {translate("custom.pages.chat.mode_research")}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.action")}</Label>
                    <Select
                      value={editingPreset.action}
                      onValueChange={(value: ChatPromptPresetAction) =>
                        updateEditingPreset((preset) => ({ ...preset, action: value }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="fill">
                          {translate("custom.pages.admin.prompt_presets.action_fill")}
                        </SelectItem>
                        <SelectItem value="submit">
                          {translate("custom.pages.admin.prompt_presets.action_submit")}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.icon")}</Label>
                    <Select
                      value={editingPreset.icon}
                      onValueChange={(value: ChatPromptPresetIcon) =>
                        updateEditingPreset((preset) => ({ ...preset, icon: value }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PROMPT_PRESET_ICONS.map((icon) => (
                          <SelectItem key={icon} value={icon}>
                            {icon}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.min_files")}</Label>
                    <Input
                      type="number"
                      min={0}
                      value={editingPreset.context.min_files}
                      onChange={(event) =>
                        updateEditingPreset((preset) => ({
                          ...preset,
                          context: {
                            ...preset.context,
                            min_files: Math.max(0, Number(event.target.value || 0)),
                          },
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.max_files")}</Label>
                    <Input
                      type="number"
                      min={0}
                      value={editingPreset.context.max_files ?? ""}
                      placeholder={translate("custom.pages.admin.prompt_presets.no_max")}
                      onChange={(event) =>
                        updateEditingPreset((preset) => ({
                          ...preset,
                          context: {
                            ...preset.context,
                            max_files:
                              event.target.value === ""
                                ? null
                                : Math.max(0, Number(event.target.value)),
                          },
                        }))
                      }
                    />
                  </div>
                </div>

                <div className="space-y-4 rounded-md border p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-medium">
                        {translate("custom.pages.admin.prompt_presets.primary_language")}
                      </h4>
                      <p className="text-xs text-muted-foreground">
                        {translate("custom.pages.admin.prompt_presets.primary_language_hint")}
                      </p>
                    </div>
                    <Select
                      value={editingLocale}
                      onValueChange={(value: PromptPresetLocale) => {
                        setEditingLocale(value);
                        setTranslationOpen(false);
                      }}
                    >
                      <SelectTrigger className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="de">Deutsch</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.label")}</Label>
                    <Input
                      value={editingPreset.label[editingLocale] ?? ""}
                      onChange={(event) =>
                        updateEditingPreset((preset) => ({
                          ...preset,
                          label: { ...preset.label, [editingLocale]: event.target.value },
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>
                      {translate("custom.pages.admin.prompt_presets.description_field")}
                    </Label>
                    <Input
                      value={editingPreset.description[editingLocale] ?? ""}
                      onChange={(event) =>
                        updateEditingPreset((preset) => ({
                          ...preset,
                          description: {
                            ...preset.description,
                            [editingLocale]: event.target.value,
                          },
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>{translate("custom.pages.admin.prompt_presets.prompt")}</Label>
                    <Textarea
                      rows={6}
                      value={editingPreset.prompt[editingLocale] ?? ""}
                      onChange={(event) =>
                        updateEditingPreset((preset) => ({
                          ...preset,
                          prompt: { ...preset.prompt, [editingLocale]: event.target.value },
                        }))
                      }
                    />
                  </div>
                </div>

                <div className="rounded-md border">
                  <Collapsible open={translationOpen} onOpenChange={setTranslationOpen}>
                    <div className="flex items-center justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Languages className="h-4 w-4 text-muted-foreground" />
                          <h4 className="text-sm font-medium">
                            {translate("custom.pages.admin.prompt_presets.translation_title", {
                              language: localeLabel(translationLocale),
                            })}
                          </h4>
                          {editingHasTranslation && (
                            <Badge variant="secondary">{translationLocale.toUpperCase()}</Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {translate("custom.pages.admin.prompt_presets.translation_hint")}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {editingHasTranslation ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              updateEditingPreset((preset) =>
                                removeLocale(preset, translationLocale),
                              );
                              setTranslationOpen(false);
                            }}
                          >
                            <X className="h-4 w-4" />
                            {translate("custom.pages.admin.prompt_presets.remove_translation")}
                          </Button>
                        ) : (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              updateEditingPreset((preset) => ({
                                ...preset,
                                label: { ...preset.label, [translationLocale]: "" },
                                description: { ...preset.description, [translationLocale]: "" },
                                prompt: { ...preset.prompt, [translationLocale]: "" },
                              }));
                              setTranslationOpen(true);
                            }}
                          >
                            <Plus className="h-4 w-4" />
                            {translate("custom.pages.admin.prompt_presets.add_translation")}
                          </Button>
                        )}
                        <CollapsibleTrigger asChild>
                          <Button type="button" variant="ghost" size="icon-sm">
                            <ChevronDown className="h-4 w-4" />
                          </Button>
                        </CollapsibleTrigger>
                      </div>
                    </div>
                    <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                      <div className="space-y-1.5">
                        <Label>{translate("custom.pages.admin.prompt_presets.label")}</Label>
                        <Input
                          value={editingPreset.label[translationLocale] ?? ""}
                          onChange={(event) =>
                            updateEditingPreset((preset) => ({
                              ...preset,
                              label: { ...preset.label, [translationLocale]: event.target.value },
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>
                          {translate("custom.pages.admin.prompt_presets.description_field")}
                        </Label>
                        <Input
                          value={editingPreset.description[translationLocale] ?? ""}
                          onChange={(event) =>
                            updateEditingPreset((preset) => ({
                              ...preset,
                              description: {
                                ...preset.description,
                                [translationLocale]: event.target.value,
                              },
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>{translate("custom.pages.admin.prompt_presets.prompt")}</Label>
                        <Textarea
                          rows={6}
                          value={editingPreset.prompt[translationLocale] ?? ""}
                          onChange={(event) =>
                            updateEditingPreset((preset) => ({
                              ...preset,
                              prompt: { ...preset.prompt, [translationLocale]: event.target.value },
                            }))
                          }
                        />
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              </div>
            </div>
          )}

          <SheetFooter className="flex-row justify-end border-t px-6 py-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setEditingIndex(null)}
              disabled={saving}
            >
              {translate("custom.common.cancel")}
            </Button>
            <Button type="button" onClick={savePresets} disabled={!dirty || saving || resetting}>
              <Save className="h-4 w-4" />
              {saving
                ? translate("custom.pages.admin.prompt_presets.saving")
                : translate("custom.pages.admin.prompt_presets.save")}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </section>
  );
}
