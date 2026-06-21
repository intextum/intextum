import { useCallback, useRef, useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useTranslate } from "@/lib/app-context";
import { ConfirmContext, type ConfirmOptions } from "@/lib/confirm-context";
import { cn } from "@/lib/utils";

type PendingConfirmation = ConfirmOptions & {
  resolve: (confirmed: boolean) => void;
};

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const translate = useTranslate();
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const resolverRef = useRef<((confirmed: boolean) => void) | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    resolverRef.current?.(false);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setPending({ ...options, resolve });
    });
  }, []);

  const settle = useCallback(
    (confirmed: boolean) => {
      pending?.resolve(confirmed);
      resolverRef.current = null;
      setPending(null);
    },
    [pending],
  );

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog
        open={Boolean(pending)}
        onOpenChange={(open) => {
          if (!open && pending) {
            settle(false);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending?.title ?? translate("custom.confirm.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>{pending?.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => settle(false)}>
              {pending?.cancelLabel ?? translate("ra.action.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              className={cn(
                pending?.destructive &&
                  "bg-destructive text-destructive-foreground hover:bg-destructive/90",
              )}
              onClick={() => settle(true)}
            >
              {pending?.confirmLabel ?? translate("custom.confirm.action")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}
