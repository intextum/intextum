import { useCallback, useEffect, useMemo, useState } from "react";
import { useNotify, useTranslate } from "@/lib/app-context";
import { Shield, Trash2, Plus, Users, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type DataConnectorEntry,
  type PermissionEntry,
  type AppUserEntry,
  type GroupEntry,
  dataConnectorsApi,
  groupsApi,
  permissionsApi,
} from "@/dataProvider";

function formatTrustee(
  trustee: string,
  trusteeLabelByValue: Map<string, string>,
  translate: (key: string, options?: Record<string, unknown>) => string,
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

interface SourcePermissionsCardProps {
  source: DataConnectorEntry;
  users: AppUserEntry[];
  groups: GroupEntry[];
}

function SourcePermissionsCard({ source, users, groups }: SourcePermissionsCardProps) {
  const translate = useTranslate();
  const notify = useNotify();
  const [permissions, setPermissions] = useState<PermissionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [selectedTrustee, setSelectedTrustee] = useState("");
  const [selectedAccess, setSelectedAccess] = useState("allow");

  const trusteeLabelByValue = useMemo(
    () =>
      new Map([
        ...users.map((user) => [`sub:${user.sub}`, user.display_name || user.username] as const),
        ...groups.map(
          (group) => [`group:${group.slug}`, group.display_name || group.slug] as const,
        ),
      ]),
    [groups, users],
  );

  const loadPermissions = useCallback(async () => {
    try {
      const perms = await permissionsApi.list(source.uuid);
      setPermissions(perms);
    } catch {
      // Silently fail for individual folder loads
    } finally {
      setLoading(false);
    }
  }, [source.uuid]);

  useEffect(() => {
    void loadPermissions();
  }, [loadPermissions]);

  const handleAdd = async () => {
    if (!selectedTrustee) return;
    setAdding(true);
    try {
      const perm = await permissionsApi.set(source.uuid, selectedTrustee, selectedAccess);
      setPermissions((prev) => {
        const filtered = prev.filter((p) => p.trustee !== perm.trustee);
        return [...filtered, perm];
      });
      setSelectedTrustee("");
      setSelectedAccess("allow");
      notify(translate("custom.permissions.added_success"), { type: "success" });
    } catch {
      notify(translate("custom.permissions.add_failed"), { type: "error" });
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (trustee: string) => {
    try {
      await permissionsApi.remove(source.uuid, trustee);
      setPermissions((prev) => prev.filter((p) => p.trustee !== trustee));
      notify(translate("custom.permissions.removed_success"), { type: "info" });
    } catch {
      notify(translate("custom.permissions.remove_failed"), { type: "error" });
    }
  };

  const trusteeOptions = [
    { value: "everyone", label: translate("custom.permissions.everyone") },
    ...users.map((u) => ({
      value: `sub:${u.sub}`,
      label: u.display_name || u.username,
    })),
    ...groups.map((group) => ({
      value: `group:${group.slug}`,
      label: group.display_name || group.slug,
    })),
  ];

  // Filter out trustees that already have a permission
  const existingTrustees = new Set(permissions.map((p) => p.trustee));
  const availableTrustees = trusteeOptions.filter((t) => !existingTrustees.has(t.value));

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Shield className="h-4 w-4" />
          {source.name}
        </CardTitle>
        <p className="text-xs text-muted-foreground">{source.connector_type}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : (
          <>
            {permissions.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{translate("custom.permissions.trustee_label")}</TableHead>
                    <TableHead>{translate("custom.permissions.access_label")}</TableHead>
                    <TableHead className="w-[80px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {permissions.map((perm) => (
                    <TableRow key={perm.trustee}>
                      <TableCell className="font-medium">
                        {formatTrustee(perm.trustee, trusteeLabelByValue, translate)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={perm.access === "allow" ? "default" : "destructive"}>
                          {perm.access === "allow"
                            ? translate("custom.permissions.access_allow")
                            : translate("custom.permissions.access_deny")}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemove(perm.trustee)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">
                {translate("custom.permissions.no_permissions")}
              </p>
            )}

            {availableTrustees.length > 0 && (
              <div className="flex items-center gap-2 pt-2">
                <Select value={selectedTrustee} onValueChange={setSelectedTrustee}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder={translate("custom.permissions.select_principal")} />
                  </SelectTrigger>
                  <SelectContent>
                    {availableTrustees.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={selectedAccess} onValueChange={setSelectedAccess}>
                  <SelectTrigger className="w-[100px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="allow">
                      {translate("custom.permissions.access_allow")}
                    </SelectItem>
                    <SelectItem value="deny">
                      {translate("custom.permissions.access_deny")}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Button size="sm" onClick={handleAdd} disabled={!selectedTrustee || adding}>
                  {adding ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  {translate("custom.permissions.add")}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface PermissionsPanelProps {
  showHeader?: boolean;
  refreshToken?: number;
}

export const PermissionsPanel = ({
  showHeader = true,
  refreshToken = 0,
}: PermissionsPanelProps) => {
  const translate = useTranslate();
  const notify = useNotify();
  const [sources, setSources] = useState<DataConnectorEntry[]>([]);
  const [users, setUsers] = useState<AppUserEntry[]>([]);
  const [groups, setGroups] = useState<GroupEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sourcesResult, usersResult, groupsResult] = await Promise.all([
        dataConnectorsApi.list(),
        permissionsApi.listUsers(),
        groupsApi.list(),
      ]);
      setSources(sourcesResult);
      setUsers(usersResult);
      setGroups(groupsResult);
    } catch {
      notify(translate("custom.permissions.loading_failed"), { type: "error" });
    } finally {
      setLoading(false);
    }
  }, [notify, translate]);

  useEffect(() => {
    void loadData();
  }, [loadData, refreshToken]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {showHeader && (
        <div>
          <h3 className="text-lg font-medium flex items-center gap-2">
            <Users className="h-5 w-5" />
            {translate("custom.permissions.title")}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            {translate("custom.permissions.description")}
          </p>
        </div>
      )}

      {sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {translate("custom.permissions.no_folders")}
        </p>
      ) : (
        <div className="space-y-4">
          {sources.map((source) => (
            <SourcePermissionsCard
              key={source.uuid}
              source={source}
              users={users}
              groups={groups}
            />
          ))}
        </div>
      )}
    </div>
  );
};
