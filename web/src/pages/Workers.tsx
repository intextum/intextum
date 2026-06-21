/**
 * Worker management page.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslate } from "@/lib/app-context";
import { AlertTriangle, Check, Copy, Cpu, Loader2, Plus } from "lucide-react";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import { WorkersManagementContent } from "@/components/workers/WorkersManagementContent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  type WorkerInstallInfo,
  type WorkerTaskQueueCleanupResponse,
  type WorkerTaskQueueItem,
} from "@/dataProvider";
import { queryKeys } from "@/lib/query-client";

/**
 * API base the installed worker should target. The worker joins this with
 * `/api/worker/...` itself, so it must be the bare origin WITHOUT a path. Prefer
 * the admin-configured public URL; fall back to the current request origin.
 */
function workerApiBase(info: WorkerInstallInfo): string {
  return info.public_url ?? window.location.origin;
}

/** Assemble the copy-paste install/run (pip) or `docker run` command. */
function buildWorkerCommands(info: WorkerInstallInfo, platformId: string, token: string): string {
  const platform = info.platforms.find((p) => p.id === platformId) ?? info.platforms[0];
  if (!platform) return "";
  const apiBase = workerApiBase(info);
  const caps = info.default_capabilities;

  if (platform.kind === "docker") {
    const image = `${platform.image}:${info.version}`;
    return [
      "docker run -d --restart unless-stopped \\",
      ...(platform.gpu ? ["  --gpus all \\"] : []),
      `  -e API_URL="${apiBase}" \\`,
      `  -e WORKER_TOKEN="${token}" \\`,
      `  -e CAPABILITIES="${caps}" \\`,
      `  ${image}`,
    ].join("\n");
  }

  const spec = `${info.package}[${platform.extra}]==${info.version}`;
  const extraIndex = platform.extra_index_url
    ? ` --extra-index-url ${platform.extra_index_url}`
    : "";
  const install = `pip install '${spec}'${extraIndex}`;
  const run =
    `API_URL="${apiBase}" WORKER_TOKEN="${token}" ` + `intextum-worker --capabilities ${caps}`;
  return `${install}\n${run}`;
}

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

  // Add-Worker install flow: the worker the token belongs to (for live
  // "connected" feedback) and the selected install platform.
  const [tokenWorker, setTokenWorker] = useState<Worker | null>(null);
  const [selectedPlatform, setSelectedPlatform] = useState("macos-mps");
  const [commandCopied, setCommandCopied] = useState(false);

  const workersQuery = useQuery({
    queryKey: queryKeys.workers.list,
    queryFn: workersApi.list,
    // While the token dialog is open, poll so a freshly installed worker shows
    // up as connected without a manual refresh.
    refetchInterval: tokenOpen ? 3000 : false,
  });
  const installInfoQuery = useQuery({
    queryKey: ["workers", "install-info"],
    queryFn: workersApi.installInfo,
    staleTime: Infinity,
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
      setTokenWorker(result.worker);
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
      setTokenWorker(result.worker);
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

  const installInfo = installInfoQuery.data;
  // Re-read the token's worker from the polled list so last_seen updates live.
  const liveTokenWorker = tokenWorker
    ? (workers.find((w) => w.id === tokenWorker.id) ?? tokenWorker)
    : null;
  const tokenWorkerConnected = Boolean(liveTokenWorker?.last_seen);
  const connectedProfile =
    (liveTokenWorker?.config as { runtime_profile?: string } | undefined)?.runtime_profile ?? null;
  const installCommands = useMemo(
    () => (installInfo ? buildWorkerCommands(installInfo, selectedPlatform, displayedToken) : ""),
    [installInfo, selectedPlatform, displayedToken],
  );

  const handleCopyCommand = async () => {
    await navigator.clipboard.writeText(installCommands);
    setCommandCopied(true);
    setTimeout(() => setCommandCopied(false), 2000);
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
          <div className="max-h-[70vh] space-y-3 overflow-y-auto py-2">
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

            {installInfo ? (
              <>
                <Separator />
                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-medium">
                      {translate("custom.pages.workers.dialogs.token.install_title")}
                    </h4>
                    <p className="text-xs text-muted-foreground">
                      {translate("custom.pages.workers.dialogs.token.install_desc")}
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label>{translate("custom.pages.workers.dialogs.token.platform_label")}</Label>
                    <Select value={selectedPlatform} onValueChange={setSelectedPlatform}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {installInfo.platforms.map((platform) => (
                          <SelectItem key={platform.id} value={platform.id}>
                            {platform.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {installInfo.platforms.find((p) => p.id === selectedPlatform)?.notes ? (
                      <p className="text-xs text-muted-foreground">
                        {installInfo.platforms.find((p) => p.id === selectedPlatform)?.notes}
                      </p>
                    ) : null}
                  </div>
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-lg bg-muted p-3 pr-12 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">
                      {installCommands}
                    </pre>
                    <Button
                      variant="outline"
                      size="icon"
                      className="absolute right-2 top-2 h-7 w-7"
                      onClick={handleCopyCommand}
                      aria-label={translate("custom.pages.workers.dialogs.token.copy_command")}
                    >
                      {commandCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    {tokenWorkerConnected ? (
                      <>
                        <Check className="h-4 w-4 text-green-600" />
                        <span>
                          {translate("custom.pages.workers.dialogs.token.connected")}
                          {connectedProfile ? ` (${connectedProfile})` : ""}
                        </span>
                      </>
                    ) : (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {translate("custom.pages.workers.dialogs.token.waiting")}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </>
            ) : null}
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
