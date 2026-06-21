import {
  dataConnectorsApi,
  type DataConnectorEntry,
  type DataConnectorTypeEntry,
  type PermissionEntry,
} from "@/dataProvider";

export interface SourceFormState {
  name: string;
  sourceType: string;
  path: string;
  watch: boolean;
  autoProcessNew: boolean;
  initialScan: boolean;
  immutable: boolean;
  forcePolling: boolean;
  pollIntervalSeconds: string;
  watcherType: string;
  smbServer: string;
  smbShare: string;
  smbPort: string;
  smbUsername: string;
  smbPassword: string;
  smbDomain: string;
  // S3 fields
  endpointUrl: string;
  bucket: string;
  s3Prefix: string;
  accessKey: string;
  secretKey: string;
  region: string;
}

export type PermissionAccess = "allow" | "deny";

export interface SourcePermissionDraft {
  trustee: string;
  access: PermissionAccess;
}

export type SourceFormValidationError =
  | "name_required"
  | "path_required"
  | "field_required"
  | "poll_interval_required"
  | "smb_server_required"
  | "smb_share_required";

export type DataConnectorPayload = Parameters<typeof dataConnectorsApi.create>[0];

export const EMPTY_FORM: SourceFormState = {
  name: "",
  sourceType: "local_fs",
  path: "",
  watch: false,
  autoProcessNew: true,
  initialScan: true,
  immutable: false,
  forcePolling: false,
  pollIntervalSeconds: "30",
  watcherType: "auto",
  smbServer: "",
  smbShare: "",
  smbPort: "445",
  smbUsername: "",
  smbPassword: "",
  smbDomain: "",
  endpointUrl: "",
  bucket: "",
  s3Prefix: "",
  accessKey: "",
  secretKey: "",
  region: "",
};

export const DEFAULT_SOURCE_TYPE = "local_fs";

export function buildInitialFormState(sourceTypes: DataConnectorTypeEntry[]): SourceFormState {
  return {
    ...EMPTY_FORM,
    sourceType: sourceTypes[0]?.connector_type ?? DEFAULT_SOURCE_TYPE,
  };
}

export function toFormState(connector: DataConnectorEntry): SourceFormState {
  return {
    name: connector.name,
    sourceType: connector.connector_type,
    path: connector.path,
    watch: connector.watch,
    autoProcessNew: connector.auto_process_new,
    initialScan: connector.initial_scan,
    immutable: connector.immutable ?? false,
    forcePolling: connector.force_polling,
    pollIntervalSeconds: String(connector.poll_interval_seconds),
    watcherType: connector.watcher_type ?? "auto",
    smbServer: connector.smb_server ?? "",
    smbShare: connector.smb_share ?? "",
    smbPort: String(connector.smb_port ?? 445),
    smbUsername: connector.smb_username ?? "",
    smbPassword: "",
    smbDomain: connector.smb_domain ?? "",
    endpointUrl: connector.endpoint_url ?? "",
    bucket: connector.bucket ?? "",
    s3Prefix: connector.s3_prefix ?? "",
    accessKey: connector.access_key ?? "",
    secretKey: "",
    region: connector.region ?? "",
  };
}

export function normalizePermissionAccess(access: string): PermissionAccess {
  return access === "deny" ? "deny" : "allow";
}

export function toPermissionDraft(permission: PermissionEntry): SourcePermissionDraft {
  return {
    trustee: permission.trustee,
    access: normalizePermissionAccess(permission.access),
  };
}

export function getErrorMessage(error: unknown, fallback: string): string {
  const detail = getErrorDetail(error);
  if (detail) {
    return detail;
  }

  return error instanceof Error ? error.message : fallback;
}

function getErrorDetail(error: unknown): string | null {
  if (error && typeof error === "object" && "body" in error) {
    const body = (error as { body?: unknown }).body;
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as { detail?: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
  }

  return null;
}

export function isDeleteConflictError(error: unknown): boolean {
  if (!error || typeof error !== "object") {
    return false;
  }
  const status = (error as { status?: unknown }).status;
  if (status !== 409) {
    return false;
  }

  const detail = getErrorDetail(error);
  return typeof detail === "string" && detail.includes("cannot delete connector");
}

function parsePollIntervalSeconds(value: string): number | null {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return null;
  }
  return parsed;
}

