# Universal AI Wallet

One identity, one prepaid balance, many AI apps — with partner pricing and margin on usage.

## Project Overview & Purpose

AI Wallet is a universal, high-throughput payment and identity layer designed specifically for the AI ecosystem. Positioned as **"MetaMask for AI,"** it is a single, centralized account that users fund once and connect across multiple AI applications.

The system solves two primary bottlenecks in the current AI landscape:

| Problem | How AI Wallet solves it |
|---------|-------------------------|
| **User friction** | Replaces fragmented subscriptions and billing across dozens of AI tools (coding assistants, image generators, writing apps) with one wallet and one balance. |
| **Economic viability** | Standard processors (e.g. Stripe at 2.9% + $0.30) destroy margins on micro-charges (e.g. $0.15 per LLM prompt). Macro-deposits and batch settlement absorb fees once, not per token. |

## Technical Blueprint

> Comprehensive technical documentation for AI Wallet — optimized for importing into an AI code editor (like Cursor) to structure models, controllers, and system architecture.

### 1. Core architecture & data flow

To handle high-frequency AI interactions without slowing app responsiveness or risking wallet overdrafts, the architecture **strictly decouples fast data from slow data**.

**The fast path (low-latency stream)**

When an AI app begins a session, it requests pre-authorization via the SDK. The system checks an in-memory cache (Redis) for sufficient funds and places a micro-hold on the balance. As the user consumes tokens, the SDK batches usage events locally and flushes them asynchronously to a durable message broker (Kafka or RabbitMQ). The application's main thread is never blocked.

**The slow path (the ledger)**

A background Billing Engine pulls raw usage events off the message queue, calculates exact financial deductions, and writes immutable transaction entries to PostgreSQL.

| Stage | Path | What happens |
|-------|------|----------------|
| **Handshake** | OAuth | User clicks "Connect AI Wallet" and approves a per-app spending limit (e.g. "$5.00 for Cursor"). |
| **Pre-auth** | Fast (Redis) | App receives a session token; SDK checks cache for balance + allowance and places a hold. |
| **Usage** | Event stream | SDK batches and async-flushes usage events to the message queue. |
| **Ledger** | Slow (Postgres) | Billing engine applies pricing rules and writes append-only micro-deductions. |
| **Settlement** | Batch (CRON) | Aggregates pending usage and executes a single Stripe Connect payout to the AI company. |

See [`docs/02-architecture.md`](./docs/02-architecture.md) for implemented service boundaries.

### 2. Immutable ledger & billing engine

Financial accuracy relies on a custom, event-sourced data model.

**Integer micro-amounts** — All monetary values are stored as exact integers (microdollars: `$1.00 = 1_000_000`) to avoid floating-point errors over millions of transactions. (Also referred to as "micro-cents" in product docs; same scale.)

**Append-only system** — The ledger never mutates past rows. Corrections and refunds are new rows that balance the ledger.

**Dynamic rating** — The Billing Engine normalizes fragmented token metrics from providers (OpenAI, Anthropic, etc.) into a uniform schema, computes base provider cost, and adds each AI company's percentage markup.

| Model | Purpose | Key fields |
|-------|---------|------------|
| **User** | Identity & balance | `id`, `wallet_address`, `balance_microdollars`, `stripe_customer_id`, `auto_topup_*` |
| **AppConnection** | Per-app limiters | `user_id`, `app_id`, `allowance_limit_microdollars`, `allowance_spent_microdollars`, `reset_period` |
| **Transaction** | Append-only ledger | `type` (DEPOSIT, USAGE, REFUND, SETTLEMENT), `amount_microdollars`, `resource_metric`, `resource_quantity` |
| **AI_Application** | Partner registry | `name`, `api_key_hash`, `stripe_connect_id`, `pricing_markup_pct` |

> **Repo mapping:** Implemented schema uses `users`, `wallets`, `ledger_entries`, `app_installs`, and `partner_accounts`. See [`schemas/001_initial.sql`](./schemas/001_initial.sql) and [`docs/03-data-model.md`](./docs/03-data-model.md).

**Billing example**

1. **Ingest** — 400 input tokens from the queue.
2. **Base cost** — `gpt-4o` @ $0.0050/1K input → $0.002 (2,000 microdollars).
3. **Markup** — App has 20% markup → 2,000 × 1.2 = **2,400 microdollars**.
4. **Ledger write** — Deduct from user balance; increment `allowance_spent`; insert transaction row.
5. **Limiter** — If allowance exceeded, emit `LimitReached` via WebSocket and revoke session token.

