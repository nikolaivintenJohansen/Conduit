import type { AuthorizeOptions, AuthorizeResult } from './types.js';
import { Transport } from './transport.js';

interface AuthorizeRequestBody {
  model: string;
  max_tokens?: number;
  requested_reserve_microdollars?: number;
}

interface AuthorizeResponseDto {
  authorized: boolean;
  request_id: string;
  mode: string;
  held_microdollars: number;
  available_microdollars: number;
  balance_microdollars: number;
  expires_at_ms?: number | null;
}

/**
 * Phase 6.2 — pre-authorize a request on the Redis fast path. Returns the hold
 * details on success. Throws {@link PaymentRequiredError} on 402 (insufficient
 * balance / allowance / spend limit) and {@link UnauthorizedError} on 401
 * (revoked app). Apps MUST catch PaymentRequiredError and freeze compute.
 */
export async function authorize(
  transport: Transport,
  options: AuthorizeOptions,
): Promise<AuthorizeResult> {
  const body: AuthorizeRequestBody = { model: options.model };
  if (options.maxTokens !== undefined) body.max_tokens = options.maxTokens;
  if (options.requestedReserveMicrodollars !== undefined) {
    body.requested_reserve_microdollars = options.requestedReserveMicrodollars;
  }

  const { data } = await transport.post<AuthorizeResponseDto>(
    '/authorize',
    body,
    options.requestId,
  );

  return {
    authorized: data.authorized,
    requestId: data.request_id,
    mode: data.mode,
    heldMicrodollars: data.held_microdollars,
    availableMicrodollars: data.available_microdollars,
    balanceMicrodollars: data.balance_microdollars,
    expiresAtMs: data.expires_at_ms ?? null,
  };
}
