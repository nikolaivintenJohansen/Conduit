/**
 * Base error for all AI Wallet SDK failures. Carries the backend `error.code`,
 * the HTTP `status`, and the `requestId` for support/usage lookup.
 */
export class ConduitError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;

  constructor(
    message: string,
    opts: { code: string; status: number; requestId?: string; cause?: unknown },
  ) {
    super(message);
    this.name = 'ConduitError';
    this.code = opts.code;
    this.status = opts.status;
    this.requestId = opts.requestId;
    if (opts.cause !== undefined) {
      (this as { cause?: unknown }).cause = opts.cause;
    }
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 402 Payment Required — wallet balance or app allowance exhausted. Freeze compute. */
export class PaymentRequiredError extends ConduitError {
  constructor(message: string, opts: { code: string; requestId?: string }) {
    super(message, { code: opts.code, status: 402, requestId: opts.requestId });
    this.name = 'PaymentRequiredError';
    Object.setPrototypeOf(this, PaymentRequiredError.prototype);
  }
}

/** 401 Unauthorized — invalid/revoked key or revoked app install. Re-auth / refresh token. */
export class UnauthorizedError extends ConduitError {
  constructor(message: string, opts: { code: string; requestId?: string }) {
    super(message, { code: opts.code, status: 401, requestId: opts.requestId });
    this.name = 'UnauthorizedError';
    Object.setPrototypeOf(this, UnauthorizedError.prototype);
  }
}

/** 403 Forbidden — model not allowed by the caller's access group. */
export class ForbiddenError extends ConduitError {
  constructor(message: string, opts: { code: string; requestId?: string }) {
    super(message, { code: opts.code, status: 403, requestId: opts.requestId });
    this.name = 'ForbiddenError';
    Object.setPrototypeOf(this, ForbiddenError.prototype);
  }
}

/** 429 Too Many Requests — RPM/TPM rate limit exceeded. */
export class RateLimitError extends ConduitError {
  constructor(message: string, opts: { code: string; requestId?: string }) {
    super(message, { code: opts.code, status: 429, requestId: opts.requestId });
    this.name = 'RateLimitError';
    Object.setPrototypeOf(this, RateLimitError.prototype);
  }
}

/** 5xx / unexpected upstream failure. */
export class ServerError extends ConduitError {
  constructor(message: string, opts: { code: string; status: number; requestId?: string }) {
    super(message, opts);
    this.name = 'ServerError';
    Object.setPrototypeOf(this, ServerError.prototype);
  }
}

/** Request aborted due to timeout. */
export class TimeoutError extends ConduitError {
  constructor(message: string, opts: { requestId?: string }) {
    super(message, { code: 'timeout', status: 408, requestId: opts.requestId });
    this.name = 'TimeoutError';
    Object.setPrototypeOf(this, TimeoutError.prototype);
  }
}

/** Network-level failure (DNS, connection refused, etc.). */
export class NetworkError extends ConduitError {
  constructor(message: string, opts: { requestId?: string; cause?: unknown }) {
    super(message, { code: 'network_error', status: 0, requestId: opts.requestId, cause: opts.cause });
    this.name = 'NetworkError';
    Object.setPrototypeOf(this, NetworkError.prototype);
  }
}
