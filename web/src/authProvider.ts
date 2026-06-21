import { getAuthConfig } from "@/authConfig";
import { authApi } from "@/dataProvider";

export interface UserInfo {
  sub?: string | null;
  username: string;
  email?: string | null;
  groups: string[];
  preferred_username?: string | null;
  is_admin?: boolean;
  must_change_password?: boolean;
  auth_provider?: string;
}

export interface UserIdentity {
  id: string;
  fullName: string;
  avatar?: string;
}

export interface UserPermissions {
  groups: string[];
  is_admin: boolean;
  auth_provider: string;
}

export async function fetchCurrentUser(forceRefresh: boolean = false): Promise<UserInfo> {
  void forceRefresh;

  const response = await fetch("/api/me", { credentials: "include" });
  if (!response.ok) {
    throw new Error("Failed to fetch current user");
  }
  return (await response.json()) as UserInfo;
}

export function clearAuthCaches() {}

export type LoginParams = {
  provider?: "local" | "proxy" | string;
  username_or_email?: string;
  email?: string;
  password?: string;
};

export async function loginWithCredentials(params: LoginParams = {}): Promise<void> {
  const authConfig = await getAuthConfig(true);
  const provider = typeof params.provider === "string" ? params.provider : "local";

  if (provider === "proxy") {
    window.location.href = authConfig.proxy_login_url;
    return;
  }

  if (!authConfig.local_enabled) {
    if (authConfig.proxy_enabled) {
      window.location.href = authConfig.proxy_login_url;
      return;
    }
    throw new Error("Local authentication is disabled");
  }

  await authApi.loginLocal({
    username_or_email: String(params.username_or_email ?? params.email ?? ""),
    password: String(params.password ?? ""),
  });
  clearAuthCaches();
}

export async function logoutCurrentUser(): Promise<boolean> {
  const authConfig = await getAuthConfig();
  let currentProvider = "anonymous";
  try {
    const currentUser = await fetchCurrentUser(true);
    currentProvider = currentUser.auth_provider || "anonymous";
  } catch {
    currentProvider = "anonymous";
  }

  try {
    const result = await authApi.logout();
    currentProvider = result.auth_provider || currentProvider;
    clearAuthCaches();
    if (currentProvider === "proxy") {
      window.location.href = result.proxy_logout_url || authConfig.proxy_logout_url;
      return true;
    }
  } catch {
    clearAuthCaches();
    if (currentProvider === "proxy") {
      window.location.href = authConfig.proxy_logout_url;
      return true;
    }
  }
  return false;
}

export function userToIdentity(user: UserInfo | null): UserIdentity {
  if (!user || !user.auth_provider || user.auth_provider === "anonymous") {
    return {
      id: "anonymous",
      fullName: "Anonymous",
    };
  }

  return {
    id: user.sub || user.username,
    fullName: user.preferred_username?.trim() || user.username,
    avatar: undefined,
  };
}

export function userToPermissions(user: UserInfo | null): UserPermissions {
  return {
    groups: user?.groups || [],
    is_admin: user?.is_admin ?? false,
    auth_provider: user?.auth_provider || "anonymous",
  };
}
