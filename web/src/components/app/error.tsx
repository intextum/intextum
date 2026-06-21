import type { FallbackProps } from "react-error-boundary";
import { useEffect } from "react";
import { useLocation } from "react-router";
import { useTranslate } from "@/lib/app-context";
import { CircleAlert, History } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import type { HtmlHTMLAttributes, ErrorInfo } from "react";

export const Error = (props: InternalErrorProps & {}) => {
  const { error, errorInfo, resetErrorBoundary, ...rest } = props;
  const translate = useTranslate();
  const location = useLocation();

  useEffect(() => {
    resetErrorBoundary();
  }, [location.pathname, location.search, resetErrorBoundary]);

  const errorMessage: string =
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string"
      ? (error.message ?? "")
      : typeof error === "string"
        ? error
        : String(error ?? "Unknown error");

  return (
    <div className="flex flex-col items-center md:p-16 gap-5" {...rest}>
      <h1 className="flex items-center text-3xl mt-5 mb-5 gap-3" role="alert">
        <CircleAlert className="w-2em h-2em" />
        {translate("ra.page.error")}
      </h1>
      <div>{translate("ra.message.error")}</div>
      {import.meta.env.DEV && (
        <>
          <Accordion type="multiple" className="mt-1 p-2 bg-secondary w-full lg:w-150">
            <AccordionItem value="error">
              <AccordionTrigger className="py-2">{errorMessage}</AccordionTrigger>
              <AccordionContent className="whitespace-pre-wrap pt-1">
                <pre className="text-xls">{errorInfo?.componentStack}</pre>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </>
      )}
      <div className="mt-8">
        <Button onClick={goBack}>
          <History />
          {translate("ra.action.back")}
        </Button>
      </div>
    </div>
  );
};

interface InternalErrorProps
  extends Omit<HtmlHTMLAttributes<HTMLDivElement>, "title">, FallbackProps {
  className?: string;
  errorInfo?: ErrorInfo;
}

export interface ErrorProps extends Pick<FallbackProps, "error"> {
  errorInfo?: ErrorInfo;
}

function goBack() {
  window.history.go(-1);
}
