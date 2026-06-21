import { useEffect } from "react";
import { useTranslate } from "@/lib/app-context";
import {
  Bot,
  Cpu,
  Database,
  type LucideIcon,
  ScanSearch,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Tags,
  WandSparkles,
  Users,
} from "lucide-react";
import { useSearchParams } from "react-router";
import { PageHeader } from "@/components/page/PageHeader";
import { PageShell } from "@/components/page/PageShell";
import {
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { DataConnectorsPage } from "@/pages/DataConnectors";
import { WorkersPage } from "@/pages/Workers";
import { AuthAdminPanel } from "@/pages/admin/AuthAdminPanel";
import { ChatPromptPresetsPanel } from "@/pages/admin/ChatPromptPresetsPanel";
import { AiSettingsPanel } from "@/pages/settings/AiSettingsPanel";

const ADMIN_TABS = [
  "chat",
  "prompt-presets",
  "content-classes",
  "content-enrichment-training",
  "content-enrichment-settings",
  "image-description",
  "data-connectors",
  "auth",
  "workers",
] as const;

type AdminTab = (typeof ADMIN_TABS)[number];

type AdminSection = {
  id: "ai" | "content_enrichment" | "integrations" | "system";
  items: {
    tab: AdminTab;
    icon: LucideIcon;
    labelKey: string;
  }[];
};

const ADMIN_SECTIONS: AdminSection[] = [
  {
    id: "ai",
    items: [
      { tab: "chat", icon: Bot, labelKey: "custom.pages.admin.tabs.chat" },
      {
        tab: "prompt-presets",
        icon: WandSparkles,
        labelKey: "custom.pages.admin.tabs.prompt_presets",
      },
      {
        tab: "image-description",
        icon: ScanSearch,
        labelKey: "custom.pages.admin.tabs.image_description",
      },
    ],
  },
  {
    id: "content_enrichment",
    items: [
      {
        tab: "content-classes",
        icon: Tags,
        labelKey: "custom.pages.admin.tabs.content_classes",
      },
      {
        tab: "content-enrichment-training",
        icon: Sparkles,
        labelKey: "custom.pages.admin.tabs.content_enrichment_training",
      },
      {
        tab: "content-enrichment-settings",
        icon: SlidersHorizontal,
        labelKey: "custom.pages.admin.tabs.content_enrichment_settings",
      },
    ],
  },
  {
    id: "integrations",
    items: [
      {
        tab: "data-connectors",
        icon: Database,
        labelKey: "custom.pages.admin.tabs.data_connectors",
      },
    ],
  },
  {
    id: "system",
    items: [
      { tab: "auth", icon: Users, labelKey: "custom.pages.admin.tabs.auth" },
      { tab: "workers", icon: Cpu, labelKey: "custom.pages.admin.tabs.workers" },
    ],
  },
];

function isAdminTab(value: string | null): value is AdminTab {
  return value !== null && ADMIN_TABS.includes(value as AdminTab);
}

function normalizeAdminTab(value: string | null): AdminTab | null {
  if (value === "ai") {
    return "chat";
  }
  if (value === "content-enrichment") {
    return "content-classes";
  }
  return isAdminTab(value) ? value : null;
}

type ContentEnrichmentRouting = {
  documentClassRouteMode: "list" | "create" | "edit";
  selectedDocumentClassId?: string;
  onOpenDocumentClass: (id: string) => void;
  onCreateDocumentClass: () => void;
  onCloseDocumentClassDetail: (options?: { replace?: boolean }) => void;
};

function renderTabContent(tab: AdminTab, contentEnrichmentRouting: ContentEnrichmentRouting) {
  switch (tab) {
    case "chat":
      return <AiSettingsPanel section="chat" />;
    case "prompt-presets":
      return <ChatPromptPresetsPanel />;
    case "content-classes":
      return (
        <AiSettingsPanel
          section="content_enrichment"
          focus="classes"
          documentClassRouteMode={contentEnrichmentRouting.documentClassRouteMode}
          selectedDocumentClassId={contentEnrichmentRouting.selectedDocumentClassId}
          onOpenDocumentClass={contentEnrichmentRouting.onOpenDocumentClass}
          onCreateDocumentClass={contentEnrichmentRouting.onCreateDocumentClass}
          onCloseDocumentClassDetail={contentEnrichmentRouting.onCloseDocumentClassDetail}
        />
      );
    case "content-enrichment-training":
      return <AiSettingsPanel section="content_enrichment" focus="training" />;
    case "content-enrichment-settings":
      return <AiSettingsPanel section="content_enrichment" focus="settings" />;
    case "image-description":
      return <AiSettingsPanel section="image_description" />;
    case "data-connectors":
      return <DataConnectorsPage embedded />;
    case "auth":
      return <AuthAdminPanel />;
    case "workers":
      return <WorkersPage embedded />;
  }
}

export const AdminPage = () => {
  const translate = useTranslate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const normalizedTab = normalizeAdminTab(requestedTab);
  const activeTab: AdminTab = normalizedTab ?? "chat";

  const classParam = searchParams.get("class");
  const documentClassRouteMode = classParam === "new" ? "create" : classParam ? "edit" : "list";
  const selectedDocumentClassId = classParam && classParam !== "new" ? classParam : undefined;

  const setClassParam = (value: string | null, options?: { replace?: boolean }) => {
    const nextParams = new URLSearchParams(searchParams);
    if (value === null) {
      nextParams.delete("class");
    } else {
      nextParams.set("class", value);
    }
    setSearchParams(nextParams, { replace: options?.replace });
  };

  const contentEnrichmentRouting: ContentEnrichmentRouting = {
    documentClassRouteMode,
    selectedDocumentClassId,
    onOpenDocumentClass: (id) => setClassParam(id),
    onCreateDocumentClass: () => setClassParam("new"),
    onCloseDocumentClassDetail: (options) => setClassParam(null, options),
  };

  useDocumentTitle(translate("custom.pages.admin.title"));

  useEffect(() => {
    if (normalizedTab !== null && requestedTab === normalizedTab) {
      return;
    }

    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", activeTab);
    setSearchParams(nextParams, { replace: true });
  }, [activeTab, normalizedTab, requestedTab, searchParams, setSearchParams]);

  const handleTabChange = (tab: AdminTab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", tab);
    nextParams.delete("class");
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <PageShell>
      <PageHeader
        icon={Shield}
        title={translate("custom.pages.admin.title")}
        description={translate("custom.pages.admin.description")}
      />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="lg:sticky lg:top-4 lg:w-56 lg:shrink-0">
          <nav className="flex flex-col gap-3">
            {ADMIN_SECTIONS.map((section) => (
              <div key={section.id} className="flex flex-col">
                <SidebarGroupLabel>
                  {translate(`custom.pages.admin.sections.${section.id}`)}
                </SidebarGroupLabel>
                <SidebarMenu>
                  {section.items.map(({ tab, icon: Icon, labelKey }) => (
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
              </div>
            ))}
          </nav>
        </aside>

        <div className="min-w-0 flex-1">
          {renderTabContent(activeTab, contentEnrichmentRouting)}
        </div>
      </div>
    </PageShell>
  );
};
