import type { Dispatch, SetStateAction } from "react";
import { useTranslate } from "@/lib/app-context";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DataConnectorTypeEntry, DataConnectorTypeFieldEntry } from "@/dataProvider";
import type { SourceFormState } from "@/pages/data-connectors/shared";

/** Map from backend field key to form state key. */
const FIELD_KEY_TO_FORM_KEY: Record<string, keyof SourceFormState> = {
  path: "path",
  endpoint_url: "endpointUrl",
  bucket: "bucket",
  s3_prefix: "s3Prefix",
  access_key: "accessKey",
  secret_key: "secretKey",
  region: "region",
};

/** Keys handled by the watcher/SMB section — skip in the dynamic renderer. */
const WATCHER_FIELD_KEYS = new Set([
  "watcher_type",
  "smb_server",
  "smb_share",
  "smb_port",
  "smb_username",
  "smb_password",
  "smb_domain",
]);

interface SourceFlagSwitchProps {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}

function SourceFlagSwitch({
  id,
  label,
  description,
  checked,
  disabled = false,
  onCheckedChange,
}: SourceFlagSwitchProps) {
  return (
    <div className="flex items-center justify-between rounded-md border p-3">
      <div className="pr-4">
        <Label htmlFor={id} className="font-medium">
          {label}
        </Label>
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className="data-[state=checked]:bg-muted-foreground"
      />
    </div>
  );
}

function DynamicField({
  field,
  form,
  setForm,
}: {
  field: DataConnectorTypeFieldEntry;
  form: SourceFormState;
  setForm: Dispatch<SetStateAction<SourceFormState>>;
}) {
  const formKey = FIELD_KEY_TO_FORM_KEY[field.key];
  if (!formKey) return null;

  const value = form[formKey];
  if (typeof value !== "string") return null;

  const inputId = `source-${field.key}`;

  return (
    <div className="space-y-2">
      <Label htmlFor={inputId}>
        {field.label}
        {field.required && <span className="text-destructive ml-1">*</span>}
      </Label>
      <Input
        id={inputId}
        type={field.input_type === "password" ? "password" : "text"}
        value={value}
        onChange={(event) => setForm((prev) => ({ ...prev, [formKey]: event.target.value }))}
        placeholder={field.placeholder ?? ""}
      />
      {!!field.description && <p className="text-xs text-muted-foreground">{field.description}</p>}
    </div>
  );
}

interface DataConnectorFormFieldsProps {
  form: SourceFormState;
  setForm: Dispatch<SetStateAction<SourceFormState>>;
  sourceTypes: DataConnectorTypeEntry[];
  selectedType: DataConnectorTypeEntry | null;
  pathField: DataConnectorTypeFieldEntry | null;
}

