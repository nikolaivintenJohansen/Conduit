import { describe, expect, it } from 'vitest';
import { Transport } from '../src/transport.js';
import {
  ConduitError,
  ForbiddenError,
  NetworkError,
  PaymentRequiredError,
  RateLimitError,
  ServerError,
  TimeoutError,
  UnauthorizedError,
} from '../src/errors.js';
import { createMockFetch } from './helpers.js';

const BASE = 'https://api.example.com/v1';

describe('Transport', () => {
  it('sends Bearer + User-Agent + X-Conduit-Client headers and JSON body', async () => {
    const { fetch, requests } = createMockFetch({ status: 200, body: { ok: true } });
    const t = new Transport(BASE, 'sk-conduit-test', 5000, fetch);
    await t.post('/authorize', { model: 'gpt-4o' }, 'req-123');
    const req = requests[0]!;
    expect(req.url).toBe(`${BASE}/authorize`);
    expect(req.headers['authorization']).toBe('Bearer sk-conduit-test');
    expect(req.headers['x-request-id']).toBe('req-123');
    expect(req.headers['user-agent']).toMatch(/^conduit-node\//);
    expect(req.headers['x-conduit-client']).toMatch(/^conduit-node\//);
    expect(req.body).toEqual({ model: 'gpt-4o' });
  });

  it('strips trailing slashes from baseUrl', async () => {
    const { fetch, requests } = createMockFetch({ status: 200, body: {} });
    const t = new Transport('https://api.example.com/v1/', 'k', 5000, fetch);
    await t.post('/authorize', { model: 'x' });
    expect(requests[0]!.url).toBe(`${BASE}/authorize`);
  });

  it('maps 402 insufficient_balance to PaymentRequiredError with sub-code', async () => {
    const { fetch } = createMockFetch({
      status: 402,
      body: { error: { code: 'insufficient_balance', message: 'no funds', request_id: 'r1' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' }, 'r1')).rejects.toBeInstanceOf(
      PaymentRequiredError,
    );
    await expect(t.post('/authorize', { model: 'x' }, 'r1')).rejects.toMatchObject({
      code: 'insufficient_balance',
      status: 402,
      requestId: 'r1',
    });
  });

  it('maps 402 allowance_exceeded and spend_limit_exceeded to PaymentRequiredError', async () => {
    for (const code of ['allowance_exceeded', 'spend_limit_exceeded']) {
      const { fetch } = createMockFetch({
        status: 402,
        body: { error: { code, message: 'm' } },
      });
      const t = new Transport(BASE, 'k', 5000, fetch);
      await expect(t.post('/authorize', { model: 'x' })).rejects.toBeInstanceOf(PaymentRequiredError);
    }
  });

  it('maps 401 app_revoked to UnauthorizedError', async () => {
    const { fetch } = createMockFetch({
      status: 401,
      body: { error: { code: 'app_revoked', message: 'revoked' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' })).rejects.toBeInstanceOf(UnauthorizedError);
  });

  it('maps 403 model_not_allowed to ForbiddenError', async () => {
    const { fetch } = createMockFetch({
      status: 403,
      body: { error: { code: 'model_not_allowed', message: 'no' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' })).rejects.toBeInstanceOf(ForbiddenError);
  });

  it('maps 429 rate_limit_exceeded to RateLimitError', async () => {
    const { fetch } = createMockFetch({
      status: 429,
      body: { error: { code: 'rate_limit_exceeded', message: 'slow' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' })).rejects.toBeInstanceOf(RateLimitError);
  });

  it('maps 502 to ServerError', async () => {
    const { fetch } = createMockFetch({
      status: 502,
      body: { error: { code: 'provider_error', message: 'upstream' } },
    });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' })).rejects.toBeInstanceOf(ServerError);
  });

  it('maps network failure to NetworkError', async () => {
    const { fetch } = createMockFetch({ networkError: true });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' }, 'r9')).rejects.toBeInstanceOf(NetworkError);
  });

  it('aborts on timeout and throws TimeoutError', async () => {
    const { fetch } = createMockFetch({ hang: true });
    const t = new Transport(BASE, 'k', 30, fetch);
    await expect(t.post('/authorize', { model: 'x' }, 'rt')).rejects.toBeInstanceOf(TimeoutError);
  });

  it('falls back to generic ConduitError when envelope missing', async () => {
    const { fetch } = createMockFetch({ status: 418, body: null });
    const t = new Transport(BASE, 'k', 5000, fetch);
    await expect(t.post('/authorize', { model: 'x' })).rejects.toBeInstanceOf(ConduitError);
  });
});
