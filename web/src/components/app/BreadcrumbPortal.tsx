import type { ReactNode } from "react";
import { createPortal } from "react-dom";

interface BreadcrumbPortalProps {
  children: ReactNode;
}

/**
 * Portals breadcrumb content into the layout's `#breadcrumb` slot
 * (rendered by `components/app/layout.tsx`).
 */
export const BreadcrumbPortal = ({ children }: BreadcrumbPortalProps) => {
  if (typeof document === "undefined") return null;
  const target = document.getElementById("breadcrumb");
  if (!target) return null;
  return createPortal(children, target);
};
