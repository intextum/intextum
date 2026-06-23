import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useNotify, useTranslate } from "@/lib/app-context";
import {
  dataConnectorsApi,
  groupsApi,
  permissionsApi,
  type AppUserEntry,
  type DataConnectorEntry,
  type DataConnectorTypeEntry,
  type DataConnectorTypeFieldEntry,
  type GroupEntry,
} from "@/dataProvider";
import {
  EMPTY_FORM,
  DEFAULT_SOURCE_TYPE,
  buildInitialFormState,
  buildSourcePayload,
  getErrorMessage,
  isDeleteConflictError,
  toFormState,
  toPermissionDraft,
  validateSourceForm,
  type SourceFormState,
  type SourcePermissionDraft,
} from "@/pages/data-connectors/shared";

interface UseDataConnectorsPageStateResult {
  sources: DataConnectorEntry[];
  sourceTypes: DataConnectorTypeEntry[];
  users: AppUserEntry[];
  groups: GroupEntry[];
  loading: boolean;
  usersLoading: boolean;
  submitting: boolean;
  error: string | null;
  createOpen: boolean;
  editOpen: boolean;
  permissionsOpen: boolean;
  deleteOpen: boolean;
  forceDeleteOpen: boolean;
  selectedSource: DataConnectorEntry | null;
  permissionsSource: DataConnectorEntry | null;
  form: SourceFormState;
  setForm: Dispatch<SetStateAction<SourceFormState>>;
  permissionsDraft: SourcePermissionDraft[];
  setPermissionsDraft: Dispatch<SetStateAction<SourcePermissionDraft[]>>;
  loadingPermissions: boolean;
  permissionsSubmitting: boolean;
  selectedType: DataConnectorTypeEntry | null;
  pathField: DataConnectorTypeFieldEntry | null;
  sourceTypeLabelByKey: Map<string, string>;
  hasSourceTypes: boolean;
  openCreateDialog: () => void;
  openEditDialog: (source: DataConnectorEntry) => void;
  openPermissionsDialog: (source: DataConnectorEntry) => Promise<void>;
  requestDeleteSource: (source: DataConnectorEntry) => void;
  handleCreateOpenChange: (open: boolean) => void;
  handleEditOpenChange: (open: boolean) => void;
  handlePermissionsOpenChange: (open: boolean) => void;
  handleDeleteOpenChange: (open: boolean) => void;
  handleForceDeleteOpenChange: (open: boolean) => void;
  cancelDeleteDialog: () => void;
  cancelForceDeleteDialog: () => void;
  closePermissionsDialog: () => void;
  closeCreateDialog: () => void;
  closeEditDialog: () => void;
  handleCreate: () => Promise<void>;
  handleEdit: () => Promise<void>;
  handleSavePermissions: () => Promise<void>;
  handleDelete: () => Promise<void>;
  handleForceDelete: () => Promise<void>;
}

