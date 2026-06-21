import type { ErrorInfo, ReactNode } from "react";
import { Suspense, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "react-error-boundary";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Notification } from "@/components/app/notification";
import { NotificationCenter } from "@/components/app/notification-center";
import { AppShortcuts } from "@/components/app/app-shortcuts";
import { AppSidebar } from "@/components/app/app-sidebar";
import { CommandPalette } from "@/components/app/command-palette";
import { KeyboardShortcutsDialog } from "@/components/app/keyboard-shortcuts-dialog";
import { UserEventBridge } from "@/components/app/user-event-bridge";
import { Error } from "@/components/app/error";
import { Loading } from "@/components/app/loading";
import { reportClientError } from "@/lib/report-client-error";
import { useTranslate } from "@/lib/app-context";

const SIDEBAR_STATE_COOKIE = "sidebar_state";

const readSavedSidebarOpen = () => {
  if (typeof document === "undefined") {
    return null;
  }

  const cookie = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${SIDEBAR_STATE_COOKIE}=`));
  if (!cookie) {
    return null;
  }

  return cookie.split("=")[1] === "true";
};

export const Layout = ({ children }: { children?: ReactNode }) => {
  const location = useLocation();
  const translate = useTranslate();
  const [errorInfo, setErrorInfo] = useState<ErrorInfo | undefined>(undefined);
  const isDashboardRoute = location.pathname === "/";
  const [savedSidebarOpen, setSavedSidebarOpen] = useState<boolean | null>(() =>
    readSavedSidebarOpen(),
  );
  const sidebarOpen = savedSidebarOpen ?? isDashboardRoute;
  const handleError = (error: unknown, info: ErrorInfo) => {
    setErrorInfo(info);
    reportClientError(error, info);
  };

  const handleSidebarOpenChange = (open: boolean) => {
    setSavedSidebarOpen(open);
  };

  return (
    <SidebarProvider open={sidebarOpen} onOpenChange={handleSidebarOpenChange}>
      <AppShortcuts />
      <CommandPalette />
      <KeyboardShortcutsDialog />
      <a
        href="#main-content"
        className="sr-only fixed left-3 top-3 z-[60] rounded-md bg-background px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {translate("custom.layout.skip_to_content")}
      </a>
      <AppSidebar />
      <main
        id="main-content"
        tabIndex={-1}
        className={cn(
          "ml-auto w-full max-w-full",
          "peer-data-[state=collapsed]:w-[calc(100%-var(--sidebar-width-icon)-1rem)]",
          "peer-data-[state=expanded]:w-[calc(100%-var(--sidebar-width))]",
          "sm:transition-[width] sm:duration-200 sm:ease-linear",
          "flex h-svh flex-col",
          "group-data-[scroll-locked=1]/body:h-full",
          "has-[main.fixed-main]:group-data-[scroll-locked=1]/body:h-svh",
        )}
      >
        <header className="flex h-16 md:h-12 shrink-0 items-center gap-2 px-4">
          <SidebarTrigger className="scale-125 sm:scale-100" />
          <div className="flex min-w-0 flex-1 items-center" id="breadcrumb" />
          <NotificationCenter />
        </header>
        <ErrorBoundary
          onError={handleError}
          fallbackRender={({ error, resetErrorBoundary }) => (
            <Error error={error} errorInfo={errorInfo} resetErrorBoundary={resetErrorBoundary} />
          )}
        >
          <Suspense fallback={<Loading />}>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4">
              {children ?? <Outlet />}
            </div>
          </Suspense>
        </ErrorBoundary>
      </main>
      <Notification />
      <UserEventBridge />
    </SidebarProvider>
  );
};
