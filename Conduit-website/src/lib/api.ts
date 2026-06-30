import { toast } from "sonner";
import { clearJwt, getJwt, getPartnerToken } from "./auth";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

const MUTATING_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

export class ApiError extends Error {
  status: number;
  code?: string;
  requestId?: string;
  constructor(status: number, message: string, code?: string, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
  partner?: boolean;
  signal?: AbortSignal;
  /** Skip global 401 handling — used on auth/me probe. */
  skipAuthRedirect?: boolean;
}

function buildUrl(path: string, query?: ApiOptions["query"]): string {
  const url = `${BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  });
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

function friendlyMessage(code: string | undefined, fallback: string): string {
  if (!code) return fallback;
  const map: Record<string, string> = {
    insufficient_balance: "Insufficient wallet balance. Add funds to continue.",
    allowance_exceeded: "This app's spending allowance has been reached.",
    model_not_allowed: "This API key isn't allowed to call that model.",
    rate_limit_exceeded: "You're sending requests too quickly. Slow down and retry.",
    payments_unavailable: "Payments are temporarily unavailable. Try again shortly.",
    google_not_configured: "Google sign-in isn't configured on this server.",
    email_taken: "An account with that email already exists.",
    invalid_credentials: "Email or password is incorrect.",
    app_not_active: "That partner app isn't active.",
    invalid_topup: "That top-up amount isn't valid.",
    invalid_settings: "Those wallet settings aren't valid.",
  };
  return map[code] ?? fallback;
}

function onUnauthorized() {
  clearJwt();
  if (typeof window !== "undefined") {
    const here = window.location.pathname + window.location.search;
    if (!here.startsWith("/auth")) {
      window.location.replace(`/auth?redirect=${encodeURIComponent(here)}`);
    }
  }
}

export async function api<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  const jwt = getJwt();
  if (jwt) headers["Authorization"] = `Bearer ${jwt}`;

  if (opts.partner) {
    const token = getPartnerToken();
    if (token) headers["X-Partner-Admin-Token"] = token;
  }

  let body: BodyInit | undefined;
  if (opts.body !== undefined && opts.body !== null) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  if (MUTATING_METHODS.has(method) && typeof crypto !== "undefined" && "randomUUID" in crypto) {
    headers["Idempotency-Key"] = crypto.randomUUID();
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), { method, headers, body, signal: opts.signal });
  } catch (err) {
    const message = "Network error — couldn't reach the Conduit API.";
    if (!opts.signal?.aborted) toast.error(message);
    throw new ApiError(0, message);
  }

  if (res.status === 204) return undefined as T;

  let data: any = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }

  if (!res.ok) {
    const errBlock = data?.detail?.error ?? data?.error ?? {};
    const code: string | undefined = errBlock.code;
    const rawMsg: string = errBlock.message ?? data?.detail ?? res.statusText ?? "Request failed";
    const message = friendlyMessage(code, typeof rawMsg === "string" ? rawMsg : "Request failed");

    if (res.status === 401 && !opts.skipAuthRedirect) {
      onUnauthorized();
    } else if (res.status >= 400 && res.status !== 401) {
      // Surface non-auth errors as toasts unless explicitly handled by caller.
      toast.error(message);
    }

    throw new ApiError(res.status, message, code, errBlock.request_id);
  }

  return data as T;
}