export function useDataConnectorsPageState(): UseDataConnectorsPageStateResult {
  const translate = useTranslate();
  const notify = useNotify();

  const [sources, setSources] = useState<DataConnectorEntry[]>([]);
  const [sourceTypes, setSourceTypes] = useState<DataConnectorTypeEntry[]>([]);
  const [users, setUsers] = useState<AppUserEntry[]>([]);
  const [groups, setGroups] = useState<GroupEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [usersLoading, setUsersLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [permissionsOpen, setPermissionsOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [forceDeleteOpen, setForceDeleteOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState<DataConnectorEntry | null>(null);
  const [permissionsSource, setPermissionsSource] = useState<DataConnectorEntry | null>(null);
  const [form, setForm] = useState<SourceFormState>(EMPTY_FORM);
  const [permissionsDraft, setPermissionsDraft] = useState<SourcePermissionDraft[]>([]);
  const [permissionsBaseline, setPermissionsBaseline] = useState<SourcePermissionDraft[]>([]);
  const [loadingPermissions, setLoadingPermissions] = useState(false);
  const [permissionsSubmitting, setPermissionsSubmitting] = useState(false);

  const fetchSources = useCallback(
    async (showLoading: boolean = true) => {
      if (showLoading) {
        setLoading(true);
      }
      try {
        const [sourceData, typeData] = await Promise.all([
          dataConnectorsApi.list(),
          dataConnectorsApi.listTypes(),
        ]);
        setSources(sourceData);
        setSourceTypes(typeData);
        setForm((prev) => {
          if (prev.sourceType.trim()) {
            return prev;
          }
          const firstType = typeData[0]?.connector_type ?? DEFAULT_SOURCE_TYPE;
          return { ...prev, sourceType: firstType };
        });
        setError(null);
      } catch (err: unknown) {
        setError(getErrorMessage(err, translate("custom.pages.data_connectors.failed_to_fetch")));
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [translate],
  );

  const fetchUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      const [userData, groupData] = await Promise.all([
        permissionsApi.listUsers(),
        groupsApi.list(),
      ]);
      setUsers(userData);
      setGroups(groupData);
    } catch (err: unknown) {
      notify(
        getErrorMessage(err, translate("custom.pages.data_connectors.users_failed_to_fetch")),
        {
          type: "error",
        },
      );
    } finally {
      setUsersLoading(false);
    }
  }, [notify, translate]);

  useEffect(() => {
    void fetchSources();
    void fetchUsers();
  }, [fetchSources, fetchUsers]);

  // While any connector is mid-scan, refresh quietly so progress counters update.
  const hasActiveScan = sources.some((source) => source.scan_state === "scanning");
  useEffect(() => {
    if (!hasActiveScan) {
      return;
    }
    const interval = setInterval(() => {
      void fetchSources(false);
    }, 5000);
    return () => {
      clearInterval(interval);
    };
  }, [hasActiveScan, fetchSources]);

  useEffect(() => {
    if (sourceTypes.length === 0) {
      return;
    }
    setForm((prev) => {
      const hasCurrent = sourceTypes.some((type) => type.connector_type === prev.sourceType);
      if (hasCurrent) {
        return prev;
      }
      return { ...prev, sourceType: sourceTypes[0].connector_type };
    });
  }, [sourceTypes]);

  const syncPermissions = useCallback(
    async (
      sourceUuid: string,
      previousPermissions: SourcePermissionDraft[],
      nextPermissions: SourcePermissionDraft[],
    ) => {
      const previousByTrustee = new Map(
        previousPermissions.map((permission) => [permission.trustee, permission.access]),
      );
      const nextByTrustee = new Map(
        nextPermissions.map((permission) => [permission.trustee, permission.access]),
      );

      const operations: Promise<unknown>[] = [];

      nextByTrustee.forEach((access, trustee) => {
        if (previousByTrustee.get(trustee) !== access) {
          operations.push(permissionsApi.set(sourceUuid, trustee, access));
        }
      });

      previousByTrustee.forEach((_access, trustee) => {
        if (!nextByTrustee.has(trustee)) {
          operations.push(permissionsApi.remove(sourceUuid, trustee));
        }
      });

      if (operations.length > 0) {
        await Promise.all(operations);
      }
    },
    [],
  );

  const selectedType = useMemo(
    () =>
      sourceTypes.find((type) => type.connector_type === form.sourceType) ?? sourceTypes[0] ?? null,
    [sourceTypes, form.sourceType],
  );
  const pathField = useMemo(
    () => selectedType?.fields.find((field) => field.key === "path") ?? null,
    [selectedType],
  );
  const sourceTypeLabelByKey = useMemo(
    () => new Map(sourceTypes.map((type) => [type.connector_type, type.label])),
    [sourceTypes],
  );
  const hasSourceTypes = sourceTypes.length > 0;

  const openCreateDialog = useCallback(() => {
    setForm(buildInitialFormState(sourceTypes));
    setCreateOpen(true);
  }, [sourceTypes]);

  const openEditDialog = useCallback((source: DataConnectorEntry) => {
    setSelectedSource(source);
    setForm(toFormState(source));
    setEditOpen(true);
  }, []);

  const openPermissionsDialog = useCallback(
    async (source: DataConnectorEntry) => {
      setPermissionsSource(source);
      setPermissionsDraft([]);
      setPermissionsBaseline([]);
      setLoadingPermissions(true);
      setPermissionsOpen(true);
      try {
        const currentPermissions = await permissionsApi.list(source.uuid);
        const permissionDrafts = currentPermissions.map(toPermissionDraft);
        setPermissionsDraft(permissionDrafts);
        setPermissionsBaseline(permissionDrafts);
      } catch (err: unknown) {
        notify(
          getErrorMessage(err, translate("custom.pages.data_connectors.permissions_load_failed")),
          { type: "error" },
        );
      } finally {
        setLoadingPermissions(false);
      }
    },
    [notify, translate],
  );

  const requestDeleteSource = useCallback((source: DataConnectorEntry) => {
    setSelectedSource(source);
    setForceDeleteOpen(false);
    setDeleteOpen(true);
  }, []);

  const handleCreate = useCallback(async () => {
    const validationError = validateSourceForm(form, selectedType);
    if (validationError) {
      notify(translate(`custom.pages.data_connectors.validation.${validationError}`), {
        type: "warning",
      });
      return;
    }

    setSubmitting(true);
    try {
      const payload = buildSourcePayload(form);
      await dataConnectorsApi.create(payload);

      notify(translate("custom.pages.data_connectors.create_success"), { type: "success" });
      notify(translate("custom.pages.data_connectors.create_permissions_hint"), { type: "info" });
      setCreateOpen(false);
      setForm(buildInitialFormState(sourceTypes));
      await fetchSources(false);
    } catch (err: unknown) {
      notify(getErrorMessage(err, translate("custom.pages.data_connectors.create_failed")), {
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }, [fetchSources, form, notify, selectedType, sourceTypes, translate]);

  const handleEdit = useCallback(async () => {
    if (!selectedSource) {
      return;
    }
    const validationError = validateSourceForm(form, selectedType);
    if (validationError) {
      notify(translate(`custom.pages.data_connectors.validation.${validationError}`), {
        type: "warning",
      });
      return;
    }

    setSubmitting(true);
    try {
      const payload: Parameters<typeof dataConnectorsApi.update>[1] = buildSourcePayload(form);
      await dataConnectorsApi.update(selectedSource.uuid, payload);

      notify(translate("custom.pages.data_connectors.update_success"), { type: "success" });
      setEditOpen(false);
      setSelectedSource(null);
      await fetchSources(false);
    } catch (err: unknown) {
      notify(getErrorMessage(err, translate("custom.pages.data_connectors.update_failed")), {
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }, [fetchSources, form, notify, selectedType, selectedSource, translate]);

  const handleSavePermissions = useCallback(async () => {
    if (!permissionsSource) {
      return;
    }

    setPermissionsSubmitting(true);
    try {
      await syncPermissions(permissionsSource.uuid, permissionsBaseline, permissionsDraft);
      notify(translate("custom.pages.data_connectors.permissions_save_success"), {
        type: "success",
      });
      setPermissionsOpen(false);
      setPermissionsSource(null);
      setPermissionsDraft([]);
      setPermissionsBaseline([]);
    } catch (err: unknown) {
      notify(
        getErrorMessage(err, translate("custom.pages.data_connectors.permissions_save_failed")),
        {
          type: "error",
        },
      );
    } finally {
      setPermissionsSubmitting(false);
    }
  }, [
    notify,
    permissionsBaseline,
    permissionsDraft,
    permissionsSource,
    syncPermissions,
    translate,
  ]);

  const handleDelete = useCallback(async () => {
    if (!selectedSource) {
      return;
    }

    setSubmitting(true);
    try {
      await dataConnectorsApi.remove(selectedSource.uuid, false);
      notify(translate("custom.pages.data_connectors.delete_success"), { type: "info" });
      setDeleteOpen(false);
      setForceDeleteOpen(false);
      setSelectedSource(null);
      await fetchSources(false);
    } catch (err: unknown) {
      if (isDeleteConflictError(err)) {
        notify(translate("custom.pages.data_connectors.delete_requires_force"), {
          type: "warning",
        });
        setDeleteOpen(false);
        setForceDeleteOpen(true);
        return;
      }
      notify(getErrorMessage(err, translate("custom.pages.data_connectors.delete_failed")), {
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }, [fetchSources, notify, selectedSource, translate]);

  const handleForceDelete = useCallback(async () => {
    if (!selectedSource) {
      return;
    }

    setSubmitting(true);
    try {
      await dataConnectorsApi.remove(selectedSource.uuid, true);
      notify(translate("custom.pages.data_connectors.delete_success"), { type: "info" });
      setDeleteOpen(false);
      setForceDeleteOpen(false);
      setSelectedSource(null);
      await fetchSources(false);
    } catch (err: unknown) {
      notify(getErrorMessage(err, translate("custom.pages.data_connectors.delete_failed")), {
        type: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }, [fetchSources, notify, selectedSource, translate]);

  const handleCreateOpenChange = useCallback(
    (open: boolean) => {
      setCreateOpen(open);
      if (!open) {
        setForm(buildInitialFormState(sourceTypes));
      }
    },
    [sourceTypes],
  );

  const handleEditOpenChange = useCallback(
    (open: boolean) => {
      setEditOpen(open);
      if (!open) {
        setSelectedSource(null);
        setForm(buildInitialFormState(sourceTypes));
      }
    },
    [sourceTypes],
  );

  const handlePermissionsOpenChange = useCallback((open: boolean) => {
    setPermissionsOpen(open);
    if (!open) {
      setPermissionsSource(null);
      setPermissionsDraft([]);
      setPermissionsBaseline([]);
      setLoadingPermissions(false);
    }
  }, []);

  const handleDeleteOpenChange = useCallback((open: boolean) => {
    setDeleteOpen(open);
  }, []);

  const handleForceDeleteOpenChange = useCallback((open: boolean) => {
    setForceDeleteOpen(open);
    if (!open) {
      setSelectedSource(null);
    }
  }, []);

  const cancelDeleteDialog = useCallback(() => {
    setDeleteOpen(false);
    setSelectedSource(null);
  }, []);

  const cancelForceDeleteDialog = useCallback(() => {
    setForceDeleteOpen(false);
  }, []);

  const closePermissionsDialog = useCallback(() => {
    setPermissionsOpen(false);
  }, []);

  const closeCreateDialog = useCallback(() => {
    setCreateOpen(false);
  }, []);

  const closeEditDialog = useCallback(() => {
    setEditOpen(false);
  }, []);

  return {
    sources,
    sourceTypes,
    users,
    groups,
    loading,
    usersLoading,
    submitting,
    error,
    createOpen,
    editOpen,
    permissionsOpen,
    deleteOpen,
    forceDeleteOpen,
    selectedSource,
    permissionsSource,
    form,
    setForm,
    permissionsDraft,
    setPermissionsDraft,
    loadingPermissions,
    permissionsSubmitting,
    selectedType,
    pathField,
    sourceTypeLabelByKey,
    hasSourceTypes,
    openCreateDialog,
    openEditDialog,
    openPermissionsDialog,
    requestDeleteSource,
    handleCreateOpenChange,
    handleEditOpenChange,
    handlePermissionsOpenChange,
    handleDeleteOpenChange,
    handleForceDeleteOpenChange,
    cancelDeleteDialog,
    cancelForceDeleteDialog,
    closePermissionsDialog,
    closeCreateDialog,
    closeEditDialog,
    handleCreate,
    handleEdit,
    handleSavePermissions,
    handleDelete,
    handleForceDelete,
  };
}
