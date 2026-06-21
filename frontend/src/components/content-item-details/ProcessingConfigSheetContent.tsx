import type { Dispatch, SetStateAction } from "react";

import { Button } from "@/components/ui/button";
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
import { useTranslate } from "@/lib/app-context";
import type { ProcessingConfigFormState } from "@/hooks/useContentItemDetails";

interface ProcessingConfigSheetContentProps {
  form: ProcessingConfigFormState;
  onFormChange: Dispatch<SetStateAction<ProcessingConfigFormState>>;
  onCancel: () => void;
  onApply: () => void;
  idPrefix?: string;
  descriptionKey?: string;
  applyLabel?: string;
}

export function ProcessingConfigSheetContent({
  form,
  onFormChange,
  onCancel,
  onApply,
  idPrefix = "cfg",
  descriptionKey = "custom.content.processing_config.description",
  applyLabel,
}: ProcessingConfigSheetContentProps) {
  const translate = useTranslate();
  const fieldId = (name: string) => `${idPrefix}-${name}`;

  return (
    <>
      <div className="shrink-0 border-b bg-muted/20 px-5 py-4">
        <h3 className="font-semibold">{translate("custom.content.processing_config.title")}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{translate(descriptionKey)}</p>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain p-5">
        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {translate("custom.content.processing_config.ocr_settings")}
          </h4>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor={fieldId("do-ocr")} className="flex-1 cursor-pointer font-medium">
                {translate("custom.content.processing_config.do_ocr")}
              </Label>
              <Switch
                id={fieldId("do-ocr")}
                checked={form.doOcr}
                onCheckedChange={(checked) => onFormChange((prev) => ({ ...prev, doOcr: checked }))}
              />
            </div>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor={fieldId("force-ocr")} className="flex-1 cursor-pointer font-medium">
                {translate("custom.content.processing_config.force_full_page_ocr")}
              </Label>
              <Switch
                id={fieldId("force-ocr")}
                checked={form.forceFullPageOcr}
                onCheckedChange={(checked) =>
                  onFormChange((prev) => ({ ...prev, forceFullPageOcr: checked }))
                }
              />
            </div>
            <div className="space-y-1.5 pt-1">
              <Label htmlFor={fieldId("ocr-lang")} className="text-xs">
                {translate("custom.content.processing_config.ocr_lang")}
              </Label>
              <Input
                id={fieldId("ocr-lang")}
                value={form.ocrLang}
                onChange={(event) =>
                  onFormChange((prev) => ({ ...prev, ocrLang: event.target.value }))
                }
                placeholder={translate("custom.content.processing_config.ocr_lang_hint")}
                className="h-8 text-sm"
              />
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {translate("custom.content.processing_config.table_settings")}
          </h4>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor={fieldId("do-table")} className="flex-1 cursor-pointer font-medium">
                {translate("custom.content.processing_config.do_table_structure")}
              </Label>
              <Switch
                id={fieldId("do-table")}
                checked={form.doTableStructure}
                onCheckedChange={(checked) =>
                  onFormChange((prev) => ({ ...prev, doTableStructure: checked }))
                }
              />
            </div>
            <div className="space-y-1.5 pt-1">
              <Label htmlFor={fieldId("table-mode")} className="text-xs">
                {translate("custom.content.processing_config.table_structure_mode")}
              </Label>
              <Select
                value={form.tableStructureMode || "none"}
                onValueChange={(value) =>
                  onFormChange((prev) => ({
                    ...prev,
                    tableStructureMode: value === "none" ? "" : value,
                  }))
                }
              >
                <SelectTrigger id={fieldId("table-mode")} className="h-8 text-sm">
                  <SelectValue
                    placeholder={translate(
                      "custom.content.processing_config.table_structure_mode_none",
                    )}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">
                    {translate("custom.content.processing_config.table_structure_mode_none")}
                  </SelectItem>
                  <SelectItem value="fast">
                    {translate("custom.content.processing_config.table_structure_mode_fast")}
                  </SelectItem>
                  <SelectItem value="accurate">
                    {translate("custom.content.processing_config.table_structure_mode_accurate")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {translate("custom.content.processing_config.content_enrichment")}
          </h4>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <Label
                htmlFor={fieldId("document-enrichment")}
                className="flex-1 cursor-pointer font-medium"
              >
                {translate("custom.content.processing_config.document_enrichment")}
              </Label>
              <Switch
                id={fieldId("document-enrichment")}
                checked={form.documentEnrichment}
                onCheckedChange={(checked) =>
                  onFormChange((prev) => ({ ...prev, documentEnrichment: checked }))
                }
              />
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {translate("custom.content.processing_config.advanced_settings")}
          </h4>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor={fieldId("images-scale")} className="text-xs">
                {translate("custom.content.processing_config.images_scale")}
              </Label>
              <Input
                id={fieldId("images-scale")}
                value={form.imagesScale}
                onChange={(event) =>
                  onFormChange((prev) => ({ ...prev, imagesScale: event.target.value }))
                }
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={fieldId("image-export-dpi")} className="text-xs">
                {translate("custom.content.processing_config.image_export_dpi")}
              </Label>
              <Input
                id={fieldId("image-export-dpi")}
                value={form.imageExportDpi}
                onChange={(event) =>
                  onFormChange((prev) => ({ ...prev, imageExportDpi: event.target.value }))
                }
                className="h-8 text-sm"
                placeholder="300"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 justify-end gap-2 border-t bg-muted/20 px-5 py-3">
        <Button variant="outline" size="sm" onClick={onCancel}>
          {translate("custom.content.processing_config.cancel")}
        </Button>
        <Button size="sm" onClick={onApply}>
          {applyLabel ?? translate("custom.content.processing_config.apply")}
        </Button>
      </div>
    </>
  );
}
