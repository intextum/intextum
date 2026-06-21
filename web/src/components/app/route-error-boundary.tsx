import { useState, type ErrorInfo, type ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { Error } from "@/components/app/error";
import { reportClientError } from "@/lib/report-client-error";

type RouteErrorBoundaryProps = {
  children: ReactNode;
  routeName: string;
};

export function RouteErrorBoundary({ children, routeName }: RouteErrorBoundaryProps) {
  const [errorInfo, setErrorInfo] = useState<ErrorInfo | undefined>(undefined);

  const handleError = (error: unknown, info: ErrorInfo) => {
    setErrorInfo(info);
    reportClientError(error, info, { routeName });
  };

  return (
    <ErrorBoundary
      onError={handleError}
      fallbackRender={({ error, resetErrorBoundary }) => (
        <Error error={error} errorInfo={errorInfo} resetErrorBoundary={resetErrorBoundary} />
      )}
    >
      {children}
    </ErrorBoundary>
  );
}
