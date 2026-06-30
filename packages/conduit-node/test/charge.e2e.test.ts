import { afterEach, describe, expect, it } from 'vitest';
import { Conduit } from '../src/client.js';
import { createMockFetch, type RecordedRequest } from './helpers.js';

const BASE = 'https://api.example.com/v1';

function route(req: RecordedRequest): { status: number; body: unknown } {
  if (req.url.endsWith('/authorize')) {
    return {
      status: 200,
      body: {
        authorized: true,
        request_id: 'r-fixed',
        mode: 'redis_hold',
        held_microdollars: 5000,
        available_microdollars: 5_000_000,
        balance_microdollars: 5_005_000,
        expires_at_ms: null,
      },
    };
  }
  if (req.url.endsWith('/usage')) {
    const events = (req.body as { events: unknown[] }).events;
    return {
      status: 202,
      body: {
        accepted: events.length,
        duplicated: 0,
        stream: 'conduit:usage:events',
        request_ids: events.map((e) => (e as { request_id: string }).request_id),
      },
    };
  }
  return { status: 404, body: { error: { code: 'not_found', message: 'no' } } };
}

describe('Conduit client — end-to-end charge flow (6.2 + 6.3)', () => {
  let wallet: Conduit;
  afterEach(async () => {
    if (wallet) await wallet.shutdown();
  });

  it('authorize -> charge -> flush posts a batch to /v1/usage', async () => {
    const { fetch, requests } = createMockFetch(route);
    wallet = new Conduit({
      apiKey: 'sk-conduit-test',
      baseUrl: BASE,
      fetch,
      flushIntervalMs: 0,
      maxBatchSize: 100,
    });

    const auth = await wallet.authorize({ model: 'gpt-4o', maxTokens: 1024 });
    expect(auth.authorized).toBe(true);

    wallet.charge({
      requestId: auth.requestId,
      model: 'gpt-4o',
      inputTokens: 400,
      outputTokens: 120,
      provider: 'openai',
    });
    wallet.charge({
      requestId: 'r-second',
      model: 'gpt-4o',
      inputTokens: 50,
      outputTokens: 10,
    });
    expect(wallet.pendingCount).toBe(2);

    const flushP = wallet.flush();
    await flushP;

    const usageCall = requests.find((r) => r.url.endsWith('/usage'));
    expect(usageCall).toBeDefined();
    const events = (usageCall!.body as { events: unknown[] }).events;
    expect(events).toHaveLength(2);
    expect((events[0] as { input_tokens: number }).input_tokens).toBe(400);
    expect((events[0] as { provider: string }).provider).toBe('openai');
    expect((events[1] as { request_id: string }).request_id).toBe('r-second');
    expect(wallet.pendingCount).toBe(0);
  });

  it('auto-flushes when maxBatchSize is reached', async () => {
    const { fetch, requests } = createMockFetch(route);
    wallet = new Conduit({
      apiKey: 'sk-conduit-test',
      baseUrl: BASE,
      fetch,
      flushIntervalMs: 0,
      maxBatchSize: 2,
    });
    wallet.charge({ requestId: 'a', model: 'gpt-4o', inputTokens: 1, outputTokens: 1 });
    wallet.charge({ requestId: 'b', model: 'gpt-4o', inputTokens: 1, outputTokens: 1 });
    await new Promise((r) => setTimeout(r, 10));
    const usageCall = requests.find((r) => r.url.endsWith('/usage'));
    expect(usageCall).toBeDefined();
  });
});
