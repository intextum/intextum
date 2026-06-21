import type { ErrorInfo } from "react";
import { httpFetch } from "@/api/client";

export type ClientErrorContext = {
  routeName?: string;
};

const truncate = (value: string | null | undefined, maxLength: number): string | undefined => {
  if (!value) {
    return undefined;
  }
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
};

const errorMessage = (error: unknown): string => {
  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return error.message;
  }
  return typeof error === "string" ? error : String(error ?? "Unknown error");
};

const errorName = (error: unknown): string | undefined => {
  if (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    typeof error.name === "string"
  ) {
    return error.name;
  }
  return undefined;
};

const errorStack = (error: unknown): string | undefined => {
  if (
    typeof error === "object" &&
    error !== null &&
    "stack" in error &&
    typeof error.stack === "string"
  ) {
    return error.stack;
  }
  return undefined;
};

export const reportClientError = (
  error: unknown,
  errorInfo?: ErrorInfo,
  context?: ClientErrorContext,
) => {
  if (import.meta.env.DEV) {
    console.error("Client error", error, errorInfo, context);
  }

  if (typeof window === "undefined") {
    return;
  }

  const payload = {
    message: truncate(errorMessage(error), 2000) ?? "Unknown error",
    name: truncate(errorName(error), 200),
    stack: truncate(errorStack(error), 12000),
    component_stack: truncate(errorInfo?.componentStack, 12000),
    route_name: truncate(context?.routeName, 200),
    href: truncate(window.location.href, 2000),
    user_agent: truncate(window.navigator.userAgent, 1000),
  };

  void httpFetch("/api/client-errors", {
    method: "POST",
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {
    // Reporting must never create a second user-visible failure.
  });
};
