import { useEffect } from "react";

/**
 * Sets the browser tab title for the current page.
 */
export function useDocumentTitle(pageTitle?: string) {
  useEffect(() => {
    const trimmed = pageTitle?.trim();
    if (!trimmed) {
      return;
    }

    document.title = trimmed;
  }, [pageTitle]);
}
