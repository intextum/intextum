import { useTranslate } from "@/lib/app-context";
import { Database, Pencil, Plus, Shield, Trash2 } from "lucide-react";
import { EmptyState } from "@/components/page/EmptyState";
import { LoadingState } from "@/components/page/LoadingState";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DataConnectorFormFields } from "@/pages/data-connectors/DataConnectorFormFields";
import { DataConnectorPermissionsEditor } from "@/pages/data-connectors/DataConnectorPermissionsEditor";
import { useDataConnectorsPageState } from "@/pages/data-connectors/useDataConnectorsPageState";

export const DataConnectorsPage = ({ embedded = false }: { embedded?: boolean }) => {
  const translate = useTranslate();
  useDocumentTitle(embedded ? undefined : translate("custom.pages.data_connectors.title"));

  const {
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
  } = useDataConnectorsPageState();

  const formFields = (
    <DataConnectorFormFields
      form={form}
      setForm={setForm}
      sourceTypes={sourceTypes}
      selectedType={selectedType}
      pathField={pathField}
    />
  );

  const content = (
    <div className="space-y-6">
      {error && (
        <Alert>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <section className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <h3 className="text-lg font-medium">
            {translate("custom.pages.data_connectors.registered_title")}
          </h3>
          <Button size="sm" onClick={openCreateDialog} disabled={submitting || !hasSourceTypes}>
            <Plus className="h-4 w-4 mr-2" />
            {translate("custom.pages.data_connectors.add_source")}
          </Button>
        </div>
        <Separator />
        <div>
          {loading ? (
            <LoadingState rows={3} />
          ) : sources.length === 0 ? (
            <EmptyState
              icon={Database}
              title={translate("custom.pages.data_connectors.no_sources")}
              actions={
                <Button
                  size="sm"
                  onClick={openCreateDialog}
                  disabled={submitting || !hasSourceTypes}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  {translate("custom.pages.data_connectors.add_source")}
                </Button>
              }
            />
          ) : (
            <div className="overflow-hidden rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{translate("custom.pages.data_connectors.table.name")}</TableHead>
                    <TableHead>{translate("custom.pages.data_connectors.table.type")}</TableHead>
                    <TableHead className="text-right">
                      {translate("custom.pages.data_connectors.table.actions")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sources.map((source) => (
                    <TableRow key={source.uuid}>
                      <TableCell className="font-medium">{source.name}</TableCell>
                      <TableCell>
                        {sourceTypeLabelByKey.get(source.connector_type) ?? source.connector_type}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => {
                              openEditDialog(source);
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => {
                              void openPermissionsDialog(source);
                            }}
                          >
                            <Shield className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive hover:text-destructive"
                            onClick={() => {
                              requestDeleteSource(source);
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </section>
    </div>
  );

  const pageContent = embedded ? (
    content
  ) : (
    <PageShell>
      <PageHeader
        icon={Database}
        title={translate("custom.pages.data_connectors.title")}
        description={translate("custom.pages.data_connectors.description")}
      />
      {content}
    </PageShell>
  );

  return (
    <>
      {pageContent}

      <Dialog open={createOpen} onOpenChange={handleCreateOpenChange}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.data_connectors.dialogs.create.title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.data_connectors.dialogs.create.description")}
            </DialogDescription>
          </DialogHeader>
          {formFields}
          <DialogFooter>
            <Button variant="outline" onClick={closeCreateDialog}>
              {translate("custom.pages.data_connectors.dialogs.cancel")}
            </Button>
            <Button onClick={handleCreate} disabled={submitting || !hasSourceTypes}>
              {submitting
                ? translate("custom.pages.data_connectors.dialogs.create.submitting")
                : translate("custom.pages.data_connectors.dialogs.create.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={handleEditOpenChange}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.data_connectors.dialogs.edit.title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.data_connectors.dialogs.edit.description")}
            </DialogDescription>
          </DialogHeader>
          {formFields}
          <DialogFooter>
            <Button variant="outline" onClick={closeEditDialog}>
              {translate("custom.pages.data_connectors.dialogs.cancel")}
            </Button>
            <Button onClick={handleEdit} disabled={submitting || !hasSourceTypes}>
              {submitting
                ? translate("custom.pages.data_connectors.dialogs.edit.submitting")
                : translate("custom.pages.data_connectors.dialogs.edit.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={permissionsOpen} onOpenChange={handlePermissionsOpenChange}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.data_connectors.dialogs.permissions.title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.data_connectors.dialogs.permissions.description", {
                name: permissionsSource?.name ?? "",
              })}
            </DialogDescription>
          </DialogHeader>
          <DataConnectorPermissionsEditor
            permissions={permissionsDraft}
            users={users}
            groups={groups}
            showHeader={false}
            loading={usersLoading || loadingPermissions}
            disabled={permissionsSubmitting}
            onChange={setPermissionsDraft}
          />
          <DialogFooter>
            <Button variant="outline" onClick={closePermissionsDialog}>
              {translate("custom.pages.data_connectors.dialogs.cancel")}
            </Button>
            <Button
              onClick={handleSavePermissions}
              disabled={permissionsSubmitting || usersLoading || loadingPermissions}
            >
              {permissionsSubmitting
                ? translate("custom.pages.data_connectors.dialogs.permissions.submitting")
                : translate("custom.pages.data_connectors.dialogs.permissions.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={handleDeleteOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.data_connectors.dialogs.delete.title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.data_connectors.dialogs.delete.description", {
                name: selectedSource?.name ?? "",
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={cancelDeleteDialog}>
              {translate("custom.pages.data_connectors.dialogs.cancel")}
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={submitting}>
              {submitting
                ? translate("custom.pages.data_connectors.dialogs.delete.submitting")
                : translate("custom.pages.data_connectors.dialogs.delete.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={forceDeleteOpen} onOpenChange={handleForceDeleteOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {translate("custom.pages.data_connectors.dialogs.force_delete.title")}
            </DialogTitle>
            <DialogDescription>
              {translate("custom.pages.data_connectors.dialogs.force_delete.description", {
                name: selectedSource?.name ?? "",
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={cancelForceDeleteDialog}>
              {translate("custom.pages.data_connectors.dialogs.cancel")}
            </Button>
            <Button variant="destructive" onClick={handleForceDelete} disabled={submitting}>
              {submitting
                ? translate("custom.pages.data_connectors.dialogs.force_delete.submitting")
                : translate("custom.pages.data_connectors.dialogs.force_delete.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
