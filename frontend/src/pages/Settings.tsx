import { useEffect, useState } from "react";
import { usePermissions, useTranslate } from "@/lib/app-context";
import { useSearchParams } from "react-router";
import {
  Settings,
  MessageSquareWarning,
  Bell,
  KeyRound,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getAuthConfig } from "@/authConfig";
import type { UserPermissions } from "@/authProvider";
import { ChatDataSettingsPanel } from "@/pages/settings/ChatDataSettingsPanel";
import { LocalPasswordSettingsPanel } from "@/pages/settings/LocalPasswordSettingsPanel";
import { NotificationSettingsPanel } from "@/pages/settings/NotificationSettingsPanel";
import { UserPreferencesSettingsPanel } from "@/pages/settings/UserPreferencesSettingsPanel";

const SETTINGS_TABS = ["preferences", "notifications", "chat-data", "auth"] as const;

type SettingsTab = (typeof SETTINGS_TABS)[number];

function isSettingsTab(value: string | null): value is SettingsTab {
  return value !== null && SETTINGS_TABS.includes(value as SettingsTab);
}

/**
 * Settings page for user-scoped chat data management.
 */
export const SettingsPage = () => {
  const translate = useTranslate();
  const { permissions, isPending: permissionsPending } = usePermissions<UserPermissions>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [authConfig, setAuthConfig] = useState<{ local_enabled: boolean } | null>(null);
  const requestedTab = searchParams.get("tab");
  const showAuthTab = authConfig?.local_enabled && permissions?.auth_provider === "local";
  const authVisibilityPending = authConfig === null || permissionsPending;
  const renderAuthTab = showAuthTab || (requestedTab === "auth" && authVisibilityPending);
  const activeTab: SettingsTab =
    isSettingsTab(requestedTab) && (requestedTab !== "auth" || showAuthTab || authVisibilityPending)
      ? requestedTab
      : "preferences";

  useDocumentTitle(translate("custom.pages.settings.title"));

  useEffect(() => {
    void getAuthConfig().then(setAuthConfig);
  }, []);

  useEffect(() => {
    if (requestedTab === activeTab) {
      return;
    }
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", activeTab);
    setSearchParams(nextParams, { replace: true });
  }, [activeTab, requestedTab, searchParams, setSearchParams]);

  const handleTabChange = (tab: SettingsTab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", tab);
    setSearchParams(nextParams, { replace: true });
  };

  const navItems: { tab: SettingsTab; icon: LucideIcon; labelKey: string }[] = [
    {
      tab: "preferences",
      icon: UserRound,
      labelKey: "custom.pages.settings.tabs.preferences",
    },
    {
      tab: "notifications",
      icon: Bell,
      labelKey: "custom.pages.settings.tabs.notifications",
    },
    {
      tab: "chat-data",
      icon: MessageSquareWarning,
      labelKey: "custom.pages.settings.tabs.chat_data",
    },
  ];
  if (renderAuthTab) {
    navItems.push({
      tab: "auth",
      icon: KeyRound,
      labelKey: "custom.pages.settings.tabs.auth",
    });
  }

  const renderActivePanel = () => {
    if (activeTab === "preferences") {
      return <UserPreferencesSettingsPanel />;
    }
    if (activeTab === "notifications") {
      return <NotificationSettingsPanel />;
    }
    if (activeTab === "chat-data") {
      return <ChatDataSettingsPanel />;
    }
    if (activeTab === "auth") {
      return showAuthTab ? (
        <LocalPasswordSettingsPanel />
      ) : (
        <div className="text-sm text-muted-foreground">{translate("ra.message.loading")}</div>
      );
    }
    return null;
  };

  return (
    <PageShell>
      <PageHeader
        icon={Settings}
        title={translate("custom.pages.settings.title")}
        description={translate("custom.pages.settings.description")}
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="lg:sticky lg:top-4 lg:w-56 lg:shrink-0">
          <nav>
            <SidebarMenu>
              {navItems.map(({ tab, icon: Icon, labelKey }) => (
                <SidebarMenuItem key={tab}>
                  <SidebarMenuButton
                    isActive={activeTab === tab}
                    onClick={() => handleTabChange(tab)}
                  >
                    <Icon />
                    <span>{translate(labelKey)}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </nav>
        </aside>

        <div className="min-w-0 flex-1">{renderActivePanel()}</div>
      </div>
    </PageShell>
  );
};
