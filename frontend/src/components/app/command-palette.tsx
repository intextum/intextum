import { useEffect, useMemo, useState, type ComponentType } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import {
  FileStack,
  FileText,
  Home,
  Keyboard,
  Languages,
  MessageSquare,
  MessageSquarePlus,
  Moon,
  Search,
  Settings,
  Shield,
  Sun,
  Upload,
} from "lucide-react";
import { useNavigate } from "react-router";
import { SHOW_SHORTCUTS_EVENT } from "@/components/app/keyboard-shortcuts-dialog";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useLocaleState, useLocales, useTranslate } from "@/lib/app-context";
import type { ContentItemInfo, ConversationSummary } from "@/dataProvider";
import { getContentItemDisplayName } from "@/lib/content-utils";
import { queryKeys } from "@/lib/query-client";
import { readRecentSearchQueries, subscribeRecentSearchQueries } from "@/lib/recent-searches";

type CommandAction = {
  icon: ComponentType<{ className?: string }>;
  label: string;
  keywords: string;
  value: string;
  onSelect: () => void;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

const isContentItem = (value: unknown): value is ContentItemInfo =>
  isRecord(value) &&
  typeof value.id === "string" &&
  typeof value.path === "string" &&
  typeof value.kind === "string" &&
  (typeof value.display_name === "string" || typeof value.name === "string");

const isConversationSummary = (value: unknown): value is ConversationSummary =>
  isRecord(value) && typeof value.id === "string" && "title" in value && "updated_at" in value;

const collectItems = <T,>(
  value: unknown,
  predicate: (candidate: unknown) => candidate is T,
  keyForItem: (item: T) => string,
  limit: number,
) => {
  const results: T[] = [];
  const seen = new Set<string>();
  const visit = (candidate: unknown, depth: number) => {
    if (results.length >= limit || depth > 5) {
      return;
    }
    if (predicate(candidate)) {
      const key = keyForItem(candidate);
      if (!seen.has(key)) {
        seen.add(key);
        results.push(candidate);
      }
      return;
    }
    if (Array.isArray(candidate)) {
      for (const item of candidate) visit(item, depth + 1);
      return;
    }
    if (isRecord(candidate)) {
      for (const item of Object.values(candidate)) visit(item, depth + 1);
    }
  };
  visit(value, 0);
  return results;
};

export function CommandPalette() {
  const translate = useTranslate();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setTheme } = useTheme();
  const [locale, setLocale] = useLocaleState();
  const locales = useLocales();
  const [open, setOpen] = useState(false);
  const [cachedContentItems, setCachedContentItems] = useState<ContentItemInfo[]>([]);
  const [cachedConversations, setCachedConversations] = useState<ConversationSummary[]>([]);
  const [recentSearchQueries, setRecentSearchQueries] = useState<string[]>([]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const refreshTimer = window.setTimeout(() => {
      const contentItems = queryClient
        .getQueriesData({ queryKey: queryKeys.content.all })
        .flatMap(([, data]) =>
          collectItems(data, isContentItem, (item) => item.id || item.path, 10),
        );
      const conversations = queryClient
        .getQueriesData({ queryKey: queryKeys.conversations.all })
        .flatMap(([, data]) => collectItems(data, isConversationSummary, (item) => item.id, 10));
      setCachedContentItems(contentItems.slice(0, 8));
      setCachedConversations(conversations.slice(0, 8));
      setRecentSearchQueries(readRecentSearchQueries(8));
    }, 0);
    return () => window.clearTimeout(refreshTimer);
  }, [open, queryClient]);

  useEffect(
    () =>
      subscribeRecentSearchQueries(() => {
        if (open) {
          setRecentSearchQueries(readRecentSearchQueries(8));
        }
      }),
    [open],
  );

  const navigationActions = useMemo<CommandAction[]>(
    () => [
      {
        icon: Home,
        label: translate("custom.command.actions.dashboard"),
        keywords: "home overview dashboard",
        value: "nav:dashboard",
        onSelect: () => navigate("/"),
      },
      {
        icon: Upload,
        label: translate("custom.command.actions.upload"),
        keywords: "upload file content",
        value: "nav:upload",
        onSelect: () => navigate("/content?upload=true"),
      },
      {
        icon: Search,
        label: translate("custom.command.actions.search"),
        keywords: "search find",
        value: "nav:search",
        onSelect: () => navigate("/search"),
      },
      {
        icon: MessageSquarePlus,
        label: translate("custom.command.actions.new_chat"),
        keywords: "chat conversation assistant",
        value: "nav:new-chat",
        onSelect: () => navigate("/chat"),
      },
      {
        icon: FileText,
        label: translate("custom.command.actions.content"),
        keywords: "content files documents",
        value: "nav:content",
        onSelect: () => navigate("/content"),
      },
      {
        icon: FileStack,
        label: translate("custom.command.actions.content_enrichment_page"),
        keywords: "content enrichment classes schemas classification extraction catalog",
        value: "nav:content-enrichment",
        onSelect: () => navigate("/admin?tab=content-classes"),
      },
      {
        icon: Settings,
        label: translate("custom.command.actions.settings"),
        keywords: "settings preferences",
        value: "nav:settings",
        onSelect: () => navigate("/settings"),
      },
      {
        icon: Shield,
        label: translate("custom.command.actions.admin"),
        keywords: "admin workers users connectors",
        value: "nav:admin",
        onSelect: () => navigate("/admin"),
      },
    ],
    [navigate, translate],
  );

  const preferenceActions = useMemo<CommandAction[]>(
    () => [
      {
        icon: Sun,
        label: translate("custom.command.actions.theme_light"),
        keywords: "theme light appearance",
        value: "pref:theme-light",
        onSelect: () => setTheme("light"),
      },
      {
        icon: Moon,
        label: translate("custom.command.actions.theme_dark"),
        keywords: "theme dark appearance",
        value: "pref:theme-dark",
        onSelect: () => setTheme("dark"),
      },
      {
        icon: Settings,
        label: translate("custom.command.actions.theme_system"),
        keywords: "theme system appearance",
        value: "pref:theme-system",
        onSelect: () => setTheme("system"),
      },
      ...locales
        .filter((language) => language.locale !== locale)
        .map<CommandAction>((language) => ({
          icon: Languages,
          label: translate("custom.command.actions.language", { language: language.name }),
          keywords: `language locale ${language.name}`,
          value: `pref:language-${language.locale}`,
          onSelect: () => setLocale(language.locale),
        })),
      {
        icon: Keyboard,
        label: translate("custom.command.actions.shortcuts"),
        keywords: "keyboard shortcuts help cheatsheet",
        value: "pref:shortcuts",
        onSelect: () => window.dispatchEvent(new Event(SHOW_SHORTCUTS_EVENT)),
      },
    ],
    [locale, locales, setLocale, setTheme, translate],
  );

  const contentActions = useMemo<CommandAction[]>(
    () =>
      cachedContentItems.map((item) => ({
        icon: FileText,
        label: getContentItemDisplayName(item),
        keywords: `content document file ${item.path}`,
        value: `content:${item.id}`,
        onSelect: () => navigate(`/content/item/${encodeURIComponent(item.id)}`),
      })),
    [cachedContentItems, navigate],
  );

  const conversationActions = useMemo<CommandAction[]>(
    () =>
      cachedConversations.map((conversation) => ({
        icon: MessageSquare,
        label: conversation.title || translate("custom.pages.chat.untitled"),
        keywords: "conversation chat",
        value: `conversation:${conversation.id}`,
        onSelect: () => navigate(`/chat/${conversation.id}`),
      })),
    [cachedConversations, navigate, translate],
  );

  const searchActions = useMemo<CommandAction[]>(
    () =>
      recentSearchQueries.map((query) => ({
        icon: Search,
        label: query,
        keywords: "recent search query",
        value: `search:${query}`,
        onSelect: () => navigate(`/search?q=${encodeURIComponent(query)}`),
      })),
    [navigate, recentSearchQueries],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const runAction = (action: CommandAction) => {
    setOpen(false);
    action.onSelect();
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder={translate("custom.command.placeholder")} />
      <CommandList>
        <CommandEmpty>{translate("custom.command.empty")}</CommandEmpty>
        <CommandGroup heading={translate("custom.command.group_navigation")}>
          {navigationActions.map((action) => {
            const Icon = action.icon;
            return (
              <CommandItem
                key={action.value}
                value={`${action.label} ${action.keywords}`}
                onSelect={() => runAction(action)}
              >
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span>{action.label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>
        {contentActions.length > 0 && (
          <CommandGroup heading={translate("custom.command.group_content")}>
            {contentActions.map((action) => {
              const Icon = action.icon;
              return (
                <CommandItem
                  key={action.value}
                  value={`${action.label} ${action.keywords}`}
                  onSelect={() => runAction(action)}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate">{action.label}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
        {conversationActions.length > 0 && (
          <CommandGroup heading={translate("custom.command.group_conversations")}>
            {conversationActions.map((action) => {
              const Icon = action.icon;
              return (
                <CommandItem
                  key={action.value}
                  value={`${action.label} ${action.keywords}`}
                  onSelect={() => runAction(action)}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate">{action.label}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
        {searchActions.length > 0 && (
          <CommandGroup heading={translate("custom.command.group_recent_searches")}>
            {searchActions.map((action) => {
              const Icon = action.icon;
              return (
                <CommandItem
                  key={action.value}
                  value={`${action.label} ${action.keywords}`}
                  onSelect={() => runAction(action)}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate">{action.label}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
        <CommandGroup heading={translate("custom.command.group_preferences")}>
          {preferenceActions.map((action) => {
            const Icon = action.icon;
            return (
              <CommandItem
                key={action.value}
                value={`${action.label} ${action.keywords}`}
                onSelect={() => runAction(action)}
              >
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span>{action.label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