export function DataConnectorFormFields({
  form,
  setForm,
  sourceTypes,
  selectedType,
}: DataConnectorFormFieldsProps) {
  const translate = useTranslate();
  const isLocalFs = form.sourceType === "local_fs";

  // Type-specific fields to render dynamically (excluding watcher/SMB handled below)
  const typeFields = (selectedType?.fields ?? []).filter((f) => !WATCHER_FIELD_KEYS.has(f.key));

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="source-name">
          {translate("custom.pages.data_connectors.fields.name_label")}
        </Label>
        <Input
          id="source-name"
          value={form.name}
          onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          placeholder={translate("custom.pages.data_connectors.fields.name_placeholder")}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="source-type">
          {translate("custom.pages.data_connectors.fields.type_label")}
        </Label>
        <Select
          value={form.sourceType}
          onValueChange={(value) => setForm((prev) => ({ ...prev, sourceType: value }))}
        >
          <SelectTrigger id="source-type">
            <SelectValue
              placeholder={translate("custom.pages.data_connectors.fields.type_placeholder")}
            />
          </SelectTrigger>
          <SelectContent>
            {sourceTypes.map((sourceType) => (
              <SelectItem key={sourceType.connector_type} value={sourceType.connector_type}>
                {sourceType.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedType && (
          <p className="text-xs text-muted-foreground">{selectedType.description}</p>
        )}
      </div>

      {/* Dynamic type-specific fields (path for local_fs, endpoint/bucket/etc for S3) */}
      {typeFields.map((field) => (
        <DynamicField key={field.key} field={field} form={form} setForm={setForm} />
      ))}

      <div className="grid gap-3 sm:grid-cols-2">
        <SourceFlagSwitch
          id="source-watch"
          label={translate("custom.pages.data_connectors.fields.watch_label")}
          description={translate("custom.pages.data_connectors.fields.watch_description")}
          checked={form.watch}
          onCheckedChange={(checked) =>
            setForm((prev) => ({
              ...prev,
              watch: checked,
              forcePolling: checked ? prev.forcePolling : false,
              watcherType: checked ? prev.watcherType : "auto",
            }))
          }
        />
        <SourceFlagSwitch
          id="source-auto-process-new"
          label={translate("custom.pages.data_connectors.fields.auto_process_new_label")}
          description={translate(
            "custom.pages.data_connectors.fields.auto_process_new_description",
          )}
          checked={form.autoProcessNew}
          onCheckedChange={(checked) => setForm((prev) => ({ ...prev, autoProcessNew: checked }))}
        />
        <SourceFlagSwitch
          id="source-scan"
          label={translate("custom.pages.data_connectors.fields.initial_scan_label")}
          description={translate("custom.pages.data_connectors.fields.initial_scan_description")}
          checked={form.initialScan}
          onCheckedChange={(checked) => setForm((prev) => ({ ...prev, initialScan: checked }))}
        />
        <SourceFlagSwitch
          id="source-immutable"
          label={translate("custom.pages.data_connectors.fields.immutable_label")}
          description={translate("custom.pages.data_connectors.fields.immutable_description")}
          checked={form.immutable}
          onCheckedChange={(checked) => setForm((prev) => ({ ...prev, immutable: checked }))}
        />
      </div>

      {/* Watcher/SMB settings — only for local_fs */}
      {isLocalFs && form.watch && (
        <>
          <div className="space-y-2 rounded-md border p-3">
            <Label htmlFor="source-watcher-type">
              {translate("custom.pages.data_connectors.fields.watcher_type_label")}
            </Label>
            <Select
              value={form.watcherType}
              onValueChange={(value) =>
                setForm((prev) => ({
                  ...prev,
                  watcherType: value,
                  forcePolling: value === "smb_notify" ? false : prev.forcePolling,
                }))
              }
            >
              <SelectTrigger id="source-watcher-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">
                  {translate("custom.pages.data_connectors.fields.watcher_type_auto")}
                </SelectItem>
                <SelectItem value="smb_notify">
                  {translate("custom.pages.data_connectors.fields.watcher_type_smb_notify")}
                </SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {translate("custom.pages.data_connectors.fields.watcher_type_description")}
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {form.watcherType === "auto" && (
              <SourceFlagSwitch
                id="source-force-polling"
                label={translate("custom.pages.data_connectors.fields.force_polling_label")}
                description={translate(
                  "custom.pages.data_connectors.fields.force_polling_description",
                )}
                checked={form.forcePolling}
                onCheckedChange={(checked) =>
                  setForm((prev) => ({ ...prev, forcePolling: checked }))
                }
              />
            )}
            <div className="space-y-2 rounded-md border p-3">
              <Label htmlFor="source-poll-interval">
                {translate("custom.pages.data_connectors.fields.poll_interval_label")}
              </Label>
              <Input
                id="source-poll-interval"
                type="number"
                min={1}
                step={1}
                value={form.pollIntervalSeconds}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    pollIntervalSeconds: event.target.value,
                  }))
                }
                placeholder="30"
              />
              <p className="text-xs text-muted-foreground">
                {translate("custom.pages.data_connectors.fields.poll_interval_description")}
              </p>
            </div>
          </div>

          {form.watcherType === "smb_notify" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="source-smb-server">
                  {translate("custom.pages.data_connectors.fields.smb_server_label")}
                </Label>
                <Input
                  id="source-smb-server"
                  value={form.smbServer}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, smbServer: event.target.value }))
                  }
                  placeholder={translate(
                    "custom.pages.data_connectors.fields.smb_server_placeholder",
                  )}
                />
              </div>
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="source-smb-share">
                  {translate("custom.pages.data_connectors.fields.smb_share_label")}
                </Label>
                <Input
                  id="source-smb-share"
                  value={form.smbShare}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, smbShare: event.target.value }))
                  }
                  placeholder={translate(
                    "custom.pages.data_connectors.fields.smb_share_placeholder",
                  )}
                />
              </div>
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="source-smb-port">
                  {translate("custom.pages.data_connectors.fields.smb_port_label")}
                </Label>
                <Input
                  id="source-smb-port"
                  type="number"
                  min={1}
                  max={65535}
                  value={form.smbPort}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, smbPort: event.target.value }))
                  }
                  placeholder="445"
                />
              </div>
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="source-smb-domain">
                  {translate("custom.pages.data_connectors.fields.smb_domain_label")}
                </Label>
                <Input
                  id="source-smb-domain"
                  value={form.smbDomain}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, smbDomain: event.target.value }))
                  }
                  placeholder={translate(
                    "custom.pages.data_connectors.fields.smb_domain_placeholder",
                  )}
                />
              </div>
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="source-smb-username">
                  {translate("custom.pages.data_connectors.fields.smb_username_label")}
                </Label>
                <Input
                  id="source-smb-username"
                  value={form.smbUsername}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, smbUsername: event.target.value }))
                  }
                />
              </div>
              <div className="space-y-2 rounded-md border p-3">
                <Label htmlFor="source-smb-password">
                  {translate("custom.pages.data_connectors.fields.smb_password_label")}
                </Label>
                <Input
                  id="source-smb-password"
                  type="password"
                  value={form.smbPassword}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, smbPassword: event.target.value }))
                  }
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
