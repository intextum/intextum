import type { ToasterProps } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/sonner";

export const Notification = (props: ToasterProps) => {
  return <Toaster richColors closeButton position="bottom-center" {...props} />;
};
