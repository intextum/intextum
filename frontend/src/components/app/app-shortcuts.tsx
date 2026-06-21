import { useEffect, useRef } from "react";
import { useNavigate } from "react-router";
import { SHOW_SHORTCUTS_EVENT } from "@/components/app/keyboard-shortcuts-dialog";

const isEditableTarget = (target: EventTarget | null) => {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return Boolean(
    target.closest("input, textarea, select, [contenteditable='true'], [role='textbox']"),
  );
};

const focusSearchInput = () => {
  const input = document.querySelector<HTMLInputElement>(
    [
      "[data-shortcut-search='true']",
      "input[type='search']",
      "input[placeholder*='Search' i]",
      "input[placeholder*='Suchen' i]",
    ].join(", "),
  );
  input?.focus();
  input?.select();
};

export function AppShortcuts() {
  const navigate = useNavigate();
  const pendingGoRef = useRef<number | null>(null);

  useEffect(() => {
    const clearPendingGo = () => {
      if (pendingGoRef.current !== null) {
        window.clearTimeout(pendingGoRef.current);
        pendingGoRef.current = null;
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      if (isEditableTarget(event.target)) {
        return;
      }

      const key = event.key.toLowerCase();

      if (event.key === "?") {
        event.preventDefault();
        clearPendingGo();
        window.dispatchEvent(new Event(SHOW_SHORTCUTS_EVENT));
        return;
      }

      if (event.key === "/") {
        event.preventDefault();
        clearPendingGo();
        focusSearchInput();
        return;
      }

      if (key === "n") {
        event.preventDefault();
        clearPendingGo();
        navigate("/chat");
        return;
      }

      if (pendingGoRef.current !== null) {
        clearPendingGo();
        if (key === "c") {
          event.preventDefault();
          navigate("/content");
          return;
        }
        if (key === "s") {
          event.preventDefault();
          navigate("/search");
          return;
        }
      }

      if (key === "g") {
        event.preventDefault();
        clearPendingGo();
        pendingGoRef.current = window.setTimeout(() => {
          pendingGoRef.current = null;
        }, 1200);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      clearPendingGo();
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [navigate]);

  return null;
}
