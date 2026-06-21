/**
 * Worker management page.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslate } from "@/lib/app-context";
import { AlertTriangle, Check, Copy, Cpu, Plus } from "lucide-react";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import { WorkersManagementContent } from "@/components/workers/WorkersManagementContent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  workersApi,
  type Worker,
  type WorkerTaskQueueCleanupResponse,
  type WorkerTaskQueueItem,
} from "@/dataProvider";
import { queryKeys } from "@/lib/query-client";

const ACTIVE_TASK_PARAMS = { activeOnly: true, limit: 50 } as const;

export const WorkersPage = ({ embedded = false }: { embedded?: boolean }) => {
  const translate = useTranslate();
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<WorkerTaskQueueCleanupResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  // Dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [selectedWorker, setSelectedWorker] = useState<Worker | null>(null);
  const [displayedToken, setDisplayedToken] = useState("");
  const [copied, setCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const workersQuery = useQuery({
    queryKey: queryKeys.workers.list,
    queryFn: workersApi.list,
  });
  const tasksQuery = useQuery({
    queryKey: queryKeys.workers.tasks(ACTIVE_TASK_PARAMS),
    queryFn: () => workersApi.listTasks(ACTIVE_TASK_PARAMS),
  });
  const { refetch: refetchWorkers } = workersQuery;
  const { refetch: refetchTasks } = tasksQuery;
  const workers: Worker[] = workersQuery.data?.workers ?? [];
  const tasks: WorkerTaskQueueItem[] = tasksQuery.data?.tasks ?? [];
  const total = workersQuery.data?.total ?? 0;
  const taskTotal = tasksQuery.data?.total ?? 0;
  const loading = workersQuery.isLoading;
  const tasksLoading = tasksQuery.isLoading || tasksQuery.isFetching;
  const workerError =
    error ?? (workersQuery.error ? translate("custom.pages.workers.failed_to_fetch") : null);
  const queueError =
    taskError ??
    (tasksQuery.error ? translate("custom.pages.workers.queue.failed_to_fetch") : null);

  const handleCleanupStaleTasks = async () => {
    setCleanupLoading(true);
    try {
      const result = await workersApi.cleanupStaleTasks();
      setCleanupResult(result);
      setTaskError(null);
      await refetchTasks();
      await refetchWorkers();
    } catch {
      setTaskError(translate("custom.pages.workers.queue.cleanup_failed"));
    } finally {
      setCleanupLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!formName.trim()) return;
    setSubmitting(true);
    try {
      const result = await workersApi.create({
        name: formName.trim(),
        description: formDescription.trim(),
      });
      setCreateOpen(false);
      setFormName("");
      setFormDescription("");
      setDisplayedToken(result.token);
      setTokenOpen(true);
      setError(null);
      void refetchWorkers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : translate("custom.failed_action");
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = async () => {
    if (!selectedWorker || !formName.trim()) return;
    setSubmitting(true);
    try {
      await workersApi.update(selectedWorker.id, {
        name: formName.trim(),
        description: formDescription.trim(),
      });
      setEditOpen(false);
      setSelectedWorker(null);
      setError(null);
      void refetchWorkers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : translate("custom.failed_action");
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedWorker) return;
    setSubmitting(true);
    try {
      await workersApi.delete(selectedWorker.id);
      setDeleteOpen(false);
      setSelectedWorker(null);
      setError(null);
      void refetchWorkers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : translate("custom.failed_action");
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRotateToken = async (worker: Worker) => {
    setSubmitting(true);
    try {
      const result = await workersApi.rotateToken(worker.id);
      setDisplayedToken(result.token);
      setTokenOpen(true);
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : translate("custom.failed_action");
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const openEdit = (worker: Worker) => {
    setSelectedWorker(worker);
    setFormName(worker.name);
    setFormDescription(worker.description);
    setEditOpen(true);
  };

  const openDelete = (worker: Worker) => {
    setSelectedWorker(worker);
    setDeleteOpen(true);
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(displayedToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const activeCount = workers.filter((w) => w.status === "active").length;

  const openCreate = () => {
    setFormName("");
    setFormDescription("");
    setCreateOpen(true);
  };

  const content = (
    <WorkersManagementContent
      cleanupLoading={cleanupLoading}
      cleanupResult={cleanupResult}
      embedded={embedded}
      loading={loading}
      queueError={queueError}
      submitting={submitting}
      taskTotal={taskTotal}
      tasks={tasks}
      tasksLoading={tasksLoading}
      translate={translate}
      workerError={workerError}
      workers={workers}
      onCleanupStaleTasks={handleCleanupStaleTasks}
      onCreateWorker={openCreate}
      onDeleteWorker={openDelete}
      onEditWorker={openEdit}
      onRefreshTasks={() => {
        void refetchTasks();
      }}
      onRotateToken={handleRotateToken}
    />
  );

  return (
    <>
      {embedded ? (
        content
      ) : (
        <PageShell>
          <PageHeader
            icon={Cpu}
            title={translate("custom.pages.workers.title")}
            description={`${translate("custom.pages.workers.total", {
              count: total,
            })} · ${translate("custom.pages.workers.active", { count: activeCount })}`}
            actions={
              <Button size="sm" onClick={openCreate}>
                <Plus className="h-4 w-4 mr-2" />
                {translate("custom.pages.workers.add_worker")}
              </Button>
            }
          />
          {content}
        </PageShell>
      )}
      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.workers.dialogs.create.title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.workers.dialogs.create.desc")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="create-name">
                {translate("custom.pages.workers.dialogs.create.name_label")}
              </Label>
              <Input
                id="create-name"
                placeholder={translate("custom.pages.workers.dialogs.create.name_placeholder")}
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-desc">
                {translate("custom.pages.workers.dialogs.create.desc_label")}
              </Label>
              <Textarea
                id="create-desc"
                placeholder={translate("custom.pages.workers.dialogs.create.desc_placeholder")}
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {translate("custom.pages.workers.dialogs.cancel")}
            </Button>
            <Button onClick={handleCreate} disabled={!formName.trim() || submitting}>
              {submitting
                ? translate("custom.pages.workers.dialogs.create.submitting")
                : translate("custom.pages.workers.dialogs.create.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.workers.dialogs.edit.title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.workers.dialogs.edit.desc")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="edit-name">
                {translate("custom.pages.workers.dialogs.edit.name_label")}
              </Label>
              <Input
                id="edit-name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-desc">
                {translate("custom.pages.workers.dialogs.edit.desc_label")}
              </Label>
              <Textarea
                id="edit-desc"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              {translate("custom.pages.workers.dialogs.cancel")}
            </Button>
            <Button onClick={handleEdit} disabled={!formName.trim() || submitting}>
              {submitting
                ? translate("custom.pages.workers.dialogs.edit.submitting")
                : translate("custom.pages.workers.dialogs.edit.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.workers.dialogs.delete.title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.workers.dialogs.delete.desc", {
                name: selectedWorker?.name,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              {translate("custom.pages.workers.dialogs.cancel")}
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={submitting}>
              {submitting
                ? translate("custom.pages.workers.dialogs.delete.submitting")
                : translate("custom.pages.workers.dialogs.delete.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Token Display Dialog */}
      <Dialog open={tokenOpen} onOpenChange={setTokenOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.workers.dialogs.token.title")}</DialogTitle>
            <DialogDescription>
              {translate("custom.pages.workers.dialogs.token.desc")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {translate("custom.pages.workers.dialogs.token.warning")}
              </AlertDescription>
            </Alert>
            <div className="flex items-center gap-2">
              <Input readOnly value={displayedToken} className="font-mono text-sm" />
              <Button variant="outline" size="icon" onClick={handleCopy}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setTokenOpen(false)}>
              {translate("custom.pages.workers.dialogs.token.button")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
