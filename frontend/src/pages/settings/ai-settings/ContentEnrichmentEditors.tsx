import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertCircle,
  ChevronDown,
  Download,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { contentApi, type AiSettingEntry } from "@/dataProvider";
import {
  applyClassSettingsImport,
  buildClassSettingsExport,
  cloneDocumentClassDraft,
  createEmptyDocumentClassDraft,
  createEmptyExtractionSchemaDraft,
  removeDocumentClassDraft,
  replaceDocumentClassDraft,
} from "@/lib/content-enrichment-admin";
import { downloadBlob } from "@/lib/chat-export";
import { useNotify } from "@/lib/app-context";
import { ExtractionFieldListEditor } from "./ExtractionFieldListEditor";
import { SchemaScenesEditor } from "./SchemaScenesEditor";
import type {
  DocumentClassDraft,
  DocumentExtractionSchemaDraft,
} from "@/lib/content-enrichment-admin";

type FormValue = string | boolean;

type TranslateFn = (key: string, options?: unknown) => string;

type ItemTranslator = (
  translate: TranslateFn,
  key: string,
  part: "label" | "description",
  fallback: string,
) => string;

type BaseEditorProps = {
  item: AiSettingEntry;
  translate: TranslateFn;
  itemTranslation: ItemTranslator;
  resettingField: string | null;
  onResetField: (key: string) => void;
};

function defaultTextareaRows(item: AiSettingEntry): number {
  if (item.input_type === "json") {
    return 12;
  }
  if (item.key === "chat_system_prompt" || item.key === "chat_tool_prompt") {
    return 18;
  }
  return 6;
}

export function AiSettingField({
  item,
  value,
  framed = true,
  translate,
  itemTranslation,
  resettingField,
  onResetField,
  onFieldChange,
}: BaseEditorProps & {
  value: FormValue | undefined;
  framed?: boolean;
  onFieldChange: (key: string, value: FormValue) => void;
}) {
  const label = itemTranslation(translate, item.key, "label", item.label);
  const description = itemTranslation(translate, item.key, "description", item.description);

  return (
    <div key={item.key} className={framed ? "space-y-2 rounded-lg border p-4" : "space-y-2 py-4"}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label htmlFor={`ai-setting-${item.key}`}>{label}</Label>
            <Badge variant={item.overridden ? "default" : "secondary"}>
              {item.overridden
                ? translate("custom.pages.settings.ai.status.overridden")
                : translate("custom.pages.settings.ai.status.default")}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            onResetField(item.key);
          }}
          disabled={resettingField === item.key}
        >
          <RotateCcw className="mr-2 h-4 w-4" />
          {translate("custom.pages.settings.ai.actions.reset_field")}
        </Button>
      </div>
      {item.input_type === "boolean" ? (
        <div className="flex items-center justify-end">
          <Switch
            id={`ai-setting-${item.key}`}
            checked={Boolean(value)}
            onCheckedChange={(checked: boolean) => onFieldChange(item.key, checked)}
          />
        </div>
      ) : item.input_type === "textarea" || item.input_type === "json" ? (
        <Textarea
          id={`ai-setting-${item.key}`}
          value={typeof value === "string" ? value : ""}
          rows={defaultTextareaRows(item)}
          onChange={(event) => onFieldChange(item.key, event.target.value)}
        />
      ) : (
        <Input
          id={`ai-setting-${item.key}`}
          type={item.input_type === "number" ? "number" : "text"}
          value={typeof value === "string" ? value : ""}
          onChange={(event) => onFieldChange(item.key, event.target.value)}
        />
      )}
    </div>
  );
}

function SectionIntro({
  item,
  translate,
  itemTranslation,
  children,
}: BaseEditorProps & { children?: ReactNode }) {
  const description = itemTranslation(translate, item.key, "description", item.description);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-muted-foreground">{description}</p>
      {children ? <div className="flex items-center gap-2">{children}</div> : null}
    </div>
  );
}

type ClassEditorState = {
  mode: "create" | "edit";
  index: number | null;
  draft: DocumentClassDraft;
  dirty: boolean;
};

