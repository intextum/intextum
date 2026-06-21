import { useQuery } from "@tanstack/react-query";
import { useTranslate } from "@/lib/app-context";
import { Files, HardDrive, Loader2, Cpu, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { contentApi, workersApi, type ContentItemInfo } from "@/dataProvider";
import { formatSize } from "@/lib/content-utils";
import { queryKeys } from "@/lib/query-client";
import { Link } from "react-router";

interface StatsCardsProps {
  path?: string;
  refreshKey?: number;
  global?: boolean;
}

const EMPTY_STATS = {
  totalItems: 0,
  totalSize: 0,
  processingCount: 0,
  staleEnrichmentCount: 0,
  activeWorkers: 0,
};

export const StatsCards = ({ path = "", refreshKey = 0, global = false }: StatsCardsProps) => {
  const translate = useTranslate();
  const statsQuery = useQuery({
    queryKey: [
      ...queryKeys.content.stats(global ? "global" : "folder", path),
      queryKeys.workers.all,
      refreshKey,
    ],
    queryFn: async () => {
      let totalItems = 0;
      let totalSize = 0;
      let processingCount = 0;
      let staleEnrichmentCount = 0;

      if (global) {
        const globalStats = await contentApi.getGlobalStats();
        totalItems = globalStats.total_items;
        totalSize = globalStats.total_size_bytes;
        processingCount = globalStats.processing_count;
        staleEnrichmentCount = globalStats.stale_enrichment_count;
      } else {
        const tree = await contentApi.getTree(path, 1);
        const folders = tree.root.children?.filter((node) => node.type === "folder") ?? [];
        const files = tree.root.children?.filter((node) => node.type === "file") ?? [];

        totalItems = folders.length + files.length;

        files.forEach((file) => {
          const details = file.details as ContentItemInfo | undefined;
          if (details) {
            totalSize += details.size_bytes || 0;
            if (["QUEUED", "PROCESSING", "RETRYING"].includes(details.status || "")) {
              processingCount++;
            }
          }
        });
      }

      const workers = await workersApi.list();
      const activeWorkers = workers.workers.filter((worker) => worker.status === "active").length;

      return {
        totalItems,
        totalSize,
        processingCount,
        staleEnrichmentCount,
        activeWorkers,
      };
    },
  });
  const stats = statsQuery.data ?? EMPTY_STATS;

  const items = [
    {
      title: translate("custom.content.stats.total_items"),
      value: stats.totalItems.toString(),
      description: global
        ? translate("custom.content.stats.all_files")
        : translate("custom.content.stats.items_in_folder"),
      icon: Files,
      color: "text-muted-foreground",
    },
    {
      title: translate("custom.content.stats.storage_used"),
      value: formatSize(stats.totalSize),
      description: global
        ? translate("custom.content.stats.total_system_size")
        : translate("custom.content.stats.total_size"),
      icon: HardDrive,
      color: "text-muted-foreground",
    },
    {
      title: translate("custom.content.stats.processing"),
      value: stats.processingCount.toString(),
      description: translate("custom.content.stats.active_tasks"),
      icon: Loader2,
      color: stats.processingCount > 0 ? "text-primary animate-spin" : "text-muted-foreground",
    },
    ...(global
      ? [
          {
            title: translate("custom.content.stats.needs_refresh"),
            value: stats.staleEnrichmentCount.toString(),
            description: translate("custom.content.stats.needs_refresh_hint"),
            icon: AlertTriangle,
            color: stats.staleEnrichmentCount > 0 ? "text-amber-600" : "text-muted-foreground",
            href:
              stats.staleEnrichmentCount > 0
                ? "/content?view=all&stale_enrichment=true"
                : undefined,
          },
        ]
      : []),
    {
      title: translate("custom.content.stats.active_workers"),
      value: stats.activeWorkers.toString(),
      description: translate("custom.content.stats.running_workers"),
      icon: Cpu,
      color: "text-muted-foreground",
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 mb-6">
      {items.map((item) => {
        const card = (
          <Card
            key={item.title}
            className={`shadow-sm ${item.href ? "transition-colors hover:border-amber-300 hover:bg-amber-50/40 dark:hover:bg-amber-950/10" : ""}`}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{item.title}</CardTitle>
              <item.icon className={`h-4 w-4 ${item.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{item.value}</div>
              <p className="text-xs text-muted-foreground mt-1">{item.description}</p>
            </CardContent>
          </Card>
        );
        return item.href ? (
          <Link key={item.title} to={item.href} className="block">
            {card}
          </Link>
        ) : (
          card
        );
      })}
    </div>
  );
};
