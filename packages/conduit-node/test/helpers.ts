export interface RecordedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

export interface MockFetchOpts {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
  /** Delay in ms before responding. */
  delayMs?: number;
  /** Cause fetch to reject (network failure). */
  networkError?: boolean;
  /** Cause fetch to never resolve (for timeout tests). */
  hang?: boolean;
}

export function createMockFetch(
  responder: MockFetchOpts | ((req: RecordedRequest) => MockFetchOpts | Promise<MockFetchOpts>),
): {
  fetch: typeof fetch;
  requests: RecordedRequest[];
  setResponder: (r: typeof responder) => void;
} {
  const requests: RecordedRequest[] = [];
  let current: typeof responder = responder;

  const fetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input.toString();
    const method = init?.method ?? 'GET';
    const rawHeaders = init?.headers;
    const headers: Record<string, string> = {};
    const lowerKey = (k: string) => k.toLowerCase();
    if (rawHeaders) {
      if (rawHeaders instanceof Headers) {
        rawHeaders.forEach((v, k) => {
          headers[lowerKey(k)] = v;
        });
      } else if (Array.isArray(rawHeaders)) {
        for (const [k, v] of rawHeaders) headers[lowerKey(k)] = String(v);
      } else {
        for (const [k, v] of Object.entries(rawHeaders)) headers[lowerKey(k)] = String(v);
      }
    }
    let body: unknown = undefined;
    if (init?.body) {
      try {
        body = JSON.parse(init.body as string);
      } catch {
        body = init.body;
      }
    }
    const recorded: RecordedRequest = { url, method, headers, body };
    requests.push(recorded);

    const opts = typeof current === 'function' ? await current(recorded) : current;

    if (opts.networkError) throw new TypeError('Failed to fetch (network)');
    if (opts.hang) {
      return new Promise<Response>((_, reject) => {
        const signal = init?.signal;
        const abort = (): void => reject(new DOMException('aborted', 'AbortError'));
        if (signal) {
          if (signal.aborted) abort();
          else signal.addEventListener('abort', abort, { once: true });
        }
      });
    }

    const status = opts.status ?? 200;
    const responseBody = opts.body ?? null;
    const responseHeaders = new Headers(opts.headers ?? {});
    if (opts.delayMs && opts.delayMs > 0) {
      await new Promise((r) => setTimeout(r, opts.delayMs));
    }
    const text = responseBody === null || responseBody === undefined ? '' : JSON.stringify(responseBody);
    return new Response(text, {
      status,
      headers: responseHeaders,
    });
  };

  return {
    fetch,
    requests,
    setResponder: (r) => {
      current = r;
    },
  };
}

export function noop(): void {
  /* silence is golden */
}
