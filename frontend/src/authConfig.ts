export interface AuthProvidersInfo {
  local_enabled: boolean;
  proxy_enabled: boolean;
  dev_enabled: boolean;
  load_error?: boolean;
  session_cookie_name: string;
  csrf_cookie_name: string;
  csrf_header_name: string;
  proxy_login_url: string;
  proxy_logout_url: string;
}

const DEFAULT_AUTH_CONFIG: AuthProvidersInfo = {
  local_enabled: false,
  proxy_enabled: false,
  dev_enabled: false,
  load_error: false,
  session_cookie_name: "intextum_session",
  csrf_cookie_name: "intextum_csrf",
  csrf_header_name: "X-CSRF-Token",
  proxy_login_url: "/oauth2/start",
  proxy_logout_url: "/oauth2/sign_out",
};

let cachedAuthConfig: AuthProvidersInfo | null = null;

export async function getAuthConfig(forceRefresh: boolean = false): Promise<AuthProvidersInfo> {
  if (!forceRefresh && cachedAuthConfig) {
    return cachedAuthConfig;
  }

  try {
    const response = await fetch("/api/auth/providers", { credentials: "include" });
    if (!response.ok) {
      cachedAuthConfig = { ...DEFAULT_AUTH_CONFIG, load_error: true };
      return cachedAuthConfig;
    }
    const payload = (await response.json()) as Partial<AuthProvidersInfo>;
    cachedAuthConfig = {
      ...DEFAULT_AUTH_CONFIG,
      ...payload,
    };
    return cachedAuthConfig;
  } catch {
    cachedAuthConfig = { ...DEFAULT_AUTH_CONFIG, load_error: true };
    return cachedAuthConfig;
  }
}

export function clearAuthConfigCache(): void {
  cachedAuthConfig = null;
}
