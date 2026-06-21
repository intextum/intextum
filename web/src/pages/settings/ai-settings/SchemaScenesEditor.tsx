import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { useRef, type RefObject } from "react";

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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  createEmptySceneDraft,
  createEmptySceneExtractionDraft,
} from "@/lib/content-enrichment-admin";
import type {
  DocumentExtractionFieldDraft,
  DocumentExtractionSceneDraft,
  DocumentExtractionSceneExtractionDraft,
} from "@/lib/content-enrichment-admin";

type TranslateFn = (key: string, options?: unknown) => string;

type SchemaScenesEditorProps = {
  scenes: DocumentExtractionSceneDraft[];
  fields: DocumentExtractionFieldDraft[];
  translate: TranslateFn;
  onChange: (scenes: DocumentExtractionSceneDraft[]) => void;
};

const TRANSLATE_PREFIX = "custom.pages.settings.ai.content_enrichment_editor";

function truncate(text: string, max = 80): string {
  const trimmed = text.trim().replace(/\s+/g, " ");
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max - 1)}…`;
}

function captureTextareaSelection(
  textareaRef: RefObject<HTMLTextAreaElement | null>,
): string | null {
  const node = textareaRef.current;
  if (!node) return null;
  const start = node.selectionStart;
  const end = node.selectionEnd;
  if (start === null || end === null || end <= start) return null;
  return node.value.slice(start, end).trim() || null;
}

export function SchemaScenesEditor({
  scenes,
  fields,
  translate,
  onChange,
}: SchemaScenesEditorProps) {
  const sceneTextRefs = useRef(new Map<string, HTMLTextAreaElement | null>());

  const setSceneTextRef = (sceneId: string) => (node: HTMLTextAreaElement | null) => {
    if (node) {
      sceneTextRefs.current.set(sceneId, node);
    } else {
      sceneTextRefs.current.delete(sceneId);
    }
  };

  const updateScene = (sceneIndex: number, patch: Partial<DocumentExtractionSceneDraft>) => {
    onChange(scenes.map((scene, index) => (index === sceneIndex ? { ...scene, ...patch } : scene)));
  };

  const updateSceneExtraction = (
    sceneIndex: number,
    extractionIndex: number,
    patch: Partial<DocumentExtractionSceneExtractionDraft>,
  ) => {
    const scene = scenes[sceneIndex];
    if (!scene) return;
    updateScene(sceneIndex, {
      extractions: scene.extractions.map((entry, index) =>
        index === extractionIndex ? { ...entry, ...patch } : entry,
      ),
    });
  };

  const setExtractionChildValue = (
    sceneIndex: number,
    extractionIndex: number,
    childName: string,
    value: string,
  ) => {
    const scene = scenes[sceneIndex];
    const entry = scene?.extractions[extractionIndex];
    if (!entry) return;
    updateSceneExtraction(sceneIndex, extractionIndex, {
      child_values: { ...entry.child_values, [childName]: value },
    });
  };

  const removeScene = (sceneIndex: number) => {
    onChange(scenes.filter((_, index) => index !== sceneIndex));
  };

  const removeExtraction = (sceneIndex: number, extractionIndex: number) => {
    const scene = scenes[sceneIndex];
    if (!scene) return;
    updateScene(sceneIndex, {
      extractions: scene.extractions.filter((_, index) => index !== extractionIndex),
    });
  };

  const handleUseSelection = (sceneIndex: number, extractionIndex: number) => {
    const scene = scenes[sceneIndex];
    if (!scene) return;
    const selected = captureTextareaSelection({
      current: sceneTextRefs.current.get(scene.id) ?? null,
    });
    if (selected) {
      updateSceneExtraction(sceneIndex, extractionIndex, { extraction_text: selected });
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Label>{translate(`${TRANSLATE_PREFIX}.scenes_section_title`)}</Label>
          <p className="text-xs text-muted-foreground">
            {translate(`${TRANSLATE_PREFIX}.scenes_section_hint`)}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...scenes, createEmptySceneDraft()])}
        >
          <Plus className="mr-2 h-4 w-4" />
          {translate(`${TRANSLATE_PREFIX}.add_scene`)}
        </Button>
      </div>

      {scenes.length === 0 ? (
        <p className="rounded-md border border-dashed bg-muted/20 px-3 py-6 text-center text-sm text-muted-foreground">
          {translate(`${TRANSLATE_PREFIX}.scenes_empty`)}
        </p>
      ) : (
        <div className="space-y-2">
          {scenes.map((scene, sceneIndex) => {
            const extractionCount = scene.extractions.length;
            const countLabel =
              extractionCount === 0
                ? translate(`${TRANSLATE_PREFIX}.scene_count_zero`)
                : extractionCount === 1
                  ? translate(`${TRANSLATE_PREFIX}.scene_count_one`)
                  : translate(`${TRANSLATE_PREFIX}.scene_count`, {
                      count: extractionCount,
                    });
            const preview =
              truncate(scene.text) || translate(`${TRANSLATE_PREFIX}.scene_text_placeholder`);
            return (
              <Collapsible
                key={scene.id}
                defaultOpen={scenes.length <= 2}
                className="space-y-2 rounded-md border bg-muted/20 p-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <CollapsibleTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="group h-8 flex-1 justify-start gap-2 px-2 text-left text-sm font-normal"
                    >
                      <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=closed]:-rotate-90" />
                      <span className="flex-1 truncate text-muted-foreground">{preview}</span>
                      <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
                        {countLabel}
                      </Badge>
                    </Button>
                  </CollapsibleTrigger>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() => removeScene(sceneIndex)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <CollapsibleContent className="space-y-3">
                  <div className="space-y-1">
                    <Label className="text-xs">
                      {translate(`${TRANSLATE_PREFIX}.scene_text_label`)}
                    </Label>
                    <Textarea
                      ref={setSceneTextRef(scene.id)}
                      rows={4}
                      value={scene.text}
                      onChange={(event) => updateScene(sceneIndex, { text: event.target.value })}
                      placeholder={translate(`${TRANSLATE_PREFIX}.scene_text_placeholder`)}
                      className="text-sm"
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <Label className="text-xs">
                        {translate(`${TRANSLATE_PREFIX}.scene_extractions_label`)}
                      </Label>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs"
                        onClick={() =>
                          updateScene(sceneIndex, {
                            extractions: [
                              ...scene.extractions,
                              createEmptySceneExtractionDraft(fields[0]?.name ?? ""),
                            ],
                          })
                        }
                      >
                        <Plus className="h-3 w-3" />
                        {translate(`${TRANSLATE_PREFIX}.scene_add_extraction`)}
                      </Button>
                    </div>
                    {scene.extractions.length === 0 ? (
                      <p className="rounded-md border border-dashed bg-background px-3 py-4 text-center text-xs text-muted-foreground">
                        {translate(`${TRANSLATE_PREFIX}.scene_count_zero`)}
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {scene.extractions.map((entry, extractionIndex) => (
                          <SceneExtractionRow
                            key={entry.id}
                            entry={entry}
                            fields={fields}
                            sceneText={scene.text}
                            translate={translate}
                            onChangeField={(value) =>
                              updateSceneExtraction(sceneIndex, extractionIndex, {
                                field: value,
                                child_values: {},
                                value: "",
                              })
                            }
                            onChangeAnchor={(value) =>
                              updateSceneExtraction(sceneIndex, extractionIndex, {
                                extraction_text: value,
                              })
                            }
                            onUseSelection={() => handleUseSelection(sceneIndex, extractionIndex)}
                            onChangeValue={(value) =>
                              updateSceneExtraction(sceneIndex, extractionIndex, { value })
                            }
                            onChangeChildValue={(childName, value) =>
                              setExtractionChildValue(sceneIndex, extractionIndex, childName, value)
                            }
                            onRemove={() => removeExtraction(sceneIndex, extractionIndex)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>
      )}
    </div>
  );
}

type SceneExtractionRowProps = {
  entry: DocumentExtractionSceneExtractionDraft;
  fields: DocumentExtractionFieldDraft[];
  sceneText: string;
  translate: TranslateFn;
  onChangeField: (value: string) => void;
  onChangeAnchor: (value: string) => void;
  onUseSelection: () => void;
  onChangeValue: (value: string) => void;
  onChangeChildValue: (childName: string, value: string) => void;
  onRemove: () => void;
};

function SceneExtractionRow({
  entry,
  fields,
  sceneText,
  translate,
  onChangeField,
  onChangeAnchor,
  onUseSelection,
  onChangeValue,
  onChangeChildValue,
  onRemove,
}: SceneExtractionRowProps) {
  const referencedField = fields.find((field) => field.name === entry.field) ?? null;
  const fieldIsUnknown = entry.field.trim() !== "" && !referencedField;
  const anchorTrimmed = entry.extraction_text.trim();
  const anchorMissingFromText = anchorTrimmed.length > 0 && !sceneText.includes(anchorTrimmed);

  return (
    <div className="space-y-2 rounded-md border bg-background p-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[160px] flex-1 space-y-1">
          <Label className="text-[11px] text-muted-foreground">
            {translate(`${TRANSLATE_PREFIX}.scene_extraction_field_label`)}
          </Label>
          <Select value={entry.field || undefined} onValueChange={onChangeField}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue
                placeholder={translate(`${TRANSLATE_PREFIX}.scene_extraction_field_placeholder`)}
              />
            </SelectTrigger>
            <SelectContent>
              {fields
                .filter((field) => field.name.trim())
                .map((field) => (
                  <SelectItem key={field.name} value={field.name}>
                    <span className="font-mono text-xs">{field.name}</span>
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          {fieldIsUnknown ? (
            <p className="text-[11px] text-destructive">
              {translate(`${TRANSLATE_PREFIX}.scene_unknown_field`)}
            </p>
          ) : null}
        </div>
        <div className="min-w-[200px] flex-1 space-y-1">
          <Label className="text-[11px] text-muted-foreground">
            {translate(`${TRANSLATE_PREFIX}.scene_extraction_anchor_label`)}
          </Label>
          <div className="flex gap-1">
            <Input
              value={entry.extraction_text}
              onChange={(event) => onChangeAnchor(event.target.value)}
              placeholder={translate(`${TRANSLATE_PREFIX}.example_anchor_placeholder`)}
              className="h-8 text-sm"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 shrink-0 px-2 text-xs"
              onClick={onUseSelection}
              title={translate(`${TRANSLATE_PREFIX}.use_selection_hint`)}
            >
              {translate(`${TRANSLATE_PREFIX}.use_selection`)}
            </Button>
          </div>
          {anchorMissingFromText ? (
            <p className="text-[11px] text-destructive">
              {translate(`${TRANSLATE_PREFIX}.example_anchor_not_in_text`)}
            </p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
          onClick={onRemove}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      {referencedField ? (
        <SceneExtractionValueInput
          field={referencedField}
          entry={entry}
          translate={translate}
          onChangeValue={onChangeValue}
          onChangeChildValue={onChangeChildValue}
        />
      ) : null}
    </div>
  );
}

type SceneExtractionValueInputProps = {
  field: DocumentExtractionFieldDraft;
  entry: DocumentExtractionSceneExtractionDraft;
  translate: TranslateFn;
  onChangeValue: (value: string) => void;
  onChangeChildValue: (childName: string, value: string) => void;
};

function SceneExtractionValueInput({
  field,
  entry,
  translate,
  onChangeValue,
  onChangeChildValue,
}: SceneExtractionValueInputProps) {
  if (field.dtype === "object_list") {
    return (
      <div className="space-y-1">
        <Label className="text-[11px] text-muted-foreground">
          {translate(`${TRANSLATE_PREFIX}.scene_extraction_value_label`)}
        </Label>
        <div className="grid gap-2 sm:grid-cols-2">
          {field.fields.map((child) => (
            <div key={child.name} className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">
                {child.name || translate(`${TRANSLATE_PREFIX}.field_name`)}
              </Label>
              {child.dtype === "bool" ? (
                <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-2">
                  <Switch
                    checked={entry.child_values[child.name] === "true"}
                    onCheckedChange={(checked) =>
                      onChangeChildValue(child.name, checked ? "true" : "false")
                    }
                  />
                  <span className="text-xs text-muted-foreground">
                    {entry.child_values[child.name] === "true"
                      ? translate(`${TRANSLATE_PREFIX}.example_bool_true`)
                      : translate(`${TRANSLATE_PREFIX}.example_bool_false`)}
                  </span>
                </div>
              ) : child.dtype === "list" ? (
                <Textarea
                  rows={3}
                  value={entry.child_values[child.name] ?? ""}
                  onChange={(event) => onChangeChildValue(child.name, event.target.value)}
                  placeholder={translate(`${TRANSLATE_PREFIX}.example_list_placeholder`)}
                  className="text-sm"
                />
              ) : (
                <Input
                  value={entry.child_values[child.name] ?? ""}
                  onChange={(event) => onChangeChildValue(child.name, event.target.value)}
                  className="h-8 text-sm"
                />
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (field.dtype === "bool") {
    return (
      <div className="space-y-1">
        <Label className="text-[11px] text-muted-foreground">
          {translate(`${TRANSLATE_PREFIX}.scene_extraction_value_label`)}
        </Label>
        <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-2">
          <Switch
            checked={entry.value === "true"}
            onCheckedChange={(checked) => onChangeValue(checked ? "true" : "false")}
          />
          <span className="text-xs text-muted-foreground">
            {entry.value === "true"
              ? translate(`${TRANSLATE_PREFIX}.example_bool_true`)
              : translate(`${TRANSLATE_PREFIX}.example_bool_false`)}
          </span>
        </div>
      </div>
    );
  }
  if (field.dtype === "list") {
    return (
      <div className="space-y-1">
        <Label className="text-[11px] text-muted-foreground">
          {translate(`${TRANSLATE_PREFIX}.scene_extraction_value_label`)}
        </Label>
        <Textarea
          rows={3}
          value={entry.value}
          onChange={(event) => onChangeValue(event.target.value)}
          placeholder={translate(`${TRANSLATE_PREFIX}.example_list_placeholder`)}
          className="text-sm"
        />
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <Label className="text-[11px] text-muted-foreground">
        {translate(`${TRANSLATE_PREFIX}.scene_extraction_value_label`)}
      </Label>
      <Input
        value={entry.value}
        onChange={(event) => onChangeValue(event.target.value)}
        className="h-8 text-sm"
      />
    </div>
  );
}