export type DocumentClassEditorRouteMode = "list" | "create" | "edit";

type DocumentClassRouteCloseOptions = {
  replace?: boolean;
};

const documentClassDisplayName = (draft: DocumentClassDraft, translate: TranslateFn) =>
  draft.name.trim() ||
  translate("custom.pages.settings.ai.content_enrichment_editor.unnamed_class");

const safeSettingsFilename = (name: string, suffix: string) => {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${base || "content-class"}-${suffix}.json`;
};

const readJsonFile = async (file: File): Promise<unknown> => JSON.parse(await file.text());

function ClassCreateActions({
  className,
  savingDocumentClasses,
  size = "sm",
  translate,
  onCreateClass,
  onImportClass,
}: {
  className?: string;
  savingDocumentClasses: boolean;
  size?: "sm" | "default";
  translate: TranslateFn;
  onCreateClass: () => void;
  onImportClass: () => void;
}) {
  return (
    <div className={`inline-flex items-center ${className ?? ""}`.trim()}>
      <Button
        type="button"
        variant="outline"
        size={size}
        className="rounded-r-none border-r-0"
        onClick={onCreateClass}
      >
        <Plus className={size === "sm" ? "mr-1 h-3.5 w-3.5" : "mr-2 h-4 w-4"} />
        {translate("custom.pages.settings.ai.content_enrichment_editor.add_class")}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size={size === "sm" ? "icon-sm" : "icon"}
            className="rounded-l-none"
            disabled={savingDocumentClasses}
          >
            <ChevronDown className="h-4 w-4" />
            <span className="sr-only">
              {translate("custom.pages.settings.ai.content_enrichment_editor.add_class_options")}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem disabled={savingDocumentClasses} onSelect={onImportClass}>
            <Upload className="mr-2 h-4 w-4" />
            {translate("custom.pages.settings.ai.content_enrichment_editor.import_class")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function ClassRowActions({
  classIndex,
  draft,
  translate,
  onDeleteClass,
  onEditClass,
  onExportClassSettings,
  onExportExtractedDataCsv,
}: {
  classIndex: number;
  draft: DocumentClassDraft;
  translate: TranslateFn;
  onDeleteClass: (index: number) => void;
  onEditClass: (index: number) => void;
  onExportClassSettings: (draft: DocumentClassDraft) => void;
  onExportExtractedDataCsv: (draft: DocumentClassDraft) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={(event) => event.stopPropagation()}
        >
          <MoreHorizontal className="h-4 w-4" />
          <span className="sr-only">
            {translate("custom.pages.settings.ai.content_enrichment_editor.table_actions")}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          onClick={(event) => {
            event.stopPropagation();
            onExportClassSettings(draft);
          }}
        >
          <Download className="mr-2 h-4 w-4" />
          {translate("custom.pages.settings.ai.content_enrichment_editor.export_class")}
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={!draft.name.trim()}
          onClick={(event) => {
            event.stopPropagation();
            onExportExtractedDataCsv(draft);
          }}
        >
          <Download className="mr-2 h-4 w-4" />
          {translate("custom.pages.settings.ai.content_enrichment_editor.export_data_csv")}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={(event) => {
            event.stopPropagation();
            onEditClass(classIndex);
          }}
        >
          <Pencil className="mr-2 h-4 w-4" />
          {translate("custom.pages.settings.ai.content_enrichment_editor.edit_class")}
        </DropdownMenuItem>
        <DropdownMenuItem
          className="text-destructive"
          onClick={(event) => {
            event.stopPropagation();
            onDeleteClass(classIndex);
          }}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          {translate("custom.pages.settings.ai.content_enrichment_editor.delete_class")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ClassEditorHeaderActions({
  activeDraft,
  activeSavedDraft,
  activeSavedClassName,
  translate,
  onExportClassSettings,
  onExportExtractedDataCsv,
}: {
  activeDraft: DocumentClassDraft;
  activeSavedDraft: DocumentClassDraft | null;
  activeSavedClassName: string;
  translate: TranslateFn;
  onExportClassSettings: (draft: DocumentClassDraft) => void;
  onExportExtractedDataCsv: (draft: DocumentClassDraft | null | undefined) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onExportClassSettings(activeDraft)}
      >
        <Download className="mr-2 h-4 w-4" />
        {translate("custom.pages.settings.ai.content_enrichment_editor.export_class")}
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onExportExtractedDataCsv(activeSavedDraft)}
        disabled={!activeSavedClassName}
      >
        <Download className="mr-2 h-4 w-4" />
        {translate("custom.pages.settings.ai.content_enrichment_editor.export_data_csv")}
      </Button>
    </div>
  );
}

function DocumentClassBasicFields({
  draft,
  translate,
  onDraftChange,
}: {
  draft: DocumentClassDraft;
  translate: TranslateFn;
  onDraftChange: (patch: Partial<DocumentClassDraft>) => void;
}) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="content-enrichment-class-name">
            {translate("custom.pages.settings.ai.content_enrichment_editor.class_name")}
          </Label>
          <Input
            id="content-enrichment-class-name"
            value={draft.name}
            onChange={(event) => onDraftChange({ name: event.target.value })}
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.class_name_placeholder",
            )}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="content-enrichment-class-aliases">
            {translate("custom.pages.settings.ai.content_enrichment_editor.class_aliases")}
          </Label>
          <Input
            id="content-enrichment-class-aliases"
            value={draft.aliases_text}
            onChange={(event) => onDraftChange({ aliases_text: event.target.value })}
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.class_aliases_placeholder",
            )}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="content-enrichment-class-description">
          {translate("custom.pages.settings.ai.content_enrichment_editor.class_description")}
        </Label>
        <Textarea
          id="content-enrichment-class-description"
          rows={4}
          value={draft.description}
          onChange={(event) => onDraftChange({ description: event.target.value })}
          placeholder={translate(
            "custom.pages.settings.ai.content_enrichment_editor.class_description_placeholder",
          )}
        />
      </div>
    </>
  );
}

function ExtractionSchemaBasicFields({
  schema,
  translate,
  onSchemaChange,
}: {
  schema: DocumentExtractionSchemaDraft;
  translate: TranslateFn;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft) => void;
}) {
  return (
    <>
      <div className="grid gap-4 md:grid-cols-1">
        <div className="space-y-1.5">
          <Label htmlFor="content-enrichment-schema-name">
            {translate("custom.pages.settings.ai.content_enrichment_editor.schema_name")}
          </Label>
          <Input
            id="content-enrichment-schema-name"
            value={schema.name}
            onChange={(event) => onSchemaChange({ ...schema, name: event.target.value })}
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.schema_name_placeholder",
            )}
          />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-1">
        <div className="space-y-1.5">
          <Label htmlFor="content-enrichment-schema-description">
            {translate("custom.pages.settings.ai.content_enrichment_editor.schema_description")}
          </Label>
          <Input
            id="content-enrichment-schema-description"
            value={schema.description}
            onChange={(event) => onSchemaChange({ ...schema, description: event.target.value })}
            placeholder={translate(
              "custom.pages.settings.ai.content_enrichment_editor.schema_description_placeholder",
            )}
          />
        </div>
      </div>
    </>
  );
}

function ExtractionSchemaSection({
  className,
  schema,
  translate,
  onSchemaChange,
  children,
}: {
  className: string;
  schema: DocumentExtractionSchemaDraft | null;
  translate: TranslateFn;
  onSchemaChange: (schema: DocumentExtractionSchemaDraft | null) => void;
  children: ReactNode;
}) {
  return (
    <div className="space-y-4 rounded-md border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Label className="text-sm">
            {translate("custom.pages.settings.ai.content_enrichment_editor.extraction_for_class")}
          </Label>
          <p className="mt-1 text-xs text-muted-foreground">
            {translate(
              "custom.pages.settings.ai.content_enrichment_editor.extraction_for_class_hint",
            )}
          </p>
        </div>
        <Switch
          checked={Boolean(schema)}
          onCheckedChange={(checked) =>
            onSchemaChange(checked ? createEmptyExtractionSchemaDraft(className) : null)
          }
        />
      </div>

      {schema ? (
        <div className="space-y-4 border-t pt-4">
          <ExtractionSchemaBasicFields
            schema={schema}
            translate={translate}
            onSchemaChange={onSchemaChange}
          />
          {children}
        </div>
      ) : null}
    </div>
  );
}

export function ContentEnrichmentDocumentClassEditor({
  documentClassesDraft,
  savingDocumentClasses,
  onSaveDocumentClasses,
  routeMode = "list",
  selectedClassId,
  onOpenDocumentClass,
  onCreateDocumentClass,
  onCloseDocumentClassDetail,
  onDocumentClassRouteLabelChange,
  ...props
}: BaseEditorProps & {
  documentClassesDraft: DocumentClassDraft[];
  savingDocumentClasses: boolean;
  onSaveDocumentClasses: (nextClasses: DocumentClassDraft[]) => Promise<void>;
  routeMode?: DocumentClassEditorRouteMode;
  selectedClassId?: string;
  onOpenDocumentClass?: (id: string) => void;
  onCreateDocumentClass?: () => void;
  onCloseDocumentClassDetail?: (options?: DocumentClassRouteCloseOptions) => void;
  onDocumentClassRouteLabelChange?: (label: string | null) => void;
}) {
  const totalCount = documentClassesDraft.length;
  const newCount = documentClassesDraft.filter((entry) => !entry.version).length;
  const classesWithoutExtraction = documentClassesDraft.filter((entry) => !entry.extraction_schema);
  const missingExtractionCount = classesWithoutExtraction.length;
  const missingExtractionNames = classesWithoutExtraction
    .map((entry) => entry.name.trim())
    .filter(Boolean)
    .slice(0, 3)
    .join(", ");
  const [editorState, setEditorState] = useState<ClassEditorState | null>(null);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [deletingClass, setDeletingClass] = useState(false);
  const exampleTextRefs = useRef(new Map<string, HTMLTextAreaElement | null>());
  const classSettingsImportInputRef = useRef<HTMLInputElement | null>(null);
  const { translate } = props;
  const notify = useNotify();

  const setExampleTextRef = (key: string) => (node: HTMLTextAreaElement | null) => {
    if (node) {
      exampleTextRefs.current.set(key, node);
    } else {
      exampleTextRefs.current.delete(key);
    }
  };

  const captureSelectionFromExampleText = (key: string, onSelect: (selection: string) => void) => {
    const node = exampleTextRefs.current.get(key);
    if (!node) return;
    const start = node.selectionStart;
    const end = node.selectionEnd;
    if (start === null || end === null || end <= start) return;
    const selected = node.value.slice(start, end).trim();
    if (selected) {
      onSelect(selected);
    }
  };

  const routeControlled = routeMode !== "list";
  const closeEditor = (options?: DocumentClassRouteCloseOptions) => {
    if (routeControlled && onCloseDocumentClassDetail) {
      onCloseDocumentClassDetail(options);
      return;
    }
    setEditorState(null);
  };

  const openCreateDrawer = () => {
    if (onCreateDocumentClass) {
      onCreateDocumentClass();
      return;
    }
    setEditorState({
      mode: "create",
      index: null,
      draft: createEmptyDocumentClassDraft(),
      dirty: true,
    });
  };

  const openEditDrawer = (index: number) => {
    const draft = documentClassesDraft[index];
    if (draft && onOpenDocumentClass) {
      onOpenDocumentClass(draft.id);
      return;
    }
    setEditorState({
      mode: "edit",
      index,
      draft: cloneDocumentClassDraft(documentClassesDraft[index]),
      dirty: false,
    });
  };

  useEffect(() => {
    if (routeMode === "list") {
      setEditorState(null);
      onDocumentClassRouteLabelChange?.(null);
      return;
    }

    if (routeMode === "create") {
      onDocumentClassRouteLabelChange?.(
        translate("custom.pages.settings.ai.content_enrichment_editor.create_class_dialog_title"),
      );
      setEditorState((current) =>
        current?.mode === "create"
          ? current
          : {
              mode: "create",
              index: null,
              draft: createEmptyDocumentClassDraft(),
              dirty: true,
            },
      );
      return;
    }

    const classIndex = documentClassesDraft.findIndex((entry) => entry.id === selectedClassId);
    if (classIndex === -1) {
      setEditorState(null);
      onDocumentClassRouteLabelChange?.(
        translate("custom.pages.settings.ai.content_enrichment_editor.class_not_found_title"),
      );
      return;
    }

    const draft = documentClassesDraft[classIndex];
    onDocumentClassRouteLabelChange?.(documentClassDisplayName(draft, translate));
    setEditorState((current) =>
      current?.mode === "edit" && current.draft.id === draft.id
        ? current
        : {
            mode: "edit",
            index: classIndex,
            draft: cloneDocumentClassDraft(draft),
            dirty: false,
          },
    );
  }, [
    documentClassesDraft,
    onDocumentClassRouteLabelChange,
    translate,
    routeMode,
    selectedClassId,
  ]);

  const updateEditorDraft = (patch: Partial<DocumentClassDraft>) => {
    setEditorState((current) =>
      current ? { ...current, draft: { ...current.draft, ...patch }, dirty: true } : current,
    );
  };

  const updateEditorSchema = (schema: DocumentExtractionSchemaDraft | null) => {
    updateEditorDraft({ extraction_schema: schema });
  };

  const handleSaveEditor = async () => {
    if (!editorState) {
      return;
    }
    await onSaveDocumentClasses(
      replaceDocumentClassDraft(documentClassesDraft, editorState.index, editorState.draft),
    );
    closeEditor({ replace: true });
  };

  const exportClassSettings = (draft: DocumentClassDraft) => {
    downloadBlob(
      safeSettingsFilename(draft.name, "class-settings"),
      new Blob([JSON.stringify(buildClassSettingsExport(draft), null, 2)], {
        type: "application/json;charset=utf-8",
      }),
    );
  };

  const exportExtractedDataCsvForClass = (draft: DocumentClassDraft | null | undefined) => {
    const className = draft?.name.trim();
    if (!className) return;
    window.open(
      contentApi.getExtractedDataCsvUrl({ document_class: className }),
      "_blank",
      "noopener,noreferrer",
    );
  };

  const handleImportClassSettings = async (file: File | null) => {
    if (!file) return;
    try {
      const payload = await readJsonFile(file);
      const importedDraft = applyClassSettingsImport(createEmptyDocumentClassDraft(), payload);
      setEditorState({
        mode: "create",
        index: null,
        draft: importedDraft,
        dirty: true,
      });
      notify(translate("custom.pages.settings.ai.content_enrichment_editor.import_class_success"), {
        type: "success",
      });
    } catch {
      notify(
        translate("custom.pages.settings.ai.content_enrichment_editor.import_settings_failed"),
        { type: "error" },
      );
    }
  };

  const handleConfirmDelete = async () => {
    if (deleteIndex === null) {
      return;
    }
    setDeletingClass(true);
    try {
      await onSaveDocumentClasses(removeDocumentClassDraft(documentClassesDraft, deleteIndex));
      setDeleteIndex(null);
    } finally {
      setDeletingClass(false);
    }
  };

  const deletingClassName =
    deleteIndex !== null
      ? documentClassesDraft[deleteIndex]?.name ||
        props.translate("custom.pages.settings.ai.content_enrichment_editor.unnamed_class")
      : "";
  const activeDraft = editorState?.draft ?? null;
  const activeSchema = activeDraft?.extraction_schema ?? null;
  const isEditorDirty = editorState?.dirty ?? false;
  const activeSavedDraft =
    editorState?.index !== null && editorState?.index !== undefined
      ? (documentClassesDraft[editorState.index] ?? null)
      : null;
  const activeSavedClassName = activeSavedDraft?.name.trim() ?? "";
  const routeClassMissing = routeMode === "edit" && !activeDraft;
  const showClassList = routeMode === "list" && !editorState;

  return (
    <div key={props.item.key} className="space-y-3 py-2" data-testid="document-classes-table">
      {showClassList ? (
        <>
          <input
            ref={classSettingsImportInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              void handleImportClassSettings(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
          <SectionIntro {...props}>
            <ClassCreateActions
              savingDocumentClasses={savingDocumentClasses}
              translate={props.translate}
              onCreateClass={openCreateDrawer}
              onImportClass={() => classSettingsImportInputRef.current?.click()}
            />
          </SectionIntro>

          {missingExtractionCount > 0 ? (
            <Alert className="border-amber-300 bg-amber-50 text-amber-950 [&>svg]:text-amber-600">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>
                {props.translate(
                  "custom.pages.settings.ai.content_enrichment_editor.missing_extraction_schema_title",
                  { count: missingExtractionCount },
                )}
              </AlertTitle>
              <AlertDescription>
                {props.translate(
                  "custom.pages.settings.ai.content_enrichment_editor.missing_extraction_schema_description",
                  {
                    classes:
                      missingExtractionNames ||
                      props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.unnamed_class",
                      ),
                  },
                )}
              </AlertDescription>
            </Alert>
          ) : null}

          {documentClassesDraft.length === 0 ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-3 py-8 text-center">
              <p className="text-sm font-medium">
                {props.translate(
                  "custom.pages.settings.ai.content_enrichment_editor.empty_classes",
                )}
              </p>
              <ClassCreateActions
                className="mt-4"
                savingDocumentClasses={savingDocumentClasses}
                size="default"
                translate={props.translate}
                onCreateClass={openCreateDrawer}
                onImportClass={() => classSettingsImportInputRef.current?.click()}
              />
            </div>
          ) : (
            <div className="overflow-hidden rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>
                      {props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.table_name",
                      )}
                    </TableHead>
                    <TableHead>
                      {props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.table_aliases",
                      )}
                    </TableHead>
                    <TableHead>
                      {props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.table_status",
                      )}
                    </TableHead>
                    <TableHead className="text-right">
                      {props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.table_fields",
                      )}
                    </TableHead>
                    <TableHead className="w-[90px]">
                      {props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.table_version",
                      )}
                    </TableHead>
                    <TableHead className="w-[80px] text-right">
                      {props.translate(
                        "custom.pages.settings.ai.content_enrichment_editor.table_actions",
                      )}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documentClassesDraft.map((entry, classIndex) => {
                    const schema = entry.extraction_schema;
                    return (
                      <TableRow
                        key={entry.id}
                        className="cursor-pointer"
                        onClick={() => openEditDrawer(classIndex)}
                      >
                        <TableCell className="min-w-[180px] font-medium">
                          {entry.name ||
                            props.translate(
                              "custom.pages.settings.ai.content_enrichment_editor.unnamed_class",
                            )}
                        </TableCell>
                        <TableCell className="max-w-[260px] truncate text-muted-foreground">
                          {entry.aliases_text || " - "}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={schema ? "default" : "outline"}
                            className={
                              schema ? undefined : "border-amber-300 bg-amber-50 text-amber-900"
                            }
                          >
                            {schema
                              ? props.translate(
                                  "custom.pages.settings.ai.content_enrichment_editor.class_has_extraction",
                                )
                              : props.translate(
                                  "custom.pages.settings.ai.content_enrichment_editor.class_no_extraction",
                                )}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">
                          {schema?.fields.length ?? 0}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col items-start gap-1">
                            <Badge variant={entry.version ? "outline" : "secondary"}>
                              {entry.version
                                ? props.translate(
                                    "custom.pages.settings.ai.content_enrichment_editor.class_version_badge",
                                    { version: entry.version },
                                  )
                                : props.translate(
                                    "custom.pages.settings.ai.content_enrichment_editor.new_badge",
                                  )}
                            </Badge>
                            {schema ? (
                              <Badge variant="outline">
                                {props.translate(
                                  "custom.pages.settings.ai.content_enrichment_editor.schema_version_badge",
                                  { version: schema.version ?? 1 },
                                )}
                              </Badge>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <ClassRowActions
                            classIndex={classIndex}
                            draft={entry}
                            translate={props.translate}
                            onDeleteClass={setDeleteIndex}
                            onEditClass={openEditDrawer}
                            onExportClassSettings={exportClassSettings}
                            onExportExtractedDataCsv={exportExtractedDataCsvForClass}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            {props.translate("custom.pages.settings.ai.content_enrichment_editor.classes_summary", {
              total: totalCount,
              new: newCount,
            })}
          </p>
        </>
      ) : null}

      {routeClassMissing ? (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>
            {props.translate(
              "custom.pages.settings.ai.content_enrichment_editor.class_not_found_title",
            )}
          </AlertTitle>
          <AlertDescription className="space-y-4">
            <p>
              {props.translate(
                "custom.pages.settings.ai.content_enrichment_editor.class_not_found_description",
              )}
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      {editorState && activeDraft ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold">
                {props.translate(
                  editorState.mode === "create"
                    ? "custom.pages.settings.ai.content_enrichment_editor.create_class_dialog_title"
                    : "custom.pages.settings.ai.content_enrichment_editor.edit_class_dialog_title",
                )}
              </h2>
              <p className="text-xs text-muted-foreground">
                {props.translate(
                  "custom.pages.settings.ai.content_enrichment_editor.class_dialog_description",
                )}
              </p>
            </div>
            <ClassEditorHeaderActions
              activeDraft={activeDraft}
              activeSavedDraft={activeSavedDraft}
              activeSavedClassName={activeSavedClassName}
              translate={props.translate}
              onExportClassSettings={exportClassSettings}
              onExportExtractedDataCsv={exportExtractedDataCsvForClass}
            />
          </div>
          <div className="space-y-5">
            <DocumentClassBasicFields
              draft={activeDraft}
              translate={props.translate}
              onDraftChange={updateEditorDraft}
            />

            <ExtractionSchemaSection
              className={activeDraft.name}
              schema={activeSchema}
              translate={props.translate}
              onSchemaChange={updateEditorSchema}
            >
              {activeSchema ? (
                <>
                  <ExtractionFieldListEditor
                    schema={activeSchema}
                    translate={props.translate}
                    setExampleTextRef={setExampleTextRef}
                    onCaptureSelectionFromExampleText={captureSelectionFromExampleText}
                    onSchemaChange={updateEditorSchema}
                  />
                  <SchemaScenesEditor
                    scenes={activeSchema.scenes}
                    fields={activeSchema.fields}
                    translate={props.translate}
                    onChange={(nextScenes) =>
                      updateEditorSchema({ ...activeSchema, scenes: nextScenes })
                    }
                  />
                </>
              ) : null}
            </ExtractionSchemaSection>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => closeEditor()}
              disabled={savingDocumentClasses}
            >
              {props.translate("custom.pages.settings.ai.content_enrichment_editor.dialog_cancel")}
            </Button>
            <Button
              type="button"
              onClick={() => {
                void handleSaveEditor().catch(() => undefined);
              }}
              disabled={savingDocumentClasses || !isEditorDirty}
            >
              {savingDocumentClasses ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {props.translate("custom.pages.settings.ai.content_enrichment_editor.dialog_save")}
            </Button>
          </div>
        </div>
      ) : null}

      <Dialog open={deleteIndex !== null} onOpenChange={(open) => !open && setDeleteIndex(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {props.translate(
                "custom.pages.settings.ai.content_enrichment_editor.delete_class_dialog_title",
              )}
            </DialogTitle>
            <DialogDescription>
              {props.translate(
                "custom.pages.settings.ai.content_enrichment_editor.delete_class_dialog_description",
                { name: deletingClassName },
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteIndex(null)}
              disabled={deletingClass}
            >
              {props.translate("custom.pages.settings.ai.content_enrichment_editor.dialog_cancel")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void handleConfirmDelete()}
              disabled={deletingClass}
            >
              {deletingClass ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {props.translate("custom.pages.settings.ai.content_enrichment_editor.delete_class")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