Base costs come from **LiteLLM** (see [Key decision](#key-decision)); partner markup is applied in `pricing/`.

### 3. Financial routing: master pool & batch settlement

AI Wallet is a ledger on top of traditional payment rails, using a **master pool and scoreboard** model.

**Macro-deposits (inbound)** — Users fund the wallet in larger increments ($20, $100, etc.) via Stripe. The platform absorbs the processing fee once on deposit. Funds sit in a central company pool or FBO (For Benefit Of) account.

**Virtual scoreboard (usage)** — As users consume tokens across apps, no real money moves per request. The database scoreboard deducts micro-amounts from the user's ledger and credits the app's pending balance.

**Batch payouts (outbound)** — A nightly or weekly CRON aggregates pending usage per AI company (e.g. $15,400) and executes a single B2B transfer via Stripe Connect.

```sql
SELECT SUM(amount_microdollars)
FROM transactions
WHERE type = 'USAGE'
  AND app_id = 'CURSOR_123'
  AND settlement_status = 'PENDING';
```

1. **Aggregate** — e.g. 1,540,000,000 microdollars ($15,400.00).
2. **Payout** — Stripe Connect transfer to the app's connected account.
3. **Reconcile** — Set `settlement_status = 'CLEARED'` on included transactions.

### 4. Security, identity & user experience

The wallet is a unified identity layer; protecting funds from runaway AI agents is critical.

**Connect handshake** — Users authenticate via a secure browser popup or Web3-style extension. They connect to an app without new passwords or card entry.

**Granular limiters (safety switch)** — Per-app monthly or per-session caps (e.g. $10 for Perplexity, $5 for Cursor).

**Isolation security** — A buggy or looping agent can only drain its isolated allowance. When the cap is hit, the SDK returns **402 Payment Required** and the gateway blocks further charges, leaving the rest of the wallet intact.

See [`docs/05-security-model.md`](./docs/05-security-model.md) for keys, PCI boundary, and idempotency.

### 5. Developer integration & SDK

AI companies integrate without building usage billing, invoicing, or subscription infrastructure from scratch.

**Plug-and-play tracking** — The `ai-wallet-node` SDK is a smart meter inside the app. Developers pass raw usage (e.g. token counts) into the SDK.

**Managed user dashboards** — Usage flows to the central ledger; AI Wallet renders itemized billing history so partners don't build billing UI.

**Lightweight fallbacks** — Hosted Checkout redirects or server-to-server webhooks for teams that cannot use the proprietary SDK.

**Target API (`@ai-wallet/sdk`)**

```javascript
import { AIWallet } from '@ai-wallet/sdk';

const wallet = new AIWallet({ apiKey: process.env.AI_WALLET_API_KEY });

async function handleChatRequest(userId, prompt) {
  const auth = await wallet.authorize({
    userToken: userId,
    requestedReserve: 0.05, // Reserve 5 cents
  });
  if (!auth.success) {
    throw new Error('402 Payment Required: Wallet balance or app allowance exceeded');
  }

  const llmResponse = await openai.chat.completions.create({ /* ... */ });

  wallet.charge({
    userToken: userId,
    usage: {
      metric: 'gpt-4o',
      inputTokens: llmResponse.usage.prompt_tokens,
      outputTokens: llmResponse.usage.completion_tokens,
    },
  });

  return llmResponse.choices[0].message;
}
```

---

**For Cursor:** Reference this README with `@README.md` or paste into Composer for full product and data-model context when generating controllers and services.

## Implementation Phases

Build order is **sequential** — ledger first, then deposits, auth, fast/slow paths, SDK, settlement. Full checklist with repo status: [`docs/07-implementation-phases.md`](./docs/07-implementation-phases.md).

| Phase | Name | Summary | Status |
|-------|------|---------|--------|
| **1** | Immutable Ledger | PostgreSQL, BigInt microdollars, append-only `ledger_entries`, balance CRUD | **Foundation done** |
| **2** | Inbound Gateway | Stripe Checkout, webhooks, DEPOSIT credits to master pool | **Mostly done** |
| **3** | Handshake & Auth | OAuth2 Authorization Code + PKCE / OIDC, Google login, per-app allowances, delegated gateway tokens | **Done** |
| **4** | Ingestion Engine | Redis `/v1/authorize` (atomic check-and-hold), Redis Streams usage queue, `POST /v1/usage` → 202 | **Done** |
| **5** | Billing Worker | Stream consumer, rating + markup, atomic USAGE writes, idempotent settle, Redis-gated monthly spend limit, cache revalidation/eviction, worker DLQ | **Done** |
| **6** | Client SDK | `ai-wallet-node`: `authorize()`, batched `charge()`, 402 handling | **Done** |
| **7** | Batch Settlement | Stripe Connect, nightly CRON, aggregate + payout + reconcile | **Not started** |

## Status

| Task | Status |
|------|--------|
| Task 1 — Foundation docs & schema | Complete |
| **Task 11 — Testing & sandbox** | **Complete** |
| **Task 12 — Minimal deploy & observability** | **Complete** |
| Task 2 — Identity layer (OAuth2/OIDC + Google login + delegated app tokens + per-app allowances) | Complete |
| Task 7/8 — Gateway ingestion + async metering (Phase 4 fast path + Phase 5 billing worker + Phase 5 hardening: monthly spend limit, cache revalidation, DLQ) | Complete |

## Quick start (Task 11 sandbox + Task 12 deploy)

```powershell
# Full stack (app + Postgres + Redis)
docker compose up --build

# Or infra only for local pytest against host-run app
docker compose up -d postgres redis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
docker compose exec postgres psql -U uaw -d uaw -c "CREATE DATABASE uaw_test;"
$env:TEST_DATABASE_URL = "postgresql+psycopg://uaw:uaw@localhost:5432/uaw_test"
psql postgresql://uaw:uaw@localhost:5432/uaw_test -f schemas/001_initial.sql
psql postgresql://uaw:uaw@localhost:5432/uaw_test -f schemas/002_oauth_and_apps.sql
python scripts/seed_sandbox.py
pytest -v
uvicorn services.app.main:app --reload --port 8000
```

Health: `GET http://localhost:8000/health` (also `/v1/health`). Structured JSON request logs include `request_id`, `latency_ms`, auth hint, and optional `cost_usd`.

See [`tests/sandbox/README.md`](./tests/sandbox/README.md) for demo credentials and mock-provider notes.

## Documents

| Resource | Path |
|----------|------|
| Project overview & blueprint | This README — [Overview](#project-overview--purpose) · [Blueprint](#technical-blueprint) |
| **Implementation phases** | [`docs/07-implementation-phases.md`](./docs/07-implementation-phases.md) |
| Engineering tasks | [`ai_wallet_tasks.txt`](./ai_wallet_tasks.txt) |
| Product stages | [`PROJECT_STAGES.txt`](./PROJECT_STAGES.txt) |
| Foundation docs | [`docs/README.md`](./docs/README.md) |

## Repo layout (Tasks 11–12)

```
services/
  app/          # FastAPI entry, /health, request logging middleware
  shared/       # config, DB (sync + async), SQLAlchemy models, logging
  wallet/       # auth, keys, ledger, payments (testable core)
  gateway/      # access control, mock provider, balance_cache, usage_queue,
                # authorize (fast path), worker (billing), rate limiting
  pricing/      # charge calculation
tests/          # unit + integration tests, CI-covered
scripts/        # sandbox seed
Dockerfile
docker-compose.yml
```

## Key decision

**Wrap the LiteLLM Python SDK** for provider routing and base cost calculation. Build wallet identity, prepaid ledger, top-ups, and settlement ourselves. Do not fork the LiteLLM repository.

## Next steps

Aligned with [Implementation Phases](./docs/07-implementation-phases.md):

1. **Phase 6** — `ai-wallet-node` client SDK: `authorize()`, batched in-memory `charge()` with periodic flush to `POST /v1/usage`, clean 402 handling mid-stream — **complete** (see `packages/ai-wallet-node/`)
2. **Phase 7** — Stripe Connect batch settlement: nightly CRON, aggregate uncleared USAGE per partner, single transfer, reconcile to `CLEARED`

### Running the billing worker

```powershell
# In-process (dev) — set WORKER_ENABLED=true in .env, then:
docker compose up --build

# Standalone (prod) — one or more replicas:
python -m services.gateway.worker
```
