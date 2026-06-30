# LiteLLM Core Audit

Audit of [BerriAI/litellm](https://github.com/BerriAI/litellm) (proxy + SDK) for Conduit.  
**Strategy:** See [ADR-001](./decisions/ADR-001-litellm-strategy.md) — wrap SDK, own wallet layer.

---

## 1. High-level architecture (LiteLLM)

LiteLLM splits into two layers:

```
Client  →  AI Gateway (litellm/proxy/)  →  SDK (litellm/)  →  Provider APIs
```

The **gateway** adds auth, budgets, rate limits, management APIs, and spend logging.  
The **SDK** handles provider calls, format translation, streaming, and cost calculation.

Our product inverts ownership: **we are the gateway**; LiteLLM is the routing engine inside it.

---

## 2. Module map

### 2.1 Gateway (`litellm/proxy/`)

| Module | Responsibility | Action |
|--------|----------------|--------|
| `proxy_server.py` | FastAPI app, `/v1/chat/completions`, management routes | **Reference only** — we build our own FastAPI app |
| `auth/user_api_key_auth.py` | Bearer token → virtual key lookup, budget checks | **Reimplement** — our keys map to wallet users |
| `auth/jwt_auth.py`, `auth/oauth2_*.py` | JWT/OAuth for proxy admin | **Ignore** — we build wallet OAuth (task 2/10) |
| `management_endpoints/key_management_endpoints.py` | `/key/generate`, `/key/info` | **Reimplement** — wallet API issues keys |
| `management_endpoints/team_endpoints.py` | Teams, team budgets | **Defer** — org/team wallets are post-MVP |
| `management_endpoints/internal_user_endpoints.py` | Proxy users | **Ignore** — our `users` table |
| `hooks/max_budget_limiter.py` | Block when key budget exhausted | **Adapt pattern** — check prepaid `wallets.balance` |
| `hooks/parallel_request_limiter_v3.py` | RPM/TPM in Redis | **Reimplement** — same semantics, our Redis keys |
| `hooks/proxy_track_cost_callback.py` | Async spend write | **Reimplement** — write `usage_events` + ledger |
| `db/db_spend_update_writer.py` | Batch spend to Postgres | **Reference** — our async settlement worker |
| `schema.prisma` | Keys, teams, spend logs | **Do not use** — our `schemas/001_initial.sql` |
| `health_endpoints/` | Liveness/readiness | **Wrap** — add wallet + DB health to our app |
| `pass_through_endpoints/` | Provider-native routes | **Later** — MVP is OpenAI-compatible only |

### 2.2 SDK (`litellm/` root)

| Module | Responsibility | Action |
|--------|----------------|--------|
| `main.py` | `completion()`, `acompletion()`, `embedding()` | **Use directly** |
| `router.py` | Load balance, fallback, cooldowns | **Use directly** via `Router` |
| `router_strategy/` | `simple_shuffle`, `lowest_latency`, etc. | **Use** — MVP: primary + failover |
| `cost_calculator.py` | Token → USD base cost | **Use** — feeds pricing engine |
| `llms/{provider}/chat/transformation.py` | OpenAI ↔ provider format | **Use** — no changes |
| `llms/custom_httpx/llm_http_handler.py` | HTTP to providers | **Use** |
| `caching/` | Response cache, Redis | **Optional later** — not MVP |
| `integrations/` | Langfuse, Datadog callbacks | **Optional** — task 12 observability |
| `models/`, `repositories/` | Prisma entity layer | **Ignore** |

### 2.3 Enterprise-only (not in our path)

- Organizations + org admins
- SSO/SAML for proxy admin
- Some guardrails and advanced analytics

We implement partner admin and SSO on our own timeline (tasks 9b, Stage 5).

---

## 3. Request lifecycle comparison

### LiteLLM proxy (reference)

1. `user_api_key_auth` — key in Redis/DB, budget on key
2. `parallel_request_limiter` — RPM/TPM
3. `route_request` → `litellm.acompletion`
4. Cost in `_hidden_params["response_cost"]`
5. Async: increment key/team/user spend in DB

### AI Wallet gateway (ours)

1. **Auth** — `sk-conduit-*` → `virtual_keys` (Redis cache → Postgres)
2. **Entitlement** — access group allows model (task 6; MVP: allow-all)
3. **Balance** — `wallets.available_balance >= estimated_max` or reject 402
4. **Rate limit** — RPM/TPM per key (Redis)
5. **Route** — `litellm.Router.acompletion`
6. **Respond** — stream/return to client immediately
7. **Async settle** — compute price → ledger deduct (idempotent on `request_id`)

Critical difference: LiteLLM decrements an abstract **key budget**; we decrement **prepaid wallet balance** with holds and refunds.

---

## 4. Extension points we use

### 4.1 CustomLogger / pre-call hooks (pattern)

LiteLLM documents `async_pre_call_hook` for modifying or rejecting requests before the provider call. We implement equivalent **FastAPI middleware / dependency** that:

- Injects `metadata.wallet_user_id`, `metadata.request_id`
- Rejects insufficient balance before provider spend

If we later embed LiteLLM proxy for a subset of routes, register a `CustomLogger` subclass.

### 4.2 Custom pricing

LiteLLM supports `model_info.input_cost_per_token` in config. We **do not** rely on this for user-facing price — our **pricing engine** (task 5) computes:

```
user_price = base_cost + partner_markup + platform_fee
```

LiteLLM `response_cost` = **base_cost** input only.

### 4.3 Router configuration

```python
# Illustrative — not production code
Router(
    model_list=[
        {
            "model_name": "gpt-4o",
            "litellm_params": {
                "model": "openai/gpt-4o",
                "api_key": os.environ["OPENAI_API_KEY"],
            },
        },
        {
            "model_name": "gpt-4o",
            "litellm_params": {
                "model": "anthropic/claude-3-5-sonnet-20241022",
                "api_key": os.environ["ANTHROPIC_API_KEY"],
            },
        },
    ],
    fallbacks=[{"gpt-4o": ["claude-3-5-sonnet"]}],
)
```

Model list eventually loaded from DB (`provider_deployments`).

---

## 5. Minimum files to study (spike checklist)

For engineers onboarding:

| Priority | Path | Why |
|----------|------|-----|
| P0 | `ARCHITECTURE.md` (upstream) | Request flow diagram |
| P0 | `proxy/auth/user_api_key_auth.py` | Key validation pattern |
| P0 | `router.py` | Routing + fallbacks |
| P0 | `cost_calculator.py` | Base cost |
| P1 | `proxy/hooks/parallel_request_limiter_v3.py` | Rate limits |
| P1 | `proxy/db/db_spend_update_writer.py` | Async spend batching |
| P2 | `docs/proxy/access_groups` (website) | Entitlement model |

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| LiteLLM breaking changes | Pin version in `requirements.txt`; integration tests with mock provider |
| Cost map stale vs provider invoice | Periodic sync job; allow manual `model_pricing` overrides in DB |
| Double-charge on retry | Idempotency key on every completion `request_id` |
| Balance race at scale | Row-level lock on wallet + hold table; optimistic for read-heavy paths |

---

## 7. Exit criteria (Task 1)

- [x] Module map with fork/wrap/reimplement per area
- [x] ADR locked: wrap SDK
- [x] Request lifecycle documented for wallet semantics
- [x] Extension points identified for balance + pricing
