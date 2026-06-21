import { Cpu, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";
import { EmptyState } from "@/components/page/EmptyState";
import { LoadingState } from "@/components/page/LoadingState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { stageLabel } from "@/lib/status-presentations";
import type { Worker, WorkerTaskQueueCleanupResponse, WorkerTaskQueueItem } from "@/dataProvider";

type TranslateFn = (key: string, options?: unknown) => string;

type WorkerRuntimeConfig = {
  runtime_profile?: string;
  classification_device?: string;
  capabilities?: string[];
  python_version?: string;
  platform_system?: string;
  torch_version?: string | null;
  docling_ocr_engine?: string;
};

type WorkersManagementContentProps = {
  cleanupLoading: boolean;
  cleanupResult: WorkerTaskQueueCleanupResponse | null;
  embedded: boolean;
  loading: boolean;
  queueError: string | null;
  submitting: boolean;
  taskTotal: number;
  tasks: WorkerTaskQueueItem[];
  tasksLoading: boolean;
  translate: TranslateFn;
  workerError: string | null;
  workers: Worker[];
  onCleanupStaleTasks: () => void;
  onCreateWorker: () => void;
  onDeleteWorker: (worker: Worker) => void;
  onEditWorker: (worker: Worker) => void;
  onRefreshTasks: () => void;
  onRotateToken: (worker: Worker) => void;
};

function formatRelativeTime(dateStr: string | null, translate: TranslateFn): string {
  if (!dateStr) return translate("custom.pages.workers.time.never");
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return translate("custom.pages.workers.time.just_now");
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return translate("custom.pages.workers.time.minutes_ago", { count: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return translate("custom.pages.workers.time.hours_ago", { count: diffHr });
  const diffDay = Math.floor(diffHr / 24);
  return translate("custom.pages.workers.time.days_ago", { count: diffDay });
}

function formatTaskAge(seconds: number | null | undefined): string {
  if (seconds == null) return "-";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function StatusBadge({ status, translate }: { status: string; translate: TranslateFn }) {
  switch (status) {
    case "active":
      return (
        <Badge variant="secondary" className="font-normal border-transparent bg-muted/50">
          <span className="mr-1.5 flex h-2 w-2 rounded-full bg-green-500" />
          {translate("custom.pages.workers.status.active")}
        </Badge>
      );
    case "error":
      return (
        <Badge variant="secondary" className="font-normal border-transparent bg-muted/50">
          <span className="mr-1.5 flex h-2 w-2 rounded-full bg-red-500" />
          {translate("custom.pages.workers.status.error")}
        </Badge>
      );
    default:
      return (
        <Badge
          variant="secondary"
          className="font-normal border-transparent bg-muted/50 text-muted-foreground"
        >
          <span className="mr-1.5 flex h-2 w-2 rounded-full bg-slate-300" />
          {translate("custom.pages.workers.status.inactive")}
        </Badge>
      );
  }
}

function TaskStatusBadge({ status }: { status: string }) {
  const variant: "default" | "secondary" | "destructive" =
    status === "FAILED" ? "destructive" : status === "COMPLETED" ? "default" : "secondary";
  return (
    <Badge variant={variant} className="font-normal">
      {status}
    </Badge>
  );
}

function RuntimeSummary({ worker, translate }: { worker: Worker; translate: TranslateFn }) {
  const config = worker.config as WorkerRuntimeConfig;
  const profile = config.runtime_profile;

  if (!profile) {
    return <span className="text-sm text-muted-foreground">-</span>;
  }

  const device = config.classification_device || profile;
  const platform = config.platform_system || "";
  const capabilities = Array.isArray(config.capabilities) ? config.capabilities.join(", ") : "";

  return (
    <div className="min-w-[150px] space-y-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="font-normal uppercase">
          {profile}
        </Badge>
        <span className="text-xs text-muted-foreground">{device}</span>
      </div>
      <div className="text-xs text-muted-foreground">
        {[platform, config.python_version ? `py ${config.python_version}` : ""]
          .filter(Boolean)
          .join(" · ")}
      </div>
      {capabilities && (
        <div className="max-w-[210px] truncate text-xs text-muted-foreground" title={capabilities}>
          {translate("custom.pages.workers.runtime.capabilities", { capabilities })}
        </div>
      )}
    </div>
  );
}

export function WorkersManagementContent({
  cleanupLoading,
  cleanupResult,
  embedded,
  loading,
  queueError,
  submitting,
  taskTotal,
  tasks,
  tasksLoading,
  translate,
  workerError,
  workers,
  onCleanupStaleTasks,
  onCreateWorker,
  onDeleteWorker,
  onEditWorker,
  onRefreshTasks,
  onRotateToken,
}: WorkersManagementContentProps) {
  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <h3 className="text-lg font-medium">
          {translate("custom.pages.workers.registered_title")}
        </h3>
        {embedded && (
          <Button variant="default" size="sm" onClick={onCreateWorker}>
            <Plus className="h-4 w-4 mr-2" />
            {translate("custom.pages.workers.add_worker")}
          </Button>
        )}
      </div>
      <Separator />
      <div>
        {workerError && (
          <Alert variant="destructive" className="mb-4 py-2">
            <AlertDescription>{workerError}</AlertDescription>
          </Alert>
        )}
        {loading ? (
          <LoadingState rows={3} />
        ) : workers.length === 0 ? (
          <EmptyState
            icon={Cpu}
            title={translate("custom.pages.workers.no_workers")}
            description={translate("custom.pages.workers.no_workers_hint")}
            actions={
              <Button size="sm" onClick={onCreateWorker}>
                <Plus className="mr-2 h-4 w-4" />
                {translate("custom.pages.workers.add_worker")}
              </Button>
            }
          />
        ) : (
          <div className="overflow-hidden rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{translate("custom.pages.workers.table.name")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.table.status")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.table.runtime")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.table.description")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.table.last_seen")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.table.created")}</TableHead>
                  <TableHead className="text-right">
                    {translate("custom.pages.workers.table.actions")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workers.map((worker) => (
                  <TableRow key={worker.id}>
                    <TableCell className="font-medium">{worker.name}</TableCell>
                    <TableCell>
                      <StatusBadge status={worker.status} translate={translate} />
                    </TableCell>
                    <TableCell>
                      <RuntimeSummary worker={worker} translate={translate} />
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-muted-foreground">
                      {worker.description || "-"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatRelativeTime(worker.last_seen, translate)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(worker.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => onEditWorker(worker)}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {translate("custom.pages.workers.actions.edit")}
                          </TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => onRotateToken(worker)}
                              disabled={submitting}
                            >
                              <RotateCcw className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {translate("custom.pages.workers.actions.rotate")}
                          </TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive hover:text-destructive"
                              onClick={() => onDeleteWorker(worker)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {translate("custom.pages.workers.actions.delete")}
                          </TooltipContent>
                        </Tooltip>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-medium">{translate("custom.pages.workers.queue.title")}</h3>
            <p className="text-sm text-muted-foreground">
              {translate("custom.pages.workers.queue.description", { count: taskTotal })}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCleanupStaleTasks}
              disabled={cleanupLoading}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              {translate("custom.pages.workers.queue.cleanup")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRefreshTasks}
              disabled={tasksLoading}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              {translate("custom.pages.workers.refresh")}
            </Button>
          </div>
        </div>
        <Separator />
        {cleanupResult ? (
          <div className="rounded-lg border bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
            {translate("custom.pages.workers.queue.cleanup_result", cleanupResult)}
          </div>
        ) : null}
        {queueError ? (
          <Alert variant="destructive" className="py-2">
            <AlertDescription>{queueError}</AlertDescription>
          </Alert>
        ) : tasksLoading ? (
          <LoadingState rows={2} />
        ) : tasks.length === 0 ? (
          <div className="rounded-lg border bg-muted/20 p-4 text-sm text-muted-foreground">
            {translate("custom.pages.workers.queue.empty")}
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{translate("custom.pages.workers.queue.table.task")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.status")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.path")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.worker")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.claim_age")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.retry")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.updated")}</TableHead>
                  <TableHead>{translate("custom.pages.workers.queue.table.error")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="font-mono text-xs">{task.id.slice(0, 8)}</div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          <Badge variant="outline" className="font-normal">
                            {task.task_type}
                          </Badge>
                          {task.content_kind ? <span>{task.content_kind}</span> : null}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <TaskStatusBadge status={task.status} />
                        {stageLabel(task.stage, translate) ? (
                          <div className="text-xs text-muted-foreground">
                            {stageLabel(task.stage, translate)}
                          </div>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate" title={task.relative_path}>
                      {task.relative_path}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {task.claimed_by || "-"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">
                          {formatTaskAge(task.claim_age_seconds)}
                        </span>
                        {task.is_stale ? (
                          <Badge variant="destructive" className="font-normal">
                            {translate("custom.pages.workers.queue.stale")}
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {task.retry_count}/{task.max_retries}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatRelativeTime(task.updated_at, translate)}
                    </TableCell>
                    <TableCell
                      className="max-w-[240px] truncate text-muted-foreground"
                      title={task.error_message || ""}
                    >
                      {task.error_message || "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </section>
  );
}
