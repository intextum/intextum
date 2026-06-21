import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useMatch, useNavigate } from "react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BRAND_SUBTITLE, BRAND_TITLE } from "@/config/branding";
import {
  Files,
  Search,
  MessageSquare,
  Trash2,
  Pencil,
  Library,
  MoreVertical,
  Shield,
  LoaderCircle,
  CircleDashed,
} from "lucide-react";
import { conversationsApi, type ConversationSummary } from "@/dataProvider";
import type { UserPermissions } from "@/authProvider";
import { useNotify, usePermissions, useTranslate } from "@/lib/app-context";
import { useConfirm } from "@/lib/confirm-context";
import { invalidateConversationQueries, queryKeys } from "@/lib/query-client";
import { NavUser } from "@/components/app/nav-user";

const CONVERSATIONS_PAGE_SIZE = 20;

export function AppSidebar() {
  const translate = useTranslate();
  const notify = useNotify();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const { permissions, isPending: isPermissionsPending } = usePermissions<UserPermissions>();
  const { openMobile, setOpenMobile } = useSidebar();
  const handleClick = () => {
    if (openMobile) {
      setOpenMobile(false);
    }
  };

  // Chat history state
  const chatHistoryViewportRef = useRef<HTMLDivElement | null>(null);

  // Re-fetch when the URL changes to a chat route (catches new conversation creation)
  const chatMatch = useMatch({ path: "/chat/:id", end: false });
  const chatRootMatch = useMatch({ path: "/chat", end: true });
  const chatConversationId = chatMatch?.params?.id ?? null;
  const isChatRoot = !!chatRootMatch;

  const conversationsQuery = useInfiniteQuery({
    queryKey: queryKeys.conversations.list(CONVERSATIONS_PAGE_SIZE, 0),
    initialPageParam: 0,
    queryFn: ({ pageParam }) => conversationsApi.list(CONVERSATIONS_PAGE_SIZE, pageParam),
    getNextPageParam: (lastPage, allPages) => {
      const nextOffset = allPages.reduce((total, page) => total + page.conversations.length, 0);
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
  });
  const {
    data: conversationsData,
    fetchNextPage,
    hasNextPage: hasMoreConversations,
    isFetchingNextPage,
    isLoading: isLoadingConversations,
    refetch: refetchConversations,
  } = conversationsQuery;

  const conversations = useMemo(() => {
    const seen = new Set<string>();
    return (
      conversationsData?.pages
        .flatMap((page) => page.conversations)
        .filter((conversation) => {
          if (seen.has(conversation.id)) {
            return false;
          }
          seen.add(conversation.id);
          return true;
        }) ?? []
    );
  }, [conversationsData]);

  useEffect(() => {
    void refetchConversations();
  }, [chatConversationId, isChatRoot, refetchConversations]);

  const loadMoreConversations = useCallback(async () => {
    if (isLoadingConversations || isFetchingNextPage || !hasMoreConversations) {
      return;
    }
    await fetchNextPage();
  }, [fetchNextPage, hasMoreConversations, isFetchingNextPage, isLoadingConversations]);

  const handleConversationHistoryScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const viewport = event.currentTarget;
      const remaining = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
      if (remaining <= 96) {
        void loadMoreConversations();
      }
    },
    [loadMoreConversations],
  );

  useEffect(() => {
    if (!hasMoreConversations || isLoadingConversations || isFetchingNextPage) {
      return;
    }

    const viewport = chatHistoryViewportRef.current;
    if (!viewport) {
      return;
    }

    if (viewport.scrollHeight <= viewport.clientHeight + 1) {
      void loadMoreConversations();
    }
  }, [
    conversations.length,
    hasMoreConversations,
    isFetchingNextPage,
    isLoadingConversations,
    loadMoreConversations,
  ]);

  const navigate = useNavigate();

  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const confirmed = await confirm({
      title: translate("custom.pages.chat.delete_conversation"),
      description: translate("custom.pages.chat.delete_confirm"),
      confirmLabel: translate("custom.confirm.delete"),
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await conversationsApi.delete(id);
      await invalidateConversationQueries();
      notify(translate("custom.pages.chat.deleted"), { type: "info" });
      // If the deleted conversation is the one currently viewed, navigate to new chat
      if (chatConversationId === id) {
        navigate("/chat");
      }
    } catch {
      notify(translate("custom.failed_action"), { type: "error" });
    }
  };

  // Edit title state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingConversation, setEditingConversation] = useState<ConversationSummary | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const handleEditTitle = (conv: ConversationSummary, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingConversation(conv);
    setEditTitle(conv.title || "");
    setEditDialogOpen(true);
  };

  const handleSaveTitle = async () => {
    if (!editingConversation) return;
    try {
      const updated = await conversationsApi.update(editingConversation.id, {
        title: editTitle.trim(),
      });
      queryClient.setQueriesData({ queryKey: queryKeys.conversations.all }, (current: unknown) => {
        if (!current || typeof current !== "object" || !("pages" in current)) {
          return current;
        }
        const data = current as {
          pages: Array<{ conversations: ConversationSummary[]; total: number }>;
          pageParams: unknown[];
        };
        return {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            conversations: page.conversations.map((conversation) =>
              conversation.id === updated.id
                ? { ...conversation, title: updated.title }
                : conversation,
            ),
          })),
        };
      });
      setEditDialogOpen(false);
      setEditingConversation(null);
    } catch {
      notify(translate("custom.failed_action"), { type: "error" });
    }
  };

  const adminMatch = useMatch({ path: "/admin", end: false });
  const contentMatch = useMatch({ path: "/content", end: false });
  const searchMatch = useMatch({ path: "/search", end: false });
  const showAdminGroup = !isPermissionsPending && (permissions?.is_admin ?? false);

  return (
    <>
      <Sidebar variant="floating" collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild size="lg">
                <Link to="/">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <Library className="size-4" />
                  </div>
                  <div className="grid min-w-0 flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold text-base">{BRAND_TITLE}</span>
                    <span className="truncate text-xs">{BRAND_SUBTITLE}</span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup className="flex min-h-0 flex-1 flex-col">
            <SidebarGroupLabel>{translate("custom.groups.documents")}</SidebarGroupLabel>
            <SidebarGroupContent className="flex min-h-0 flex-1 flex-col">
              <SidebarMenu className="min-h-0 flex-1">
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={!!contentMatch}>
                    <Link to="/content" onClick={handleClick}>
                      <Files />
                      <span>{translate("resources.content.name")}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={!!searchMatch}>
                    <Link to="/search" onClick={handleClick}>
                      <Search />
                      <span>{translate("custom.pages.search.title")}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem className="flex min-h-0 flex-1 flex-col">
                  <SidebarMenuButton asChild isActive={!!chatRootMatch}>
                    <Link to="/chat" onClick={handleClick}>
                      <MessageSquare />
                      <span>{translate("custom.pages.chat.new_chat")}</span>
                    </Link>
                  </SidebarMenuButton>
                  <div
                    ref={chatHistoryViewportRef}
                    className="mt-1 min-h-0 flex-1 overflow-y-auto"
                    onScroll={handleConversationHistoryScroll}
                  >
                    <SidebarMenuSub>
                      {conversations.map((conv) => (
                        <ConversationMenuItem
                          key={conv.id}
                          conversation={conv}
                          onClick={handleClick}
                          onDelete={handleDeleteConversation}
                          onEdit={handleEditTitle}
                          translate={translate}
                        />
                      ))}
                    </SidebarMenuSub>
                    {(conversationsQuery.isLoading || conversationsQuery.isFetchingNextPage) && (
                      <div className="px-2 py-1.5 space-y-1.5">
                        <Skeleton className="h-6 w-full" />
                        <Skeleton className="h-6 w-[85%]" />
                      </div>
                    )}
                  </div>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          {showAdminGroup && (
            <SidebarGroup>
              <SidebarGroupLabel>{translate("custom.groups.admin")}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton asChild isActive={!!adminMatch}>
                      <Link to="/admin?tab=ai" onClick={handleClick}>
                        <Shield />
                        <span>{translate("custom.pages.admin.title")}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <NavUser />
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      {/* Edit title dialog - outside Sidebar to avoid transform context breaking fixed positioning */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{translate("custom.pages.chat.edit_title_dialog.title")}</DialogTitle>
          </DialogHeader>
          <Input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveTitle();
            }}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              {translate("ra.action.cancel")}
            </Button>
            <Button onClick={handleSaveTitle} disabled={!editTitle.trim()}>
              {translate("custom.pages.chat.edit_title_dialog.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

const ConversationMenuItem = ({
  conversation,
  onClick,
  onDelete,
  onEdit,
  translate,
}: {
  conversation: ConversationSummary;
  onClick?: () => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
  onEdit: (conv: ConversationSummary, e: React.MouseEvent) => void;
  translate: (key: string, options?: Record<string, unknown>) => string;
}) => {
  const match = useMatch({ path: `/chat/${conversation.id}`, end: true });
  const title = conversation.title || translate("custom.pages.chat.untitled");
  const activeRunStatus = conversation.active_run_status;
  const activeRunLabel =
    activeRunStatus === "RUNNING"
      ? translate("custom.pages.chat.run_status.running")
      : activeRunStatus === "PENDING"
        ? translate("custom.pages.chat.run_status.pending")
        : null;

  return (
    <SidebarMenuSubItem className="group/menu-item relative">
      <SidebarMenuSubButton asChild isActive={!!match}>
        <Link to={`/chat/${conversation.id}`} onClick={onClick} title={title} className="pr-10">
          <span className="flex min-w-0 items-center gap-2">
            {activeRunStatus === "RUNNING" ? (
              <span title={activeRunLabel ?? undefined}>
                <LoaderCircle className="size-3.5 shrink-0 animate-spin text-primary" />
              </span>
            ) : activeRunStatus === "PENDING" ? (
              <span title={activeRunLabel ?? undefined}>
                <CircleDashed className="size-3.5 shrink-0 text-muted-foreground" />
              </span>
            ) : null}
            <span className="truncate">{title}</span>
          </span>
        </Link>
      </SidebarMenuSubButton>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuAction
            className="opacity-100 transition-opacity md:opacity-0 md:group-hover/menu-item:opacity-100 md:group-focus-within/menu-item:opacity-100 data-[state=open]:opacity-100"
            showOnHover
          >
            <MoreVertical className="size-4" />
            <span className="sr-only">Actions</span>
          </SidebarMenuAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start">
          <DropdownMenuItem onClick={(e) => onEdit(conversation, e)}>
            <Pencil className="mr-2 size-4 text-muted-foreground" />
            <span>{translate("custom.pages.chat.edit_title")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={(e) => onDelete(conversation.id, e)}>
            <Trash2 className="mr-2 size-4" />
            <span>{translate("custom.pages.chat.delete_conversation")}</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuSubItem>
  );
};
