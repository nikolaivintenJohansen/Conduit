# ADR-001: LiteLLM Integration Strategy

**Status:** Accepted  
**Date:** 2026-06-26  
**Context:** Task 1 — Stage 0 foundation

## Decision

**Wrap the LiteLLM Python SDK as a library dependency. Do not fork the LiteLLM repository.**

Build a first-party **AI Wallet Gateway** (FastAPI) that owns authentication, prepaid balance, metering, and settlement. Delegate provider I/O to `litellm.Router` and `litellm.completion_cost()`.

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Fork LiteLLM proxy** | Full gateway UI, key mgmt, routing out of box | Massive codebase (~16k lines in proxy_server alone); Prisma schema tied to their user/team/org model; enterprise features gated; merge burden | Reject |
| **Run LiteLLM proxy as-is + sidecar** | Fastest spike | Their virtual keys ≠ wallet keys; spend tracked in their DB not our ledger; hard to inject prepaid balance semantics | Reject for production |
| **Wrap SDK + own gateway** | Clean boundaries; we own wallet schema; reuse 100+ provider adapters | Must implement key validation, rate limits, access groups ourselves (patterns are well documented) | **Accept** |
| **Reimplement routing from scratch** | Total control | Rebuild provider translation layer LiteLLM already maintains | Reject |

## What we take from LiteLLM

| Capability | LiteLLM source | How we use it |
|------------|----------------|---------------|
| Provider routing & failover | `litellm.Router`, `router_strategy/` | Configure `model_list` from our DB or config |
| Request/response translation | `litellm/llms/{provider}/` | Transparent via SDK |
| Base cost calculation | `cost_calculator.py`, model cost map | Input to our pricing engine |
| Rate limit *patterns* | `proxy/hooks/parallel_request_limiter_v3.py` | Reimplement against Redis using same RPM/TPM semantics |
| Virtual key *pattern* | `proxy/auth/user_api_key_auth.py` | Our `virtual_keys` table + cache, not their `LiteLLM_VerificationToken` |
| Access group *pattern* | Access Groups docs + model access | Our `access_groups` + `access_group_models` tables |
| Async usage logging *pattern* | `db/db_spend_update_writer.py` | Our async pipeline writes to `usage_events` + ledger |

## What we build (differentiation)

- Wallet identity (email/OAuth → Stage 3 OIDC)
- Prepaid balance, holds, idempotent deductions
- Stripe top-ups and webhook crediting
- Partner pricing (base + markup + platform fee)
- Cross-app consent and delegated auth
- Settlement and partner payout ledger (Stage 4)

## Dependency boundary

```
pip install litellm   # SDK only — we do NOT ship litellm/proxy as our entrypoint
```

Provider API keys live in environment / secrets manager, never exposed to end users. Users receive `sk-uaw-...` virtual keys issued by our wallet service.

## Consequences

- **Positive:** Single PostgreSQL schema we control; no Prisma coupling; clear MVP path.
- **Positive:** LiteLLM upgrades are `pip` bumps, not merge conflicts.
- **Negative:** No LiteLLM Admin UI for free — we build dashboard (tasks 9a/9b).
- **Negative:** Must implement Redis-backed rate limits and key cache (well-scoped, ~1 week).

## Review trigger

Revisit if any of these become true:

- LiteLLM exposes a stable plugin API for external ledger backends
- We need >50 provider-specific proxy endpoints beyond OpenAI-compatible `/v1/chat/completions`
- Team size cannot maintain our gateway layer
