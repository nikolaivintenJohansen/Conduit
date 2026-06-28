# Implementation Phases

Step-by-step build order for AI Wallet. Phases are **sequential** — each unlocks the next. Blueprint model names map to this repo's schema in [03-data-model.md](./03-data-model.md).

| Blueprint model | Repo table(s) |
|-----------------|---------------|
| **User** | `users` + `wallets` (balance on wallet, not user row) |
| **AppConnection** | `app_installs` (+ `spend_limit_microdollars`, `revoked_at`) |
| **Transaction** | `ledger_entries` (+ `usage_events` for metering detail) |
| **AI_Application** | `partner_accounts` + `app_registrations` |

All money columns use **BigInt microdollars** (`$1.00 = 1_000_000`). Product docs may say "micro-cents"; same integer scale, no floats.

---

## Phase 1: The Immutable Ledger (Database & ORM)

Build the financial ledger first — flawless money storage before usage calculation.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 1.1 | Initialize PostgreSQL | **Done** | `docker-compose.yml`, `schemas/001_initial.sql` |
| 1.2 | Core models: User, AppConnection, Transaction, AI_Application | **Done** (mapped names) | `schemas/001_initial.sql`, `services/shared/models.py` |
| 1.3 | Enforce micro-integer amounts (BigInt, no floats) | **Done** | All `*_microdollars` columns |
| 1.4 | Append-only ledger (insert-only corrections) | **Done** | `ledger_entries`; refunds via new `credit` rows |
| 1.5 | CRUD: fetch balances, append transactions | **Done** | `services/wallet/ledger.py`, `services/wallet/balance.py` |

**Exit criteria:** Atomic credit/debit with idempotency keys; balance never goes negative; monthly/key spend limits enforced.

---

## Phase 2: Inbound Gateway (Adding Funds)

Users deposit into the central **master pool** before connecting AI apps.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 2.1 | Stripe Checkout (or Elements) deposit flow | **Done** | `services/wallet/payments.py`, `services/app/wallet/topups_routes.py` |
| 2.2 | Master pool / FBO account separation | **Planned** | Stripe Treasury or platform balance — configure in production |
| 2.3 | Webhook: `payment_intent.succeeded` (and Checkout completion) | **Done** | `POST /wallet/v1/topups/webhook` |
| 2.4 | On webhook: insert DEPOSIT (`credit`) + update balance | **Done** | `handle_stripe_webhook_event()` → `credit_wallet()` |

**Exit criteria:** User tops up $20+ via Checkout; webhook credits wallet once (idempotent); ledger shows `credit` entry.

---

## Phase 3: The Handshake & Identity Layer (Auth)

"MetaMask for AI" — users approve per-app spending limits.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 3.1 | Connect UI (secure popup / consent) | **Done** | `services/app/wallet/oauth_routes.py` (authorize/consent), `services/app/dashboard/static/consent.html` |
| 3.2 | Cryptographic verification (OAuth2 Authorization Code + PKCE) | **Done** | `services/wallet/oauth.py` (PKCE S256, rotating refresh tokens) |
| 3.3 | Allowance endpoint → `AppConnection` with spend limit | **Done** | `services/wallet/apps.py`, `services/app/wallet/apps_routes.py` (`/wallet/v1/apps`) |
| 3.4 | Short-lived JWT / session token (`userId` + `appId`) | **Done** | `services/wallet/oauth.py` (access/id/refresh tokens, `app_install_id` claim); Google login in `services/wallet/google_oauth.py` |

**Exit criteria:** User connects app via consent flow, sets $5 cap → backend issues access/id/refresh tokens; partner app calls `/v1/chat/completions` with the delegated token, debits wallet and increments `app_installs.allowance_spent_microdollars`; allowance exceeded → gateway `402`; user revokes app → gateway `401`; Google login produces a wallet session identical in shape to email/password. Verified by `tests/integration/test_oauth_api.py`, `tests/integration/test_apps_api.py`, `tests/integration/test_google_login_api.py`, `tests/integration/test_gateway_delegated.py`.

---

## Phase 4: The Ingestion Engine (The Fast Path)

