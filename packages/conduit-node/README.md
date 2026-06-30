# @conduit/sdk

Smart metering SDK for [Conduit](../../README.md) — the prepaid payment and identity layer for AI ("MetaMask for AI"). The SDK sits inside a partner app and meters LLM usage: it pre-authorizes a hold on the Redis fast path, then batches and async-flushes actual token usage to the wallet's ingestion endpoint. A `402 Payment Required` mid-stream lets the app freeze compute cleanly when funds are exhausted.

## Install

```bash
npm install @conduit/sdk
# or
pnpm add @conduit/sdk
```

## Quick start (< 30 lines)

```ts
import { Conduit, PaymentRequiredError } from '@conduit/sdk';
import OpenAI from 'openai';

const wallet = new Conduit({ apiKey: process.env.CONDUIT_API_KEY });
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function chat(prompt: string) {
  const auth = await wallet.authorize({ model: 'gpt-4o', maxTokens: 1024 });
  if (!auth.authorized) throw new PaymentRequiredError('funds exhausted', { code: 'insufficient_balance' });

  try {
    const res = await openai.chat.completions.create({ model: 'gpt-4o', messages: [{ role: 'user', content: prompt }] });
    wallet.charge({
      requestId: auth.requestId,
      model: 'gpt-4o',
      inputTokens: res.usage!.prompt_tokens,
      outputTokens: res.usage!.completion_tokens,
      provider: 'openai',
    });
    return res.choices[0]!.message;
  } catch (err) {
    if (err instanceof PaymentRequiredError) return { content: 'Top up your AI Wallet to continue.' };
    throw err;
  }
}

// On graceful shutdown / in serverless handlers, flush before exit:
await wallet.shutdown();
```

## API

### `new Conduit(config)`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `apiKey` | `string` | `env.CONDUIT_API_KEY` | `sk-conduit-*` virtual key **or** a delegated OAuth app access token. Carries identity via `Authorization: Bearer`. |
| `baseUrl` | `string` | `env.CONDUIT_BASE_URL` / `https://api.example.com/v1` | Gateway base URL including `/v1`. |
| `flushIntervalMs` | `number` | `5000` | Periodic flush interval for batched `charge()` events. `0` disables the timer. |
| `maxBatchSize` | `number` | `100` | Flush trigger when the buffer reaches this many events. |
| `maxBufferSize` | `number` | `10000` | Hard cap; oldest events are dropped via `onDrop` when exceeded. |
| `timeoutMs` | `number` | `10000` | Per-request HTTP timeout. |
| `retries` | `number` | `3` | Retries (exponential backoff) for a failing usage flush. |
| `fetch` | `FetchLike` | global `fetch` | Injectable for browser / edge / tests. |
| `logger` | `Logger` | silent | Optional structured logger. |
| `onDrop` | `(events, reason) => void` | — | Called when events are dropped (`buffer_full` or `max_retries`). |
| `onError` | `(error, { events }) => void` | — | Called when a flush fails permanently. |

### `wallet.authorize(options): Promise<AuthorizeResult>`

Phase 6.2 — pre-authorize on the Redis fast path and place a hold.

```ts
const auth = await wallet.authorize({
  model: 'gpt-4o',
  maxTokens: 1024,                       // optional
  requestedReserveMicrodollars: 50_000,  // optional; $0.05 = 50_000 microdollars
  requestId: 'optional-uuid',            // optional; generated if absent
});
// → { authorized, requestId, mode, heldMicrodollars, availableMicrodollars, balanceMicrodollars, expiresAtMs }
```

Throws `PaymentRequiredError` (`402`, `code` ∈ `insufficient_balance` | `allowance_exceeded` | `spend_limit_exceeded`) or `UnauthorizedError` (`401`, `code` = `app_revoked`). Catch `PaymentRequiredError` and **freeze compute** before calling the LLM provider.

### `wallet.charge(input): void`

Phase 6.3 — enqueue usage for batched, fire-and-forget flush. **Synchronous and non-blocking.** `requestId` must match the value returned by `authorize()` so the billing worker can release the hold and debit the correct wallet.

```ts
wallet.charge({
  requestId: auth.requestId,
  model: 'gpt-4o',
  inputTokens: 400,
  outputTokens: 120,
  provider: 'openai',
});
```

### `wallet.flush(): Promise<void>`

Flush all buffered events now. **Await this in serverless handlers** (Vercel / Lambda / edge) where the periodic timer may not fire before the process is frozen.

### `wallet.shutdown(): Promise<void>`

Stop the timer and await a final flush. Call on graceful process shutdown.

## Error handling (Phase 6.4)

| Error | HTTP | `code` | Action |
|-------|------|-------|--------|
| `PaymentRequiredError` | 402 | `insufficient_balance` / `allowance_exceeded` / `spend_limit_exceeded` | Freeze compute; prompt user to top up / raise the per-app cap. |
| `UnauthorizedError` | 401 | `invalid_api_key` / `app_revoked` | Re-auth or refresh the delegated token. |
| `ForbiddenError` | 403 | `model_not_allowed` | Pick a model the caller's access group permits. |
| `RateLimitError` | 429 | `rate_limit_exceeded` | Back off. |
| `ServerError` | 5xx | `provider_error` / `unknown_error` | Retry; usage flushes retry automatically with backoff. |
| `TimeoutError` | — | `timeout` | Request exceeded `timeoutMs`. |
| `NetworkError` | — | `network_error` | DNS / connection failure; retriable for usage flushes. |

All errors extend `ConduitError` and carry `code`, `status`, and `requestId` (for support / usage lookup).

## Serverless usage

In serverless environments, set `flushIntervalMs: 0` (no background timer) and await `wallet.flush()` at the end of every request:

```ts
export async function handler(req) {
  const wallet = new Conduit({ apiKey, flushIntervalMs: 0 });
  try {
    const auth = await wallet.authorize({ model: 'gpt-4o' });
    // ... call provider, wallet.charge(...) ...
    return { statusCode: 200, body: 'ok' };
  } finally {
    await wallet.flush();
  }
}
```

## Backend contract

The SDK targets two Bearer-authenticated endpoints (identity carried by the key/token, no `userToken` body field):

- `POST /v1/authorize` → `{ model, max_tokens?, requested_reserve_microdollars? }`
- `POST /v1/usage` → `{ events: [{ request_id, model, input_tokens, output_tokens, provider? }] }` (`202`, idempotent on `request_id`)

See [`docs/04-api-contracts.md`](../../docs/04-api-contracts.md) and [`openapi/gateway.yaml`](../../openapi/gateway.yaml).

## Development

```bash
pnpm install
pnpm --filter @conduit/sdk lint
pnpm --filter @conduit/sdk typecheck
pnpm --filter @conduit/sdk test
pnpm --filter @conduit/sdk build
```

Money is integer microdollars (`$1.00 = 1_000_000`) end-to-end; the SDK never converts to floats.

## License

MIT
