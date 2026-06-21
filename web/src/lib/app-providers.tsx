import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider as NextThemeProvider } from "next-themes";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ConfirmProvider } from "@/components/app/confirm-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  fetchCurrentUser,
  loginWithCredentials,
  logoutCurrentUser,
  userToIdentity,
  userToPermissions,
  type LoginParams,
  type UserInfo,
} from "@/authProvider";
import { de } from "@/i18n/de";
import { en } from "@/i18n/en";
import {
  AuthContext,
  I18nContext,
  useAuth,
  type LocaleInfo,
  type TranslateOptions,
  type TranslationMessages,
} from "@/lib/app-context";
import { queryClient } from "@/lib/query-client";

const messages: Record<string, TranslationMessages> = { en, de };
const locales: LocaleInfo[] = [
  { locale: "en", name: "English" },
  { locale: "de", name: "Deutsch" },
];

const readStoredLocale = (): string => {
  if (typeof window === "undefined") {
    return "en";
  }
  const stored = window.localStorage.getItem("locale");
  return stored && messages[stored] ? stored : "en";
};

const readMessage = (locale: string, key: string): unknown =>
  key.split(".").reduce<unknown>((current, segment) => {
    if (current && typeof current === "object" && segment in current) {
      return (current as Record<string, unknown>)[segment];
    }
    return undefined;
  }, messages[locale]);

const interpolate = (message: string, options: TranslateOptions = {}): string =>
  message.replace(/%\{([^}]+)\}/g, (_, name: string) => {
    const value = options[name];
    return value === undefined || value === null ? "" : String(value);
  });

const normalizeTranslateOptions = (options: unknown): TranslateOptions =>
  options && typeof options === "object" && !Array.isArray(options)
    ? (options as TranslateOptions)
    : {};

function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState(readStoredLocale);

  const setLocale = useCallback((nextLocale: string) => {
    const normalizedLocale = messages[nextLocale] ? nextLocale : "en";
    setLocaleState(normalizedLocale);
    window.localStorage.setItem("locale", normalizedLocale);
  }, []);

  const translate = useCallback(
    (key: string, options: unknown = {}) => {
      const normalizedOptions = normalizeTranslateOptions(options);
      const message = readMessage(locale, key) ?? readMessage("en", key);
      if (typeof message === "string") {
        return interpolate(message, normalizedOptions);
      }
      return normalizedOptions._ ?? key;
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, locales, setLocale, translate }),
    [locale, setLocale, translate],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isPending, setIsPending] = useState(true);
  const navigate = useNavigate();

  const refreshUser = useCallback(async () => {
    try {
      const currentUser = await fetchCurrentUser(true);
      setUser(currentUser);
      return currentUser;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser(true)
      .then((currentUser) => {
        if (!cancelled) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPending(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (params: LoginParams = {}, redirectTo = "/") => {
      await loginWithCredentials(params);
      const currentUser = await refreshUser();
      if (currentUser?.auth_provider && currentUser.auth_provider !== "anonymous") {
        navigate(redirectTo, { replace: true });
      }
    },
    [navigate, refreshUser],
  );

  const logout = useCallback(async () => {
    const redirected = await logoutCurrentUser();
    setUser(null);
    if (!redirected) {
      navigate("/login", { replace: true });
    }
  }, [navigate]);

  const value = useMemo(
    () => ({
      user,
      identity: userToIdentity(user),
      permissions: userToPermissions(user),
      isPending,
      refreshUser,
      login,
      logout,
    }),
    [isPending, login, logout, refreshUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <NextThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <AuthProvider>
            <ConfirmProvider>
              <TooltipProvider>{children}</TooltipProvider>
            </ConfirmProvider>
          </AuthProvider>
        </NextThemeProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isPending } = useAuth();
  const location = useLocation();

  if (isPending) {
    return null;
  }

  if (!user?.auth_provider || user.auth_provider === "anonymous") {
    const redirectTo = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?redirectTo=${encodeURIComponent(redirectTo)}`} replace />;
  }

  return children;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { permissions, isPending } = useAuth();

  if (isPending) {
    return null;
  }

  if (!permissions.is_admin) {
    return <Navigate to="/" replace />;
  }

  return children;
}
