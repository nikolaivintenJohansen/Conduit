import { afterEach, describe, expect, it } from 'vitest';
import { Conduit, PaymentRequiredError } from '../src/index.js';
import { createMockFetch } from './helpers.js';

const BASE = 'https://api.example.com/v1';

describe('Phase 6.4 — 402 stops LLM calls cleanly', () => {
  let wallet: Conduit;
  afterEach(async () => {
    if (wallet) await wallet.shutdown();
  });

  it('authorize() throws PaymentRequiredError on 402 and the app skips the provider call', async () => {
    const { fetch } = createMockFetch({
      status: 402,
      body: {
        error: {
          code: 'insufficient_balance',
          message: 'Wallet balance too low',
          request_id: 'r-402',
        },
      },
    });
    wallet = new Conduit({
      apiKey: 'sk-conduit-test',
      baseUrl: BASE,
      fetch,
      flushIntervalMs: 0,
    });

    let providerCalled = false;
    const fakeProviderCall = async (): Promise<string> => {
      providerCalled = true;
      return 'should-not-happen';
    };

    let caught: PaymentRequiredError | null = null;
    try {
      const auth = await wallet.authorize({ model: 'gpt-4o', maxTokens: 256 });
      // If somehow authorized, call provider.
      if (auth.authorized) await fakeProviderCall();
    } catch (err) {
      caught = err as PaymentRequiredError;
      // App freezes compute here — do NOT call the provider.
    }

    expect(caught).toBeInstanceOf(PaymentRequiredError);
    expect(caught!.code).toBe('insufficient_balance');
    expect(caught!.status).toBe(402);
    expect(caught!.requestId).toBe('r-402');
    expect(providerCalled).toBe(false); // compute frozen — provider never invoked
  });

  it('maps allowance_exceeded 402 to PaymentRequiredError with that sub-code', async () => {
    const { fetch } = createMockFetch({
      status: 402,
      body: { error: { code: 'allowance_exceeded', message: 'app cap hit' } },
    });
    wallet = new Conduit({
      apiKey: 'sk-conduit-test',
      baseUrl: BASE,
      fetch,
      flushIntervalMs: 0,
    });
    await expect(wallet.authorize({ model: 'gpt-4o' })).rejects.toMatchObject({
      name: 'PaymentRequiredError',
      code: 'allowance_exceeded',
    });
  });
});
