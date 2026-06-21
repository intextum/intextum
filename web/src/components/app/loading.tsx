import { useEffect, useState } from "react";
import { useTranslate } from "@/lib/app-context";
import { Spinner } from "@/components/ui/spinner";

export const Loading = (props: LoadingProps) => {
  const {
    loadingPrimary = "ra.page.loading",
    loadingSecondary = "ra.message.loading",
    delay = 1000,
    ...rest
  } = props;
  const translate = useTranslate();
  const [delayHasPassed, setDelayHasPassed] = useState(false);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDelayHasPassed(true), delay);
    return () => window.clearTimeout(timeout);
  }, [delay]);

  return delayHasPassed ? (
    <div className="flex flex-col justify-center items-center h-full" {...rest}>
      <div className="text-center font-sans color-muted pt-1 pb-1">
        <Spinner className="size-12 text-primary" />
        <h5 className="mt-3 text-2xl text-secondary-foreground">{translate(loadingPrimary)}</h5>
        <p className="text-primary">{translate(loadingSecondary)}</p>
      </div>
    </div>
  ) : null;
};

export interface LoadingProps {
  loadingPrimary?: string;
  loadingSecondary?: string;
  delay?: number;
}
