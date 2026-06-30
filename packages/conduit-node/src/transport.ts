import {
  ConduitError,
  ForbiddenError,
  NetworkError,
  PaymentRequiredError,
  RateLimitError,
  ServerError,
  TimeoutError,
  UnauthorizedError,
} from './errors.js';
import { CLIENT_HEADER, USER_AGENT } from './version.js';
import type { FetchLike } from './types.js';

interface BackendErrorEnvelope {
  error: { code: string; message: string; request_id?: string };
}

export interface RequestOptions {
  method: 'POST' | 'GET';
  path: string;
  /** Already snake_case body, or undefined for GET. */
  body?: object;
  requestId?: string;
  timeoutMs: number;
  fetch: FetchLike;
  baseUrl: string;
  apiKey: string;
  /** When true, network/5xx errors are thrown (caller handles retry). */
  signal?: AbortSignal;
}

export interface ParsedResponse<T> {
  status: number;
  data: T;
  requestId?: string;
}

const HTTP_STATUS_TO_ERROR_CODE: Record<number, string> = {
  400: 'invalid_request',
  401: 'invalid_api_key',
  402: 'insufficient_balance',
  403: 'model_not_allowed',
  429: 'rate_limit_exceeded',
};

export class Transport {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
    private readonly timeoutMs: number,
    private readonly fetchImpl: FetchLike,
  ) {}

  async post<T>(
    path: string,
    body: object,
    requestId?: string,
    signal?: AbortSignal,
  ): Promise<ParsedResponse<T>> {
    return request<T>(
      {
        method: 'POST',
        path,
        body,
        requestId,
        timeoutMs: this.timeoutMs,
        fetch: this.fetchImpl,
        baseUrl: this.baseUrl,
        apiKey: this.apiKey,
        signal,
      },
    );
  }

  /** Issue a request that swallows retriable failures and returns null on exhaustion — used by the flush path. */
  async tryPost<T>(
    path: string,
    body: object,
    requestId?: string,
  ): Promise<ParsedResponse<T> | null> {
    try {
      return await this.post<T>(path, body, requestId);
    } catch (err) {
      if (err instanceof ConduitError && isRetriable(err)) {
        return null;
      }
      throw err;
    }
  }
}

export async function request<T>(opts: RequestOptions): Promise<ParsedResponse<T>> {
  const url = joinUrl(opts.baseUrl, opts.path);
  const headers: Record<string, string> = {
    Authorization: `Bearer ${opts.apiKey}`,
    'Content-Type': 'application/json',
    Accept: 'application/json',
    'User-Agent': USER_AGENT,
    'X-Conduit-Client': CLIENT_HEADER,
  };
  if (opts.requestId) headers['X-Request-Id'] = opts.requestId;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs);
  // Link an external signal (e.g. shutdown) if provided.
  if (opts.signal) {
    if (opts.signal.aborted) controller.abort();
    else opts.signal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  let response: Response;
  try {
    response = await opts.fetch(url, {
      method: opts.method,
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    if (controller.signal.aborted) {
      throw new TimeoutError('Request timed out', { requestId: opts.requestId });
    }
    throw new NetworkError(`Network request failed: ${String(err)}`, {
      requestId: opts.requestId,
      cause: err,
    });
  }
  clearTimeout(timer);

  const respRequestId = response.headers.get('X-Request-Id') ?? undefined;

  if (response.status >= 200 && response.status < 300) {
    const data = (await parseJson(response)) as T;
    return { status: response.status, data, requestId: respRequestId };
  }

  const envelope = await parseError(response);
  throw mapError(response.status, envelope, respRequestId);
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function parseError(response: Response): Promise<BackendErrorEnvelope> {
  const parsed = (await parseJson(response)) as Partial<BackendErrorEnvelope> | null;
  if (parsed && parsed.error && typeof parsed.error.code === 'string') {
    return parsed as BackendErrorEnvelope;
  }
  return {
    error: {
      code: HTTP_STATUS_TO_ERROR_CODE[response.status] ?? 'unknown_error',
      message: `HTTP ${response.status}`,
    },
  };
}

function mapError(status: number, env: BackendErrorEnvelope, requestId?: string): ConduitError {
  const code = env.error.code;
  const message = env.error.message ?? code;
  const rid = env.error.request_id ?? requestId;
  switch (status) {
    case 401:
      return new UnauthorizedError(message, { code, requestId: rid });
    case 402:
      return new PaymentRequiredError(message, { code, requestId: rid });
    case 403:
      return new ForbiddenError(message, { code, requestId: rid });
    case 429:
      return new RateLimitError(message, { code, requestId: rid });
    default:
      if (status >= 500) return new ServerError(message, { code, status, requestId: rid });
      return new ConduitError(message, { code, status, requestId: rid });
  }
}

export function isRetriable(err: ConduitError): boolean {
  if (err instanceof ServerError) return true;
  if (err instanceof NetworkError) return true;
  if (err instanceof TimeoutError) return true;
  if (err instanceof RateLimitError) return true;
  return false;
}

function joinUrl(base: string, path: string): string {
  const trimmedBase = base.replace(/\/+$/, '');
  const trimmedPath = path.replace(/^\/+/, '');
  return `${trimmedBase}/${trimmedPath}`;
}
