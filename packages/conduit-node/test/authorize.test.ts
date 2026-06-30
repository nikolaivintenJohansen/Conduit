import { describe, expect, it } from 'vitest';
import { authorize } from '../src/authorize.js';
import { Transport } from '../src/transport.js';
import { PaymentRequiredError, UnauthorizedError } from '../src/errors.js';
import { createMockFetch } from './helpers.js';

const BASE = 'https://api.example.com/v1';

describe('authorize (Phase 6.2)', () => {
  it('returns camelCase result and echoes requestId', async () => {
    const { fetch, requests } = createMockFetch({
      status: 200,
      body: {
        authorized: true,
        request_id: 'req-abc',
        mode: 'redis_hold',
        held_microdollars: 5000,
        available_microdollars: 4_995_000,
        balance_microdollars: 5_000_000,
        expires_at_ms: 1234567890,
      },
    });
    const t = new Transport(BASE, 'sk-conduit-x', 5000, fetch);
    const res = await authorize(t, { model: 'gpt-4o', maxTokens: 1024, requestId: 'req-abc' });
    expect(res).toEqual({
      authorized: true,
      requestId: 'req-abc',
      mode: 'redis_hold',
      heldMicrodollars: 5000,
      availableMicrodollars: 4_995_000,
      balanceMicrodollars: 5_000_000,
      expiresAtMs: 1234567890,
    });
    expect(requests[0]!.body).toEqual({ model: 'gpt-4o', max_tokens: 1024 });
    expect(requests[0]!.headers['x-request-id']).toBe('req-abc');
  });

  it('passes requestedReserveMicrodollars as requested_reserve_microdollars', async () => {
    const { fetch, requests } = createMockFetch({
      status: 200,
      body: {
        authorized: true,
        request_id: 'r',
        mode: 'redis_hold',
        held_microdollars: 50_000,
        available_microdollars: 0,
        balance_microdollars: 0,
      },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await authorize(t, { model: 'gpt-4o', requestedReserveMicrodollars: 50_000 });
    expect(requests[0]!.body).toEqual({
      model: 'gpt-4o',
      requested_reserve_microdollars: 50_000,
    });
  });

  it('omits optional fields when not provided', async () => {
    const { fetch, requests } = createMockFetch({
      status: 200,
      body: {
        authorized: true,
        request_id: 'r',
        mode: 'redis_hold',
        held_microdollars: 0,
        available_microdollars: 0,
        balance_microdollars: 0,
      },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await authorize(t, { model: 'claude-3' });
    expect(requests[0]!.body).toEqual({ model: 'claude-3' });
  });

  it('throws PaymentRequiredError on 402 insufficient_balance', async () => {
    const { fetch } = createMockFetch({
      status: 402,
      body: { error: { code: 'insufficient_balance', message: 'no funds', request_id: 'r' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(authorize(t, { model: 'x' })).rejects.toBeInstanceOf(PaymentRequiredError);
  });

  it('throws UnauthorizedError on 401 app_revoked', async () => {
    const { fetch } = createMockFetch({
      status: 401,
      body: { error: { code: 'app_revoked', message: 'revoked', request_id: 'r' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(authorize(t, { model: 'x' })).rejects.toBeInstanceOf(UnauthorizedError);
  });
});
