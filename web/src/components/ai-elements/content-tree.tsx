"use client";

import type { HTMLAttributes, ReactNode } from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { ChevronRightIcon, FileIcon, FolderIcon, FolderOpenIcon } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

interface ContentTreeContextType {
  expandedPaths: Set<string>;
  togglePath: (path: string) => void;
  selectedPath?: string;
  onSelect?: (path: string) => void;
}

// Default noop for context default value
// oxlint-disable-next-line eslint(no-empty-function)
const noop = () => {};

const ContentTreeContext = createContext<ContentTreeContextType>({
  // oxlint-disable-next-line eslint-plugin-unicorn(no-new-builtin)
  expandedPaths: new Set(),
  togglePath: noop,
});

export type ContentTreeProps = HTMLAttributes<HTMLDivElement> & {
  expanded?: Set<string>;
  defaultExpanded?: Set<string>;
  selectedPath?: string;
  onSelect?: (path: string) => void;
  onExpandedChange?: (expanded: Set<string>) => void;
};

export const ContentTree = ({
  expanded: controlledExpanded,
  defaultExpanded = new Set(),
  selectedPath,
  onSelect,
  onExpandedChange,
  className,
  children,
  ...props
}: ContentTreeProps) => {
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded);
  const expandedPaths = controlledExpanded ?? internalExpanded;

  const togglePath = useCallback(
    (path: string) => {
      const newExpanded = new Set(expandedPaths);
      if (newExpanded.has(path)) {
        newExpanded.delete(path);
      } else {
        newExpanded.add(path);
      }
      setInternalExpanded(newExpanded);
      onExpandedChange?.(newExpanded);
    },
    [expandedPaths, onExpandedChange],
  );

  const contextValue = useMemo(
    () => ({ expandedPaths, onSelect, selectedPath, togglePath }),
    [expandedPaths, onSelect, selectedPath, togglePath],
  );

  return (
    <ContentTreeContext.Provider value={contextValue}>
      <div
        className={cn("rounded-lg border bg-background font-mono text-sm", className)}
        role="tree"
        {...props}
      >
        <div className="p-2">{children}</div>
      </div>
    </ContentTreeContext.Provider>
  );
};

interface ContentTreeFolderContextType {
  path: string;
  name: string;
  isExpanded: boolean;
}

const ContentTreeFolderContext = createContext<ContentTreeFolderContextType>({
  isExpanded: false,
  name: "",
  path: "",
});

export type ContentTreeFolderProps = HTMLAttributes<HTMLDivElement> & {
  path: string;
  name: string;
};

export const ContentTreeFolder = ({
  path,
  name,
  className,
  children,
  ...props
}: ContentTreeFolderProps) => {
  const { expandedPaths, togglePath, selectedPath, onSelect } = useContext(ContentTreeContext);
  const isExpanded = expandedPaths.has(path);
  const isSelected = selectedPath === path;

  const handleOpenChange = useCallback(() => {
    togglePath(path);
  }, [togglePath, path]);

  const handleSelect = useCallback(() => {
    onSelect?.(path);
  }, [onSelect, path]);

  const folderContextValue = useMemo(() => ({ isExpanded, name, path }), [isExpanded, name, path]);

  return (
    <ContentTreeFolderContext.Provider value={folderContextValue}>
      <Collapsible onOpenChange={handleOpenChange} open={isExpanded}>
        <div className={cn("", className)} role="treeitem" tabIndex={0} {...props}>
          <CollapsibleTrigger asChild>
            <button
              className={cn(
                "flex w-full items-center gap-1 rounded px-2 py-1 text-left transition-colors hover:bg-muted/50",
                isSelected && "bg-muted",
              )}
              onClick={handleSelect}
              type="button"
            >
              <ChevronRightIcon
                className={cn(
                  "size-4 shrink-0 text-muted-foreground transition-transform",
                  isExpanded && "rotate-90",
                )}
              />
              <ContentTreeIcon>
                {isExpanded ? (
                  <FolderOpenIcon className="size-4 text-blue-500" />
                ) : (
                  <FolderIcon className="size-4 text-blue-500" />
                )}
              </ContentTreeIcon>
              <ContentTreeName>{name}</ContentTreeName>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="ml-4 border-l pl-2">{children}</div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </ContentTreeFolderContext.Provider>
  );
};

interface ContentTreeFileContextType {
  path: string;
  name: string;
}

const ContentTreeFileContext = createContext<ContentTreeFileContextType>({
  name: "",
  path: "",
});

export type ContentTreeFileProps = HTMLAttributes<HTMLDivElement> & {
  path: string;
  name: string;
  icon?: ReactNode;
};

export const ContentTreeFile = ({
  path,
  name,
  icon,
  className,
  children,
  ...props
}: ContentTreeFileProps) => {
  const { selectedPath, onSelect } = useContext(ContentTreeContext);
  const isSelected = selectedPath === path;

  const handleClick = useCallback(() => {
    onSelect?.(path);
  }, [onSelect, path]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        onSelect?.(path);
      }
    },
    [onSelect, path],
  );

  const fileContextValue = useMemo(() => ({ name, path }), [name, path]);

  return (
    <ContentTreeFileContext.Provider value={fileContextValue}>
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1 rounded px-2 py-1 transition-colors hover:bg-muted/50",
          isSelected && "bg-muted",
          className,
        )}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        role="treeitem"
        tabIndex={0}
        {...props}
      >
        {children ?? (
          <>
            {/* Spacer for alignment */}
            <span className="size-4" />
            <ContentTreeIcon>
              {icon ?? <FileIcon className="size-4 text-muted-foreground" />}
            </ContentTreeIcon>
            <ContentTreeName>{name}</ContentTreeName>
          </>
        )}
      </div>
    </ContentTreeFileContext.Provider>
  );
};

export type ContentTreeIconProps = HTMLAttributes<HTMLSpanElement>;

export const ContentTreeIcon = ({ className, children, ...props }: ContentTreeIconProps) => (
  <span className={cn("shrink-0", className)} {...props}>
    {children}
  </span>
);

export type ContentTreeNameProps = HTMLAttributes<HTMLSpanElement>;

export const ContentTreeName = ({ className, children, ...props }: ContentTreeNameProps) => (
  <span className={cn("truncate", className)} {...props}>
    {children}
  </span>
);

export type ContentTreeActionsProps = HTMLAttributes<HTMLDivElement>;

const stopPropagation = (e: React.SyntheticEvent) => e.stopPropagation();

export const ContentTreeActions = ({ className, children, ...props }: ContentTreeActionsProps) => (
  // biome-ignore lint/a11y/noNoninteractiveElementInteractions: stopPropagation required for nested interactions
  // biome-ignore lint/a11y/useSemanticElements: fieldset doesn't fit this UI pattern
  <div
    className={cn("ml-auto flex items-center gap-1", className)}
    onClick={stopPropagation}
    onKeyDown={stopPropagation}
    role="group"
    {...props}
  >
    {children}
  </div>
);
