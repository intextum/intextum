import { getAuthConfig } from "../authConfig.ts";

export const apiUrl = "/api";

type HttpClientOptions = RequestInit;

type HttpError = Error & {
  status?: number;
  body?: string;
  json?: unknown;
};

async function fetchJson<T = never>(url: string, options: HttpClientOptions = {}) {
  const response = await fetch(url, options);
  const body = await response.text();
  let json: unknown;
  try {
    json = body ? JSON.parse(body) : undefined;
  } catch {
    json = undefined;
  }

  if (!response.ok) {
    const message =
      json && typeof json === "object" && "detail" in json
        ? String((json as { detail?: unknown }).detail ?? response.statusText)
        : response.statusText;
    const error = new Error(message) as HttpError;
    error.status = response.status;
    error.body = body;
    error.json = json;
    throw error;
  }

  return {
    status: response.status,
    headers: response.headers,
    body,
    json: json as T,
  };
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const cookie = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : null;
}

const withAuthRequestOptions = async (options: HttpClientOptions = {}): Promise<RequestInit> => {
  const authConfig = await getAuthConfig();
  const headers = new Headers(options.headers ?? {});
  const method = (options.method || "GET").toUpperCase();
  if (typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = readCookie(authConfig.csrf_cookie_name);
    if (csrfToken) {
      headers.set(authConfig.csrf_header_name, csrfToken);
    }
  }

  return {
    ...options,
    headers,
    credentials: "include",
  };
};

export const httpFetch = async (url: string, options: HttpClientOptions = {}) => {
  return fetch(url, await withAuthRequestOptions(options));
};

export const httpClient = async <T = never>(url: string, options: HttpClientOptions = {}) => {
  return fetchJson<T>(url, await withAuthRequestOptions(options));
};
