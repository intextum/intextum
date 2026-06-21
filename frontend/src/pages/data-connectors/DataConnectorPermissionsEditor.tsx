import { useMemo, useState } from "react";
import { useTranslate } from "@/lib/app-context";
import { Trash2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AppUserEntry, GroupEntry } from "@/dataProvider";
import {
  formatTrusteeLabel,
  normalizePermissionAccess,
  type PermissionAccess,
  type SourcePermissionDraft,
} from "@/pages/data-connectors/shared";

interface DataConnectorPermissionsEditorProps {
  permissions: SourcePermissionDraft[];
  users: AppUserEntry[];
  groups: GroupEntry[];
  showHeader?: boolean;
  loading?: boolean;
  disabled?: boolean;
  onChange: (permissions: SourcePermissionDraft[]) => void;
}

export function DataConnectorPermissionsEditor({
  permissions,
  users,
  groups,
  showHeader = true,
  loading = false,
  disabled = false,
  onChange,
}: DataConnectorPermissionsEditorProps) {
  const translate = useTranslate();
  const [selectedTrustee, setSelectedTrustee] = useState("");
  const [selectedAccess, setSelectedAccess] = useState<PermissionAccess>("allow");

  const trusteeOptions = useMemo(
    () => [
      { value: "everyone", label: translate("custom.permissions.everyone") },
      ...users.map((user) => ({
        value: `sub:${user.sub}`,
        label: user.display_name || user.username,
      })),
      ...groups.map((group) => ({
        value: `group:${group.slug}`,
        label: group.display_name || group.slug,
      })),
    ],
    [groups, translate, users],
  );

  const trusteeLabelByValue = useMemo(
    () => new Map(trusteeOptions.map((option) => [option.value, option.label])),
    [trusteeOptions],
  );

  const existingTrustees = useMemo(
    () => new Set(permissions.map((permission) => permission.trustee)),
    [permissions],
  );

  const availableTrustees = useMemo(
    () => trusteeOptions.filter((option) => !existingTrustees.has(option.value)),
    [existingTrustees, trusteeOptions],
  );

  const selectedTrusteeValue = existingTrustees.has(selectedTrustee) ? "" : selectedTrustee;

  const handleAddPermission = () => {
    if (!selectedTrusteeValue) {
      return;
    }
    onChange([
      ...permissions,
      {
        trustee: selectedTrusteeValue,
        access: selectedAccess,
      },
    ]);
    setSelectedTrustee("");
    setSelectedAccess("allow");
  };

  const handleRemovePermission = (trustee: string) => {
    onChange(permissions.filter((permission) => permission.trustee !== trustee));
  };

  const handleAccessChange = (trustee: string, access: string) => {
    const nextAccess = normalizePermissionAccess(access);
    onChange(
      permissions.map((permission) =>
        permission.trustee === trustee ? { ...permission, access: nextAccess } : permission,
      ),
    );
  };

  return (
    <div className="space-y-3 rounded-md border p-4">
      {showHeader && (
        <div>
          <h3 className="text-sm font-medium">
            {translate("custom.pages.data_connectors.permissions_title")}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {translate("custom.pages.data_connectors.permissions_description")}
          </p>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : permissions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {translate("custom.permissions.no_permissions")}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{translate("custom.permissions.trustee_label")}</TableHead>
              <TableHead>{translate("custom.permissions.access_label")}</TableHead>
              <TableHead className="text-right">
                {translate("custom.pages.data_connectors.table.actions")}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {permissions.map((permission) => (
              <TableRow key={permission.trustee}>
                <TableCell className="font-medium">
                  {formatTrusteeLabel(permission.trustee, trusteeLabelByValue, translate)}
                </TableCell>
                <TableCell className="w-[160px]">
                  <Select
                    value={permission.access}
                    onValueChange={(value) => handleAccessChange(permission.trustee, value)}
                    disabled={disabled}
                  >
                    <SelectTrigger>
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
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => handleRemovePermission(permission.trustee)}
                    disabled={disabled}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_140px_auto] sm:items-center">
        <Select
          value={selectedTrusteeValue}
          onValueChange={setSelectedTrustee}
          disabled={disabled || loading || availableTrustees.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder={translate("custom.permissions.select_principal")} />
          </SelectTrigger>
          <SelectContent>
            {availableTrustees.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={selectedAccess}
          onValueChange={(value) => setSelectedAccess(normalizePermissionAccess(value))}
          disabled={disabled || loading || availableTrustees.length === 0}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="allow">{translate("custom.permissions.access_allow")}</SelectItem>
            <SelectItem value="deny">{translate("custom.permissions.access_deny")}</SelectItem>
          </SelectContent>
        </Select>
        <Button
          size="sm"
          onClick={handleAddPermission}
          disabled={disabled || loading || !selectedTrusteeValue || availableTrustees.length === 0}
        >
          {translate("custom.permissions.add")}
        </Button>
      </div>
    </div>
  );
}
