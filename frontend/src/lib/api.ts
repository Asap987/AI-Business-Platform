import { API_BASE_URL, API_PREFIX, API_TIMEOUT_MS } from "@/lib/config";

/**
 * Central API client. All backend communication goes through apiRequest().
 *
 * Session handling: the backend is expected to keep the session in an
 * httpOnly cookie, so the browser sends it automatically (credentials:
 * "include") and no token is ever readable by, or stored in, frontend code.
 *
 * Tenant handling: the backend decides the business from the session. The
 * optional X-Business-Id header is sent only after a user with access to
 * several businesses switches business, and the backend must verify it.
 * The frontend never relies on this header for security.
 */

export type ApiErrorKind =
  | "network"
  | "timeout"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "validation"
  | "server"
  | "unknown";

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly code?: string;
  /** Field name -> message, populated for 422 responses. */
  readonly fieldErrors: Record<string, string>;

  constructor(init: {
    status: number;
    kind: ApiErrorKind;
    message: string;
    code?: string;
    fieldErrors?: Record<string, string>;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.kind = init.kind;
    this.code = init.code;
    this.fieldErrors = init.fieldErrors ?? {};
  }
}

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;
let activeBusinessId: string | null = null;

/** Called by AuthProvider so an expired session is handled in one place. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

/** Called by AuthProvider when the user switches business. */
export function setApiBusinessId(id: string | null): void {
  activeBusinessId = id;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  timeoutMs?: number;
  /**
   * Set for calls where a 401 is an expected answer (login, the initial
   * session check) so it does not trigger the "session expired" flow.
   */
  skipUnauthorizedHandler?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${API_BASE_URL}${API_PREFIX}${normalized}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

const DEFAULT_MESSAGES: Record<ApiErrorKind, string> = {
  network: "We couldn't reach the server. Check your connection and try again.",
  timeout: "The server took too long to respond. Please try again.",
  unauthorized: "Your session has expired. Please sign in again.",
  forbidden: "You don't have permission to view this.",
  not_found: "This resource isn't available yet.",
  validation: "Some of the information you entered isn't valid.",
  server: "Something went wrong on our side. Please try again shortly.",
  unknown: "Something unexpected happened. Please try again.",
};

function kindFromStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 422 || status === 400) return "validation";
  if (status >= 500) return "server";
  return "unknown";
}

interface ParsedErrorBody {
  message?: string;
  code?: string;
  fieldErrors: Record<string, string>;
}

/** Understands FastAPI-style {detail: ...} bodies and {message}/{error} bodies. */
function parseErrorBody(body: unknown): ParsedErrorBody {
  const result: ParsedErrorBody = { fieldErrors: {} };
  if (!body || typeof body !== "object") return result;
  const record = body as Record<string, unknown>;

  const detail = record.detail;
  if (typeof detail === "string") {
    result.message = detail;
  } else if (Array.isArray(detail)) {
    const messages: string[] = [];
    for (const entry of detail) {
      if (!entry || typeof entry !== "object") continue;
      const item = entry as { loc?: unknown; msg?: unknown };
      const msg = typeof item.msg === "string" ? item.msg : null;
      if (!msg) continue;
      messages.push(msg);
      if (Array.isArray(item.loc)) {
        const field = [...item.loc].reverse().find((part) => typeof part === "string");
        if (typeof field === "string" && field !== "body" && !(field in result.fieldErrors)) {
          result.fieldErrors[field] = msg;
        }
      }
    }
    if (messages.length > 0) result.message = messages[0];
  }

  if (!result.message && typeof record.message === "string") {
    result.message = record.message;
  }
  if (record.error && typeof record.error === "object") {
    const err = record.error as { message?: unknown; code?: unknown };
    if (!result.message && typeof err.message === "string") result.message = err.message;
    if (typeof err.code === "string") result.code = err.code;
  }
  if (!result.code && typeof record.code === "string") result.code = record.code;

  return result;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    query,
    signal,
    timeoutMs = API_TIMEOUT_MS,
    skipUnauthorizedHandler = false,
  } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const onExternalAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (activeBusinessId) headers["X-Business-Id"] = activeBusinessId;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (cause) {
    if (signal?.aborted && !timedOut) {
      // The caller cancelled (e.g. the component unmounted); not an error to show.
      throw new DOMException("Request cancelled", "AbortError");
    }
    if (timedOut) {
      throw new ApiError({ status: 0, kind: "timeout", message: DEFAULT_MESSAGES.timeout });
    }
    void cause;
    throw new ApiError({ status: 0, kind: "network", message: DEFAULT_MESSAGES.network });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }

  if (response.ok) {
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError({
        status: response.status,
        kind: "unknown",
        message: "The server sent a response we couldn't read.",
      });
    }
  }

  let parsed: ParsedErrorBody = { fieldErrors: {} };
  try {
    parsed = parseErrorBody(await response.json());
  } catch {
    // Non-JSON error body; fall back to defaults below.
  }

  const kind = kindFromStatus(response.status);
  const error = new ApiError({
    status: response.status,
    kind,
    message: parsed.message ?? DEFAULT_MESSAGES[kind],
    code: parsed.code,
    fieldErrors: parsed.fieldErrors,
  });

  if (kind === "unauthorized" && !skipUnauthorizedHandler) {
    unauthorizedHandler?.();
  }

  throw error;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "DELETE" }),
};

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
