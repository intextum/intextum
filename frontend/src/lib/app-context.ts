import { createContext, useCallback, useContext, type ReactNode } from "react";
import { toast } from "@/components/ui/sonner";
import { invalidateContentQueries, invalidateConversationQueries } from "@/lib/query-client";
import {
  type UserIdentity,
  type UserInfo,
  type UserPermissions,
  type LoginParams,
} from "@/authProvider";

export type TranslationMessages = Record<string, unknown>;
export type TranslateOptions = Record<string, unknown> & { _?: string };

export type LocaleInfo = {
  locale: string;
  name: string;
};

export type I18nContextValue = {
  locale: string;
  locales: LocaleInfo[];
  setLocale: (locale: string) => void;
  translate: (key: string, options?: unknown) => string;
};

export type AuthContextValue = {
  user: UserInfo | null;
  identity: UserIdentity;
  permissions: UserPermissions;
  isPending: boolean;
  refreshUser: () => Promise<UserInfo | null>;
  login: (params?: LoginParams, redirectTo?: string) => Promise<void>;
  logout: () => Promise<void>;
};

export type NotificationType = "info" | "success" | "warning" | "error";

export type NotificationOptions = {
  type?: NotificationType;
  messageArgs?: TranslateOptions;
  undoable?: boolean;
};

export const I18nContext = createContext<I18nContextValue | undefined>(undefined);
export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AppProviders");
  }
  return context;
}

export function useLogin() {
  return useAuth().login;
}

export function useLogout() {
  return useAuth().logout;
}

export function useGetIdentity() {
  const { identity, isPending } = useAuth();
  return { identity, data: identity, isPending };
}

export function usePermissions<TPermissions = UserPermissions>() {
  const { permissions, isPending } = useAuth();
  return { permissions: permissions as TPermissions, isPending };
}

export function useTranslate() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useTranslate must be used inside AppProviders");
  }
  return context.translate;
}

export function useLocales() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useLocales must be used inside AppProviders");
  }
  return context.locales;
}

export function useLocaleState(): [string, (locale: string) => void] {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useLocaleState must be used inside AppProviders");
  }
  return [context.locale, context.setLocale];
}

export function useNotify() {
  const translate = useTranslate();
  return useCallback(
    (message: ReactNode, options: NotificationOptions = {}) => {
      const type = options.type ?? "info";
      const text = typeof message === "string" ? translate(message, options.messageArgs) : message;
      toast[type](text);
    },
    [translate],
  );
}

export function useRefresh() {
  return useCallback(() => {
    void invalidateContentQueries();
    void invalidateConversationQueries();
  }, []);
}
