import { useEffect, useMemo, useState } from "react";
import { Keyboard } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslate } from "@/lib/app-context";

const ShortcutKey = ({ children }: { children: string }) => (
  <kbd className="inline-flex min-w-6 items-center justify-center rounded border bg-muted px-1.5 py-0.5 font-mono text-[11px] font-medium text-muted-foreground shadow-sm">
    {children}
  </kbd>
);

export const SHOW_SHORTCUTS_EVENT = "app:show-keyboard-shortcuts";

export function KeyboardShortcutsDialog() {
  const translate = useTranslate();
  const [open, setOpen] = useState(false);
  const shortcuts = useMemo(
    () => [
      {
        keys: ["⌘/Ctrl", "K"],
        label: translate("custom.shortcuts.items.command_palette"),
      },
      {
        keys: ["/"],
        label: translate("custom.shortcuts.items.focus_search"),
      },
      {
        keys: ["N"],
        label: translate("custom.shortcuts.items.new_chat"),
      },
      {
        keys: ["G", "C"],
        label: translate("custom.shortcuts.items.go_content"),
      },
      {
        keys: ["G", "S"],
        label: translate("custom.shortcuts.items.go_search"),
      },
      {
        keys: ["?"],
        label: translate("custom.shortcuts.items.show_shortcuts"),
      },
    ],
    [translate],
  );

  useEffect(() => {
    const openShortcuts = () => setOpen(true);
    window.addEventListener(SHOW_SHORTCUTS_EVENT, openShortcuts);
    return () => window.removeEventListener(SHOW_SHORTCUTS_EVENT, openShortcuts);
  }, []);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="h-4 w-4" />
            {translate("custom.shortcuts.title")}
          </DialogTitle>
          <DialogDescription>{translate("custom.shortcuts.description")}</DialogDescription>
        </DialogHeader>
        <div className="divide-y">
          {shortcuts.map((shortcut) => (
            <div key={shortcut.label} className="flex items-center justify-between gap-4 py-2.5">
              <span className="text-sm">{shortcut.label}</span>
              <span className="flex shrink-0 items-center gap-1">
                {shortcut.keys.map((key) => (
                  <ShortcutKey key={key}>{key}</ShortcutKey>
                ))}
              </span>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