/** Map from field definition key to form state key. */
const FIELD_KEY_TO_FORM_KEY: Record<string, keyof SourceFormState> = {
  path: "path",
  endpoint_url: "endpointUrl",
  bucket: "bucket",
  s3_prefix: "s3Prefix",
  access_key: "accessKey",
  secret_key: "secretKey",
  region: "region",
};

export function validateSourceForm(
  form: SourceFormState,
  selectedType: DataConnectorTypeEntry | null,
): SourceFormValidationError | null {
  if (!form.name.trim()) {
    return "name_required";
  }

  // Validate required fields from the type definition
  if (selectedType) {
    for (const field of selectedType.fields) {
      if (!field.required) continue;
      const formKey = FIELD_KEY_TO_FORM_KEY[field.key];
      if (formKey) {
        const value = form[formKey];
        if (typeof value === "string" && !value.trim()) {
          return "field_required" as SourceFormValidationError;
        }
      }
    }
  }

  const parsedPollIntervalSeconds = parsePollIntervalSeconds(form.pollIntervalSeconds);
  if (form.watch && parsedPollIntervalSeconds === null) {
    return "poll_interval_required";
  }

  if (form.watch && form.watcherType === "smb_notify") {
    if (!form.smbServer.trim()) {
      return "smb_server_required";
    }
    if (!form.smbShare.trim()) {
      return "smb_share_required";
    }
  }

  return null;
}

export function buildSourcePayload(form: SourceFormState): DataConnectorPayload {
  const pollIntervalSeconds = parsePollIntervalSeconds(form.pollIntervalSeconds) ?? 30;
  const connectorType = form.sourceType.trim() || DEFAULT_SOURCE_TYPE;
  const payload: DataConnectorPayload = {
    name: form.name.trim(),
    connector_type: connectorType,
    watch: form.watch,
    auto_process_new: form.autoProcessNew,
    initial_scan: form.initialScan,
    immutable: form.immutable,
    force_polling: form.watcherType === "smb_notify" ? false : form.forcePolling,
    poll_interval_seconds: pollIntervalSeconds,
    watcher_type: form.watch ? form.watcherType : "auto",
  };

  if (connectorType === "local_fs") {
    payload.path = form.path.trim();

    if (form.watch && form.watcherType === "smb_notify") {
      payload.smb_server = form.smbServer.trim();
      payload.smb_share = form.smbShare.trim();
      payload.smb_port = Number.parseInt(form.smbPort, 10) || 445;
      if (form.smbUsername.trim()) payload.smb_username = form.smbUsername.trim();
      if (form.smbPassword) payload.smb_password = form.smbPassword;
      if (form.smbDomain.trim()) payload.smb_domain = form.smbDomain.trim();
    }
  } else if (connectorType === "s3") {
    payload.endpoint_url = form.endpointUrl.trim();
    payload.bucket = form.bucket.trim();
    if (form.s3Prefix.trim()) payload.s3_prefix = form.s3Prefix.trim();
    payload.access_key = form.accessKey.trim();
    if (form.secretKey) payload.secret_key = form.secretKey;
    if (form.region.trim()) payload.region = form.region.trim();
  }

  return payload;
}

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

export function formatTrusteeLabel(
  trustee: string,
  trusteeLabelByValue: Map<string, string>,
  translate: TranslateFn,
): string {
  if (trustee === "everyone") {
    return translate("custom.permissions.everyone");
  }
  const knownUser = trusteeLabelByValue.get(trustee);
  if (knownUser) {
    return knownUser;
  }
  if (trustee.startsWith("sub:")) {
    return translate("custom.permissions.user", { name: trustee.slice(4) });
  }
  if (trustee.startsWith("group:")) {
    return translate("custom.permissions.group", { name: trustee.slice(6) });
  }
  return trustee;
}
