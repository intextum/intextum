/**
 * Main application component.
 */
import { Suspense, lazy, type ComponentType, type LazyExoticComponent } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router";
import { Layout } from "@/components/app/layout";
import { LoginPage } from "@/components/app/login-page";
import { RouteErrorBoundary } from "@/components/app/route-error-boundary";
import { AppProviders, RequireAdmin, RequireAuth } from "@/lib/app-providers";
import { useTranslate } from "@/lib/app-context";

const ContentList = lazy(async () => ({
  default: (await import("./pages/Content")).ContentList,
}));
const ContentItemPage = lazy(async () => ({
  default: (await import("./pages/ContentItem")).ContentItemPage,
}));
const ContentItemActivityPage = lazy(async () => ({
  default: (await import("./pages/ContentItemActivity")).ContentItemActivityPage,
}));
const SearchPage = lazy(async () => ({
  default: (await import("./pages/Search")).SearchPage,
}));
const ChatPage = lazy(async () => ({
  default: (await import("./pages/Chat")).ChatPage,
}));
const SettingsPage = lazy(async () => ({
  default: (await import("./pages/Settings")).SettingsPage,
}));
const AdminPage = lazy(async () => ({
  default: (await import("./pages/Admin")).AdminPage,
}));
const EnrichmentClassRedirect = () => {
  const { classId } = useParams<{ classId?: string }>();
  const target = classId
    ? `/admin?tab=content-classes&class=${encodeURIComponent(classId)}`
    : "/admin?tab=content-classes";
  return <Navigate to={target} replace />;
};
const DashboardPage = lazy(async () => ({
  default: (await import("./pages/Dashboard")).DashboardPage,
}));

function PageLoadingFallback() {
  const translate = useTranslate();
  return (
    <div className="flex h-full min-h-[16rem] items-center justify-center p-6 text-sm text-muted-foreground">
      {translate("ra.message.loading")}
    </div>
  );
}

function makeSuspendedPage<P extends object>(
  LazyPage: LazyExoticComponent<ComponentType<P>>,
  routeName: string,
) {
  return function SuspendedPage(props: P) {
    return (
      <RouteErrorBoundary routeName={routeName}>
        <Suspense fallback={<PageLoadingFallback />}>
          <LazyPage {...props} />
        </Suspense>
      </RouteErrorBoundary>
    );
  };
}

const ContentListPage = makeSuspendedPage(ContentList, "content-list");
const ContentItemRoutePage = makeSuspendedPage(ContentItemPage, "content-item");
const ContentItemActivityRoutePage = makeSuspendedPage(
  ContentItemActivityPage,
  "content-item-activity",
);
const SearchRoutePage = makeSuspendedPage(SearchPage, "search");
const ChatRoutePage = makeSuspendedPage(ChatPage, "chat");
const SettingsRoutePage = makeSuspendedPage(SettingsPage, "settings");
const AdminRoutePage = makeSuspendedPage(AdminPage, "admin");
const DashboardRoutePage = makeSuspendedPage(DashboardPage, "dashboard");

const AppRoutes = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route
      element={
        <RequireAuth>
          <Layout />
        </RequireAuth>
      }
    >
      <Route index element={<DashboardRoutePage />} />
      <Route path="/content" element={<ContentListPage />} />
      <Route path="/content/item/:id/activity" element={<ContentItemActivityRoutePage />} />
      <Route path="/content/item/:id" element={<ContentItemRoutePage />} />
      <Route path="/review" element={<Navigate to="/content" replace />} />
      <Route path="/search" element={<SearchRoutePage />} />
      <Route path="/settings" element={<SettingsRoutePage />} />
      <Route
        path="/admin"
        element={
          <RequireAdmin>
            <AdminRoutePage />
          </RequireAdmin>
        }
      />
      <Route
        path="/content/enrichment"
        element={<Navigate to="/admin?tab=content-classes" replace />}
      />
      <Route
        path="/content/enrichment/classes/new"
        element={<Navigate to="/admin?tab=content-classes&class=new" replace />}
      />
      <Route path="/content/enrichment/classes/:classId" element={<EnrichmentClassRedirect />} />
      <Route
        path="/content-enrichment/*"
        element={<Navigate to="/admin?tab=content-classes" replace />}
      />
      <Route
        path="/workers"
        element={
          <RequireAdmin>
            <Navigate to="/admin?tab=workers" replace />
          </RequireAdmin>
        }
      />
      <Route
        path="/data-connectors"
        element={
          <RequireAdmin>
            <Navigate to="/admin?tab=data-connectors" replace />
          </RequireAdmin>
        }
      />
      <Route path="/chat" element={<ChatRoutePage />} />
      <Route path="/chat/:conversationId" element={<ChatRoutePage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
);

const App = () => (
  <BrowserRouter>
    <AppProviders>
      <AppRoutes />
    </AppProviders>
  </BrowserRouter>
);

export default App;