Decouple fast token streaming from slow database writes.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 4.1 | Redis ultra-fast cache | **Done** | `services/shared/redis_client.py`, health check |
| 4.2 | `POST /api/wallet/authorize` — Redis balance + allowance, &lt;5ms budget, 200 or 402 | **Not started** | Gateway does sync balance/hold today; dedicated authorize route TBD |
| 4.3 | Durable message broker (Kafka, RabbitMQ, or Redis Streams) | **Not started** | MVP uses sync/async in-process metering |
| 4.4 | Usage endpoint: fire-and-forget push to queue | **Partial** | `services/app/wallet/usage_routes.py` — direct path, no queue yet |

**Exit criteria:** Authorize returns in &lt;5ms from Redis; usage POST returns 202 immediately; events land in queue.

---

## Phase 5: The Billing Worker (The Slow Path)

Background engine: raw tokens → financial charges → immutable ledger.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 5.1 | Queue consumer (background worker) | **Not started** | Reference: LiteLLM `db_spend_update_writer` pattern |
| 5.2 | Rating: base token cost + application markup | **Done** | `services/pricing/engine.py`, `services/gateway/billing.py` |
| 5.3 | Atomic write: deduct balance, update allowance, insert USAGE | **Done** (sync path) | `services/wallet/ledger.py`, `services/gateway/service.py` |
| 5.4 | Limiter: zero balance/allowance → block Redis pre-auth | **Partial** | DB limits enforced; Redis session block TBD |

**Exit criteria:** Worker drains queue without duplicate charges; allowance and wallet stay consistent under concurrency.

---

## Phase 6: The Client SDK (`ai-wallet-node`)

Smart meter package for AI developers.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 6.1 | Node.js / TypeScript package scaffold | **Not started** | Target: `packages/ai-wallet-node` or separate repo |
| 6.2 | `wallet.authorize()` → pre-auth endpoint | **Not started** | See [README SDK example](../README.md#5-developer-integration--sdk) |
| 6.3 | `wallet.charge()` — in-memory batch, periodic flush to ingestion API | **Not started** | Fire-and-forget; no blocking on main thread |
| 6.4 | Clear `402 Payment Required` errors mid-stream | **Not started** | Apps freeze compute when funds exhausted |

**Exit criteria:** Partner app integrates SDK in &lt;30 lines; usage batches every N seconds; 402 stops LLM calls cleanly.

---

## Phase 7: Batch Settlement (Outbound Payouts)

Bulk payouts to avoid per-micro-transaction card fees.

| Step | Requirement | Repo status | Location |
|------|-------------|-------------|----------|
| 7.1 | Stripe Connect onboarding; store `stripe_connect_id` | **Partial** | `partner_accounts.stripe_connect_id` column exists |
| 7.2 | CRON (nightly UTC midnight) | **Not started** | `scripts/` or worker service |
| 7.3 | Aggregate uncleared USAGE per AI application | **Not started** | Add `settlement_status` on usage/ledger when built |
| 7.4 | Single Stripe Connect transfer per partner batch | **Not started** | Stage 4 — see `ai_wallet_tasks.txt` task 8 |
| 7.5 | Reconcile: mark transactions `CLEARED` | **Not started** | Idempotent payout + ledger `settlement` entries |

**Exit criteria:** Nightly job pays Cursor $15,400 from aggregated usage; no double payout; audit trail links transfer to rows.

---

## Phase dependency graph

```
Phase 1 (Ledger)
    └── Phase 2 (Deposits)
            └── Phase 3 (Auth / Connect)
                    └── Phase 4 (Fast path / Redis + queue)
                            └── Phase 5 (Billing worker)
                                    ├── Phase 6 (SDK)
                                    └── Phase 7 (Settlement)
```

## Mapping to engineering tasks

| Phase | `ai_wallet_tasks.txt` |
|-------|------------------------|
| 1 | Task 1 (foundation), Task 3 (ledger) |
| 2 | Task 4 (top-ups / Stripe) |
| 3 | Task 2 (identity), Task 10 (OAuth / apps) |
| 4–5 | Task 7 (gateway), Task 8 (metering) |
| 6 | Task 9 (partner SDK / docs) |
| 7 | Task 8 settlement slice, Stage 4 marketplace |

## Current focus

Per repo status: **Phase 1–3 are complete** (ledger, deposits, OAuth2/OIDC handshake + Google login + delegated-token allowance enforcement); **Phase 4** (dedicated Redis `/authorize` fast-path route + durable message queue) is next, then **Phase 5–7**.
