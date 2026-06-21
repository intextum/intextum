import { ChevronDown, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  createEmptyExtractionChildFieldDraft,
  createEmptyExtractionFieldDraft,
} from "@/lib/content-enrichment-admin";
import type {
  DocumentExtractionChildDtype,
  DocumentExtractionChildFieldDraft,
  DocumentExtractionDtype,
  DocumentExtractionExampleDraft,
  DocumentExtractionFieldDraft,
  DocumentExtractionSchemaDraft,
} from "@/lib/content-enrichment-admin";

type TranslateFn = (key: string, options?: unknown) => string;

type ExampleTextRefSetter = (key: string) => (node: HTMLTextAreaElement | null) => void;

type CaptureExampleTextSelection = (key: string, onSelect: (selection: string) => void) => void;

const EXTRACTION_DTYPES: DocumentExtractionDtype[] = [
  "str",
  "int",
  "float",
  "bool",
  "list",
  "date",
  "currency",
  "object_list",
];

const CHILD_EXTRACTION_DTYPES: DocumentExtractionChildDtype[] = [
  "str",
  "int",
  "float",
  "bool",
  "list",
  "date",
  "currency",
];

const extractionDtypeLabel = (translate: TranslateFn, dtype: DocumentExtractionDtype) =>
  translate(`custom.pages.settings.ai.content_enrichment_editor.field_type_options.${dtype}`, {
    defaultValue: dtype,
  });

function createEmptyExtractionExampleDraft(): DocumentExtractionExampleDraft {
  return {
    text: "",
    value: "",
    child_values: {},
    extraction_text: "",
  };
}

function updateSchemaField(
  schema: DocumentExtractionSchemaDraft,
  fieldIndex: number,
  patch: Partial<DocumentExtractionFieldDraft>,
) {
  return {
    ...schema,
    fields: schema.fields.map((field, index) =>
      index === fieldIndex ? { ...field, ...patch } : field,
    ),
  };
}

function updateChildSchemaField(
  field: DocumentExtractionFieldDraft,
  childIndex: number,
  patch: Partial<DocumentExtractionChildFieldDraft>,
) {
  return {
    ...field,
    fields: field.fields.map((child, index) =>
      index === childIndex ? { ...child, ...patch } : child,
    ),
  };
}

function updateFieldExample(
  field: DocumentExtractionFieldDraft,
  exampleIndex: number,
  patch: Partial<DocumentExtractionExampleDraft>,
) {
  return {
    ...field,
    examples: field.examples.map((example, index) =>
      index === exampleIndex ? { ...example, ...patch } : example,
    ),
  };
}

function updateFieldExampleChildValue(
  field: DocumentExtractionFieldDraft,
  exampleIndex: number,
  childName: string,
  value: string,
) {
  return updateFieldExample(field, exampleIndex, {
    child_values: {
      ...field.examples[exampleIndex]?.child_values,
      [childName]: value,
    },
  });
}

function FieldDtypeControls({
  field,
  translate,
  onChange,
}: {
  field: DocumentExtractionFieldDraft;
  translate: TranslateFn;
  onChange: (patch: Partial<DocumentExtractionFieldDraft>) => void;
}) {
  return (
    <div className="inline-flex h-8 items-center gap-0.5 rounded-md border bg-background p-0.5">
      {EXTRACTION_DTYPES.map((dtype) => (
        <Button
          key={dtype}
          type="button"
          variant={field.dtype === dtype ? "default" : "ghost"}
          size="sm"
          className="h-7 px-2 font-mono text-[11px]"
          onClick={() => {
            const nextField: Partial<DocumentExtractionFieldDraft> = { dtype };
            if (dtype === "object_list" && field.fields.length === 0) {
              nextField.fields = [createEmptyExtractionChildFieldDraft()];
            }
            if (dtype !== "object_list") {
              nextField.fields = [];
            }
            onChange(nextField);
          }}
          title={extractionDtypeLabel(translate, dtype)}
        >
          {extractionDtypeLabel(translate, dtype)}
        </Button>
      ))}
    </div>
  );
}

