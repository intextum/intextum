import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNotify, useTranslate } from "@/lib/app-context";
import { useConfirm } from "@/lib/confirm-context";
import { KeyRound, Pencil, Plus, ShieldAlert, Trash2 } from "lucide-react";

import { getAuthConfig, type AuthProvidersInfo } from "@/authConfig";
import { groupsApi, usersApi, type AppUserEntry, type GroupEntry } from "@/dataProvider";
import { queryKeys } from "@/lib/query-client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { ChipInput } from "@/components/ui/chip-input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

interface UserFormState {
  username: string;
  email: string;
  displayName: string;
  password: string;
  isAdmin: boolean;
  isDisabled: boolean;
  groups: string[];
}

interface GroupFormState {
  slug: string;
  displayName: string;
  description: string;
  proxyAliases: string[];
}

const EMPTY_USER_FORM: UserFormState = {
  username: "",
  email: "",
  displayName: "",
  password: "",
  isAdmin: false,
  isDisabled: false,
  groups: [],
};

const EMPTY_GROUP_FORM: GroupFormState = {
  slug: "",
  displayName: "",
  description: "",
  proxyAliases: [],
};

const EMPTY_USERS: AppUserEntry[] = [];
const EMPTY_GROUPS: GroupEntry[] = [];

export function AuthAdminPanel() {
  const notify = useNotify();
  const translate = useTranslate();
  const confirm = useConfirm();

  const [userDialogOpen, setUserDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AppUserEntry | null>(null);
  const [userForm, setUserForm] = useState<UserFormState>(EMPTY_USER_FORM);
  const [passwordDialogUser, setPasswordDialogUser] = useState<AppUserEntry | null>(null);
  const [passwordDraft, setPasswordDraft] = useState("");

  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<GroupEntry | null>(null);
  const [groupForm, setGroupForm] = useState<GroupFormState>(EMPTY_GROUP_FORM);

  const authAdminQuery = useQuery({
    queryKey: queryKeys.auth.admin,
    queryFn: async () => {
      const [nextUsers, nextGroups, nextConfig] = await Promise.all([
        usersApi.list(),
        groupsApi.list(),
        getAuthConfig(true),
      ]);
      return { users: nextUsers, groups: nextGroups, authConfig: nextConfig };
    },
  });
  const { refetch: refetchAuthAdmin } = authAdminQuery;
  const users: AppUserEntry[] = authAdminQuery.data?.users ?? EMPTY_USERS;
  const groups: GroupEntry[] = authAdminQuery.data?.groups ?? EMPTY_GROUPS;
  const authConfig: AuthProvidersInfo | null = authAdminQuery.data?.authConfig ?? null;

  useEffect(() => {
    if (authAdminQuery.error) {
      notify("Failed to load auth admin data", { type: "error" });
    }
  }, [authAdminQuery.error, notify]);

  const groupOptions = useMemo(
    () => groups.map((group) => ({ slug: group.slug, label: group.display_name || group.slug })),
    [groups],
  );

  const openCreateUser = () => {
    setEditingUser(null);
    setUserForm(EMPTY_USER_FORM);
    setUserDialogOpen(true);
  };

  const openEditUser = (user: AppUserEntry) => {
    setEditingUser(user);
    setUserForm({
      username: user.username,
      email: user.email || "",
      displayName: user.display_name || "",
      password: "",
      isAdmin: user.is_admin,
      isDisabled: user.is_disabled,
      groups: user.groups || [],
    });
    setUserDialogOpen(true);
  };

  const saveUser = async () => {
    try {
      if (editingUser) {
        await usersApi.update(editingUser.sub, {
          username: userForm.username,
          email: userForm.email || undefined,
          display_name: userForm.displayName || undefined,
          is_admin: userForm.isAdmin,
          is_disabled: userForm.isDisabled,
          groups: userForm.groups,
        });
      } else {
        await usersApi.create({
          username: userForm.username,
          password: userForm.password,
          email: userForm.email || undefined,
          display_name: userForm.displayName || undefined,
          is_admin: userForm.isAdmin,
          is_disabled: userForm.isDisabled,
          groups: userForm.groups,
        });
      }
      setUserDialogOpen(false);
      setUserForm(EMPTY_USER_FORM);
      notify("User saved", { type: "success" });
      await refetchAuthAdmin();
    } catch {
      notify("Failed to save user", { type: "error" });
    }
  };

  const resetPassword = async () => {
    if (!passwordDialogUser || !passwordDraft.trim()) {
      return;
    }
    try {
      await usersApi.setPassword(passwordDialogUser.sub, { password: passwordDraft });
      setPasswordDraft("");
      setPasswordDialogUser(null);
      notify("Password updated", { type: "success" });
      await refetchAuthAdmin();
    } catch {
      notify("Failed to update password", { type: "error" });
    }
  };

  const openCreateGroup = () => {
    setEditingGroup(null);
    setGroupForm(EMPTY_GROUP_FORM);
    setGroupDialogOpen(true);
  };

  const openEditGroup = (group: GroupEntry) => {
    setEditingGroup(group);
    setGroupForm({
      slug: group.slug,
      displayName: group.display_name,
      description: group.description || "",
      proxyAliases: group.proxy_aliases || [],
    });
    setGroupDialogOpen(true);
  };

  const saveGroup = async () => {
    try {
      if (editingGroup) {
        await groupsApi.update(editingGroup.slug, {
          display_name: groupForm.displayName,
          description: groupForm.description || undefined,
          proxy_aliases: groupForm.proxyAliases,
        });
      } else {
        await groupsApi.create({
          slug: groupForm.slug,
          display_name: groupForm.displayName,
          description: groupForm.description || undefined,
          proxy_aliases: groupForm.proxyAliases,
        });
      }
      setGroupDialogOpen(false);
      setGroupForm(EMPTY_GROUP_FORM);
      notify("Group saved", { type: "success" });
      await refetchAuthAdmin();
    } catch {
      notify("Failed to save group", { type: "error" });
    }
  };

  const removeGroup = async (slug: string) => {
    if (
      !(await confirm({
        title: "Delete group?",
        description: `Delete group ${slug}?`,
        confirmLabel: translate("custom.confirm.delete"),
        destructive: true,
      }))
    ) {
      return;
    }
    try {
      await groupsApi.remove(slug);
      notify("Group removed", { type: "info" });
      await refetchAuthAdmin();
    } catch {
      notify("Failed to remove group", { type: "error" });
    }
  };

  if (authAdminQuery.isLoading) {
    return <div className="text-sm text-muted-foreground">Loading authentication settings...</div>;
  }

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="space-y-1">
          <h3 className="text-lg font-medium">Provider status</h3>
          <p className="text-sm text-muted-foreground">
            Authentication providers are controlled by environment config.
          </p>
        </div>
        <Separator />
        <div className="space-y-3">
          {authConfig?.dev_enabled ? (
            <Alert>
              <ShieldAlert className="h-4 w-4" />
              <AlertTitle>Insecure dev auth enabled</AlertTitle>
              <AlertDescription>
                Development auto-login is active. This should not be enabled in production.
              </AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Badge variant={authConfig?.local_enabled ? "default" : "secondary"}>
              Local auth {authConfig?.local_enabled ? "enabled" : "disabled"}
            </Badge>
            <Badge variant={authConfig?.proxy_enabled ? "default" : "secondary"}>
              Proxy auth {authConfig?.proxy_enabled ? "enabled" : "disabled"}
            </Badge>
            <Badge variant={authConfig?.dev_enabled ? "destructive" : "secondary"}>
              Dev auth {authConfig?.dev_enabled ? "enabled" : "disabled"}
            </Badge>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-lg font-medium">Users</h3>
            <p className="text-sm text-muted-foreground">
              Manage canonical app users, linked providers, and local passwords.
            </p>
          </div>
          <Button onClick={openCreateUser}>
            <Plus className="mr-2 h-4 w-4" />
            Add user
          </Button>
        </div>
        <Separator />
        <div className="overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Providers</TableHead>
                <TableHead>Groups</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.sub}>
                  <TableCell>
                    <div className="font-medium">{user.display_name || user.username}</div>
                    <div className="text-xs text-muted-foreground">
                      {user.username}
                      {user.email ? ` • ${user.email}` : ""}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {user.providers.map((provider) => (
                        <Badge key={provider} variant="secondary">
                          {provider}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {user.groups.map((group) => (
                        <Badge key={group} variant="outline">
                          {group}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {user.is_admin ? <Badge>admin</Badge> : null}
                      {user.is_disabled ? <Badge variant="destructive">disabled</Badge> : null}
                      {user.has_local_credential ? (
                        <Badge variant="secondary">local password</Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEditUser(user)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          setPasswordDialogUser(user);
                          setPasswordDraft("");
                        }}
                      >
                        <KeyRound className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-lg font-medium">Groups</h3>
            <p className="text-sm text-muted-foreground">
              Manage ACL groups and proxy group alias mapping.
            </p>
          </div>
          <Button onClick={openCreateGroup}>
            <Plus className="mr-2 h-4 w-4" />
            Add group
          </Button>
        </div>
        <Separator />
        <div className="overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Group</TableHead>
                <TableHead>Proxy aliases</TableHead>
                <TableHead>Members</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((group) => (
                <TableRow key={group.slug}>
                  <TableCell>
                    <div className="font-medium">{group.display_name}</div>
                    <div className="text-xs text-muted-foreground">{group.slug}</div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {group.proxy_aliases.map((alias) => (
                        <Badge key={alias} variant="secondary">
                          {alias}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>{group.member_count}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEditGroup(group)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        onClick={() => {
                          void removeGroup(group.slug);
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
      </section>

      <Dialog open={userDialogOpen} onOpenChange={setUserDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingUser ? "Edit user" : "Create local user"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="auth-user-username">Username</Label>
              <Input
                id="auth-user-username"
                value={userForm.username}
                onChange={(event) =>
                  setUserForm((prev) => ({ ...prev, username: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="auth-user-email">Email</Label>
              <Input
                id="auth-user-email"
                value={userForm.email}
                onChange={(event) =>
                  setUserForm((prev) => ({ ...prev, email: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="auth-user-display-name">Display name</Label>
              <Input
                id="auth-user-display-name"
                value={userForm.displayName}
                onChange={(event) =>
                  setUserForm((prev) => ({ ...prev, displayName: event.target.value }))
                }
              />
            </div>
            {!editingUser ? (
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="auth-user-password">Initial password</Label>
                <Input
                  id="auth-user-password"
                  type="password"
                  value={userForm.password}
                  onChange={(event) =>
                    setUserForm((prev) => ({ ...prev, password: event.target.value }))
                  }
                />
              </div>
            ) : null}
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">Admin</p>
                <p className="text-xs text-muted-foreground">Grants access to the admin area.</p>
              </div>
              <Switch
                checked={userForm.isAdmin}
                onCheckedChange={(checked) =>
                  setUserForm((prev) => ({ ...prev, isAdmin: checked }))
                }
              />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">Disabled</p>
                <p className="text-xs text-muted-foreground">
                  Blocks sign-in and revokes sessions.
                </p>
              </div>
              <Switch
                checked={userForm.isDisabled}
                onCheckedChange={(checked) =>
                  setUserForm((prev) => ({ ...prev, isDisabled: checked }))
                }
              />
            </div>
            <div className="space-y-3 md:col-span-2">
              <Label>Groups</Label>
              <div className="grid gap-2 md:grid-cols-2">
                {groupOptions.map((group) => (
                  <label
                    key={group.slug}
                    className="flex items-center gap-2 rounded-md border p-2 text-sm"
                  >
                    <Checkbox
                      checked={userForm.groups.includes(group.slug)}
                      onCheckedChange={(checked) => {
                        setUserForm((prev) => ({
                          ...prev,
                          groups: checked
                            ? [...prev.groups, group.slug]
                            : prev.groups.filter((item) => item !== group.slug),
                        }));
                      }}
                    />
                    <span>{group.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUserDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void saveUser()}>
              {editingUser ? "Save user" : "Create user"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={passwordDialogUser !== null}
        onOpenChange={(open) => !open && setPasswordDialogUser(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="auth-user-reset-password">New password</Label>
            <Input
              id="auth-user-reset-password"
              type="password"
              value={passwordDraft}
              onChange={(event) => setPasswordDraft(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasswordDialogUser(null)}>
              Cancel
            </Button>
            <Button onClick={() => void resetPassword()}>Update password</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={groupDialogOpen} onOpenChange={setGroupDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingGroup ? "Edit group" : "Create group"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {!editingGroup ? (
              <div className="space-y-2">
                <Label htmlFor="auth-group-slug">Slug</Label>
                <Input
                  id="auth-group-slug"
                  value={groupForm.slug}
                  onChange={(event) =>
                    setGroupForm((prev) => ({ ...prev, slug: event.target.value }))
                  }
                />
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="auth-group-display-name">Display name</Label>
              <Input
                id="auth-group-display-name"
                value={groupForm.displayName}
                onChange={(event) =>
                  setGroupForm((prev) => ({ ...prev, displayName: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="auth-group-description">Description</Label>
              <Textarea
                id="auth-group-description"
                value={groupForm.description}
                onChange={(event) =>
                  setGroupForm((prev) => ({ ...prev, description: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Proxy aliases</Label>
              <ChipInput
                values={groupForm.proxyAliases}
                onChange={(next) => setGroupForm((prev) => ({ ...prev, proxyAliases: next }))}
                placeholder="Add proxy group alias"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGroupDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void saveGroup()}>
              {editingGroup ? "Save group" : "Create group"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