function ChildFieldEditor({
  child,
  childIndex,
  field,
  fieldIndex,
  schema,
  translate,
  onSchemaChange,
}: {
  child: DocumentExtractionChildFieldDraft;
  childIndex: number;
  field: DocumentExtractionFieldDraft;
  fieldIndex: number;
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  const deleteChild = () =>
    onSchemaChange(
      updateSchemaField(schema, fieldIndex, {
        fields: field.fields.filter((_, index) => index !== childIndex),
      }),
    );

  return (
    <Collapsible
      key={`${schema.id}-field-${fieldIndex}-child-${childIndex}`}
      defaultOpen={field.fields.length <= 2 || !child.name.trim()}
      className="space-y-2 rounded-md border bg-muted/20 p-2"
    >
      <div className="flex flex-wrap items-center gap-2">
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="group h-8 min-w-0 flex-1 justify-start gap-2 px-2 text-left"
          >
            <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=closed]:-rotate-90" />
            <span className="min-w-0 flex-1 truncate font-mono text-sm">
              {child.name ||
                translate(
                  "custom.pages.settings.ai.content_enrichment_editor.field_name_placeholder",
                )}
            </span>
            <Badge variant="secondary" className="shrink-0 font-mono">
              {extractionDtypeLabel(translate, child.dtype)}
            </Badge>
            {child.required ? (
              <Badge variant="outline" className="shrink-0">
                {translate("custom.pages.settings.ai.content_enrichment_editor.field_required")}
              </Badge>
            ) : null}
          </Button>
        </CollapsibleTrigger>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          onClick={deleteChild}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <CollapsibleContent className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={child.name}
            onChange={(event) =>
              onSchemaChange(
                updateSchemaField(
                  schema,
                  fieldIndex,
                  updateChildSchemaField(field, childIndex, { name: event.target.value }),
                ),
              )
            }
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.field_name_placeholder",
            )}
            className="h-8 min-w-[120px] flex-1 font-mono text-sm"
          />
          <div className="inline-flex h-8 items-center gap-0.5 rounded-md border bg-background p-0.5">
            {CHILD_EXTRACTION_DTYPES.map((dtype) => (
              <Button
                key={dtype}
                type="button"
                variant={child.dtype === dtype ? "default" : "ghost"}
                size="sm"
                className="h-7 px-2 font-mono text-[11px]"
                onClick={() =>
                  onSchemaChange(
                    updateSchemaField(
                      schema,
                      fieldIndex,
                      updateChildSchemaField(field, childIndex, { dtype }),
                    ),
                  )
                }
              >
                {extractionDtypeLabel(translate, dtype)}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-2 rounded-md border bg-background px-2 py-1">
            <Switch
              checked={child.required}
              onCheckedChange={(checked) =>
                onSchemaChange(
                  updateSchemaField(
                    schema,
                    fieldIndex,
                    updateChildSchemaField(field, childIndex, { required: checked }),
                  ),
                )
              }
            />
            <span className="text-xs">
              {translate("custom.pages.settings.ai.content_enrichment_editor.field_required")}
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="ml-auto h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={deleteChild}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
        <Textarea
          rows={2}
          value={child.description}
          onChange={(event) =>
            onSchemaChange(
              updateSchemaField(
                schema,
                fieldIndex,
                updateChildSchemaField(field, childIndex, { description: event.target.value }),
              ),
            )
          }
          placeholder={translate(
            "custom.pages.settings.ai.content_enrichment_editor.field_description_placeholder",
          )}
          className="text-sm"
        />
      </CollapsibleContent>
    </Collapsible>
  );
}

function ObjectListChildFieldsEditor({
  field,
  fieldIndex,
  schema,
  translate,
  onSchemaChange,
}: {
  field: DocumentExtractionFieldDraft;
  fieldIndex: number;
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  return (
    <div className="space-y-2 rounded-md border bg-background p-2">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">
          {translate("custom.pages.settings.ai.content_enrichment_editor.object_list_fields")}
        </Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() =>
            onSchemaChange(
              updateSchemaField(schema, fieldIndex, {
                fields: [...field.fields, createEmptyExtractionChildFieldDraft()],
              }),
            )
          }
        >
          <Plus className="h-3 w-3" />
          {translate("custom.pages.settings.ai.content_enrichment_editor.add_child_field")}
        </Button>
      </div>
      <div className="space-y-2">
        {field.fields.map((child, childIndex) => (
          <ChildFieldEditor
            key={`${schema.id}-field-${fieldIndex}-child-${childIndex}`}
            child={child}
            childIndex={childIndex}
            field={field}
            fieldIndex={fieldIndex}
            schema={schema}
            translate={translate}
            onSchemaChange={onSchemaChange}
          />
        ))}
      </div>
    </div>
  );
}

function ExampleValueEditor({
  example,
  exampleIndex,
  field,
  fieldIndex,
  schema,
  translate,
  onSchemaChange,
}: {
  example: DocumentExtractionExampleDraft;
  exampleIndex: number;
  field: DocumentExtractionFieldDraft;
  fieldIndex: number;
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  if (field.dtype === "object_list") {
    return (
      <div className="grid gap-2 sm:grid-cols-2">
        {field.fields.map((child) => (
          <div key={child.name} className="space-y-1">
            <Label className="text-[11px] text-muted-foreground">
              {child.name ||
                translate("custom.pages.settings.ai.content_enrichment_editor.field_name")}
            </Label>
            {child.dtype === "bool" ? (
              <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-2">
                <Switch
                  checked={example.child_values[child.name] === "true"}
                  onCheckedChange={(checked) =>
                    onSchemaChange(
                      updateSchemaField(
                        schema,
                        fieldIndex,
                        updateFieldExampleChildValue(
                          field,
                          exampleIndex,
                          child.name,
                          checked ? "true" : "false",
                        ),
                      ),
                    )
                  }
                />
                <span className="text-xs text-muted-foreground">
                  {example.child_values[child.name] === "true"
                    ? translate(
                        "custom.pages.settings.ai.content_enrichment_editor.example_bool_true",
                      )
                    : translate(
                        "custom.pages.settings.ai.content_enrichment_editor.example_bool_false",
                      )}
                </span>
              </div>
            ) : child.dtype === "list" ? (
              <Textarea
                rows={3}
                value={example.child_values[child.name] ?? ""}
                onChange={(event) =>
                  onSchemaChange(
                    updateSchemaField(
                      schema,
                      fieldIndex,
                      updateFieldExampleChildValue(
                        field,
                        exampleIndex,
                        child.name,
                        event.target.value,
                      ),
                    ),
                  )
                }
                placeholder={translate(
                  "custom.pages.settings.ai.content_enrichment_editor.example_list_placeholder",
                )}
                className="text-sm"
              />
            ) : (
              <Input
                value={example.child_values[child.name] ?? ""}
                onChange={(event) =>
                  onSchemaChange(
                    updateSchemaField(
                      schema,
                      fieldIndex,
                      updateFieldExampleChildValue(
                        field,
                        exampleIndex,
                        child.name,
                        event.target.value,
                      ),
                    ),
                  )
                }
                placeholder={extractionDtypeLabel(translate, child.dtype)}
                className="h-8 text-sm"
              />
            )}
          </div>
        ))}
      </div>
    );
  }

  if (field.dtype === "bool") {
    return (
      <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-2">
        <Switch
          checked={example.value === "true"}
          onCheckedChange={(checked) =>
            onSchemaChange(
              updateSchemaField(
                schema,
                fieldIndex,
                updateFieldExample(field, exampleIndex, {
                  value: checked ? "true" : "false",
                }),
              ),
            )
          }
        />
        <span className="text-xs text-muted-foreground">
          {example.value === "true"
            ? translate("custom.pages.settings.ai.content_enrichment_editor.example_bool_true")
            : translate("custom.pages.settings.ai.content_enrichment_editor.example_bool_false")}
        </span>
      </div>
    );
  }

  if (field.dtype === "list") {
    return (
      <Textarea
        rows={3}
        value={example.value}
        onChange={(event) =>
          onSchemaChange(
            updateSchemaField(
              schema,
              fieldIndex,
              updateFieldExample(field, exampleIndex, { value: event.target.value }),
            ),
          )
        }
        placeholder={translate(
          "custom.pages.settings.ai.content_enrichment_editor.example_list_placeholder",
        )}
        className="text-sm"
      />
    );
  }

  return (
    <Input
      value={example.value}
      onChange={(event) =>
        onSchemaChange(
          updateSchemaField(
            schema,
            fieldIndex,
            updateFieldExample(field, exampleIndex, { value: event.target.value }),
          ),
        )
      }
      placeholder={extractionDtypeLabel(translate, field.dtype)}
      className="h-8 text-sm"
    />
  );
}

function ExtractionExampleEditor({
  example,
  exampleIndex,
  field,
  fieldIndex,
  schema,
  translate,
  setExampleTextRef,
  onCaptureSelectionFromExampleText,
  onSchemaChange,
}: {
  example: DocumentExtractionExampleDraft;
  exampleIndex: number;
  field: DocumentExtractionFieldDraft;
  fieldIndex: number;
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  setExampleTextRef: ExampleTextRefSetter;
  onCaptureSelectionFromExampleText: CaptureExampleTextSelection;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  const exampleKey = `${fieldIndex}-${exampleIndex}`;

  return (
    <div
      key={`${schema.id}-field-${fieldIndex}-example-${exampleIndex}`}
      className="space-y-2 rounded-md border bg-muted/20 p-2"
    >
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">
          {translate("custom.pages.settings.ai.content_enrichment_editor.example_text")}
        </Label>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          onClick={() =>
            onSchemaChange(
              updateSchemaField(schema, fieldIndex, {
                examples: field.examples.filter((_, index) => index !== exampleIndex),
              }),
            )
          }
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <Textarea
        ref={setExampleTextRef(exampleKey)}
        rows={3}
        value={example.text}
        onChange={(event) =>
          onSchemaChange(
            updateSchemaField(
              schema,
              fieldIndex,
              updateFieldExample(field, exampleIndex, { text: event.target.value }),
            ),
          )
        }
        placeholder={translate(
          "custom.pages.settings.ai.content_enrichment_editor.example_text_placeholder",
        )}
        className="text-sm"
      />
      <div className="space-y-1">
        <Label className="text-xs">
          {translate("custom.pages.settings.ai.content_enrichment_editor.example_anchor_label")}
        </Label>
        <div className="flex gap-1">
          <Textarea
            rows={2}
            value={example.extraction_text}
            onChange={(event) =>
              onSchemaChange(
                updateSchemaField(
                  schema,
                  fieldIndex,
                  updateFieldExample(field, exampleIndex, {
                    extraction_text: event.target.value,
                  }),
                ),
              )
            }
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.example_anchor_placeholder",
            )}
            className="min-h-16 text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 shrink-0 px-2 text-xs"
            onClick={() =>
              onCaptureSelectionFromExampleText(exampleKey, (selected) =>
                onSchemaChange(
                  updateSchemaField(
                    schema,
                    fieldIndex,
                    updateFieldExample(field, exampleIndex, {
                      extraction_text: selected,
                    }),
                  ),
                ),
              )
            }
            title={translate(
              "custom.pages.settings.ai.content_enrichment_editor.use_selection_hint",
            )}
          >
            {translate("custom.pages.settings.ai.content_enrichment_editor.use_selection")}
          </Button>
        </div>
        {example.extraction_text.trim() &&
        !example.text.includes(example.extraction_text.trim()) ? (
          <p className="text-[11px] text-destructive">
            {translate(
              "custom.pages.settings.ai.content_enrichment_editor.example_anchor_not_in_text",
            )}
          </p>
        ) : !example.extraction_text.trim() ? (
          <p className="text-[11px] text-muted-foreground">
            {translate(
              "custom.pages.settings.ai.content_enrichment_editor.example_anchor_missing_hint",
            )}
          </p>
        ) : null}
      </div>
      <Label className="text-xs">
        {translate("custom.pages.settings.ai.content_enrichment_editor.example_value")}
      </Label>
      <ExampleValueEditor
        example={example}
        exampleIndex={exampleIndex}
        field={field}
        fieldIndex={fieldIndex}
        schema={schema}
        translate={translate}
        onSchemaChange={onSchemaChange}
      />
    </div>
  );
}

function FieldExamplesEditor({
  field,
  fieldIndex,
  schema,
  translate,
  setExampleTextRef,
  onCaptureSelectionFromExampleText,
  onSchemaChange,
}: {
  field: DocumentExtractionFieldDraft;
  fieldIndex: number;
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  setExampleTextRef: ExampleTextRefSetter;
  onCaptureSelectionFromExampleText: CaptureExampleTextSelection;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  return (
    <div className="space-y-2 rounded-md border bg-background p-2">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs">
          {translate("custom.pages.settings.ai.content_enrichment_editor.field_examples")}
        </Label>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={() =>
              onSchemaChange(
                updateSchemaField(schema, fieldIndex, {
                  examples: [...field.examples, createEmptyExtractionExampleDraft()],
                }),
              )
            }
          >
            <Plus className="h-3 w-3" />
            {translate("custom.pages.settings.ai.content_enrichment_editor.add_example")}
          </Button>
        </div>
      </div>
      {field.examples.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {translate("custom.pages.settings.ai.content_enrichment_editor.empty_examples")}
        </p>
      ) : (
        <div className="space-y-2">
          {field.examples.map((example, exampleIndex) => (
            <ExtractionExampleEditor
              key={`${schema.id}-field-${fieldIndex}-example-${exampleIndex}`}
              example={example}
              exampleIndex={exampleIndex}
              field={field}
              fieldIndex={fieldIndex}
              schema={schema}
              translate={translate}
              setExampleTextRef={setExampleTextRef}
              onCaptureSelectionFromExampleText={onCaptureSelectionFromExampleText}
              onSchemaChange={onSchemaChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ExtractionFieldEditor({
  field,
  fieldIndex,
  schema,
  translate,
  setExampleTextRef,
  onCaptureSelectionFromExampleText,
  onSchemaChange,
}: {
  field: DocumentExtractionFieldDraft;
  fieldIndex: number;
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  setExampleTextRef: ExampleTextRefSetter;
  onCaptureSelectionFromExampleText: CaptureExampleTextSelection;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  const updateField = (patch: Partial<DocumentExtractionFieldDraft>) =>
    onSchemaChange(updateSchemaField(schema, fieldIndex, patch));

  return (
    <Collapsible
      key={`${schema.id}-field-${fieldIndex}`}
      defaultOpen={schema.fields.length <= 2 || !field.name.trim()}
      className="space-y-2 rounded-md border bg-muted/20 p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="group h-8 min-w-0 flex-1 justify-start gap-2 px-2 text-left"
          >
            <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=closed]:-rotate-90" />
            <span className="min-w-0 flex-1 truncate font-mono text-sm">
              {field.name ||
                translate(
                  "custom.pages.settings.ai.content_enrichment_editor.field_name_placeholder",
                )}
            </span>
            <Badge variant="secondary" className="shrink-0 font-mono">
              {extractionDtypeLabel(translate, field.dtype)}
            </Badge>
            {field.required ? (
              <Badge variant="outline" className="shrink-0">
                {translate("custom.pages.settings.ai.content_enrichment_editor.field_required")}
              </Badge>
            ) : null}
            <Badge variant="outline" className="shrink-0">
              {field.examples.length}
            </Badge>
          </Button>
        </CollapsibleTrigger>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          onClick={() =>
            onSchemaChange({
              ...schema,
              fields: schema.fields.filter((_, index) => index !== fieldIndex),
            })
          }
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <CollapsibleContent className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={field.name}
            onChange={(event) => updateField({ name: event.target.value })}
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.field_name_placeholder",
            )}
            className="h-8 min-w-[140px] max-w-[240px] flex-1 font-mono text-sm"
          />
          <FieldDtypeControls field={field} translate={translate} onChange={updateField} />
          <div className="flex items-center gap-2 rounded-md border bg-background px-2 py-1">
            <Switch
              checked={field.required}
              onCheckedChange={(checked) => updateField({ required: checked })}
            />
            <span className="text-xs">
              {translate("custom.pages.settings.ai.content_enrichment_editor.field_required")}
            </span>
          </div>
          {field.dtype === "list" || field.dtype === "object_list" ? (
            <div
              className="flex items-center gap-2 rounded-md border bg-background px-2 py-1"
              title={translate(
                "custom.pages.settings.ai.content_enrichment_editor.field_clustered_under_heading_hint",
              )}
            >
              <Switch
                checked={field.clustered_under_heading}
                onCheckedChange={(checked) => updateField({ clustered_under_heading: checked })}
              />
              <span className="text-xs">
                {translate(
                  "custom.pages.settings.ai.content_enrichment_editor.field_clustered_under_heading",
                )}
              </span>
            </div>
          ) : null}
        </div>
        <Textarea
          rows={2}
          value={field.description}
          onChange={(event) => updateField({ description: event.target.value })}
          placeholder={translate(
            "custom.pages.settings.ai.content_enrichment_editor.field_description_placeholder",
          )}
          className="text-sm"
        />
        {field.dtype === "object_list" ? (
          <ObjectListChildFieldsEditor
            field={field}
            fieldIndex={fieldIndex}
            schema={schema}
            translate={translate}
            onSchemaChange={onSchemaChange}
          />
        ) : null}
        <FieldExamplesEditor
          field={field}
          fieldIndex={fieldIndex}
          schema={schema}
          translate={translate}
          setExampleTextRef={setExampleTextRef}
          onCaptureSelectionFromExampleText={onCaptureSelectionFromExampleText}
          onSchemaChange={onSchemaChange}
        />
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ExtractionFieldListEditor({
  schema,
  translate,
  setExampleTextRef,
  onCaptureSelectionFromExampleText,
  onSchemaChange,
}: {
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  setExampleTextRef: ExampleTextRefSetter;
  onCaptureSelectionFromExampleText: CaptureExampleTextSelection;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label>
          {translate("custom.pages.settings.ai.content_enrichment_editor.schema_fields")}
        </Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            onSchemaChange({
              ...schema,
              fields: [...schema.fields, createEmptyExtractionFieldDraft()],
            })
          }
        >
          <Plus className="mr-2 h-4 w-4" />
          {translate("custom.pages.settings.ai.content_enrichment_editor.add_field")}
        </Button>
      </div>

      {schema.fields.length === 0 ? (
        <p className="rounded-md border border-dashed bg-muted/20 px-3 py-6 text-center text-sm text-muted-foreground">
          {translate("custom.pages.settings.ai.content_enrichment_editor.empty_schema_fields")}
        </p>
      ) : (
        <div className="space-y-2">
          {schema.fields.map((field, fieldIndex) => (
            <ExtractionFieldEditor
              key={`${schema.id}-field-${fieldIndex}`}
              field={field}
              fieldIndex={fieldIndex}
              schema={schema}
              translate={translate}
              setExampleTextRef={setExampleTextRef}
              onCaptureSelectionFromExampleText={onCaptureSelectionFromExampleText}
              onSchemaChange={onSchemaChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}
