# Universal AI Wallet — Foundation Docs (Task 1)

Stage 0 deliverables. Everything downstream (tasks 2–12) should align with these documents.

| Doc | Purpose |
|-----|---------|
| [../README.md](../README.md) | Project overview, technical blueprint, and Cursor import guide |
| [07-implementation-phases.md](./07-implementation-phases.md) | **7-phase build order** with repo status and exit criteria |
| [01-litellm-audit.md](./01-litellm-audit.md) | LiteLLM module map; fork / wrap / reimplement per area |
| [02-architecture.md](./02-architecture.md) | System diagram, request lifecycle, service boundaries |
| [03-data-model.md](./03-data-model.md) | Entities, relationships, invariants |
| [04-api-contracts.md](./04-api-contracts.md) | Gateway + wallet/auth API surface |
| [05-security-model.md](./05-security-model.md) | Keys, PCI boundary, audit, idempotency |
| [06-partner-pricing.md](./06-partner-pricing.md) | Base cost + markup + platform fee |
| [decisions/ADR-001-litellm-strategy.md](./decisions/ADR-001-litellm-strategy.md) | Locked decision: wrap LiteLLM SDK, own wallet layer |

## Artifacts

| Path | Purpose |
|------|---------|
| [../schemas/001_initial.sql](../schemas/001_initial.sql) | PostgreSQL schema (source of truth for migrations) |
| [../openapi/wallet-api.yaml](../openapi/wallet-api.yaml) | Wallet, auth, balance, keys |
| [../openapi/gateway.yaml](../openapi/gateway.yaml) | OpenAI-compatible gateway subset |

## Decision summary (read this first)

**Wrap LiteLLM SDK; do not fork the LiteLLM repository.**

- Use `litellm` (pip) for provider routing, translation, cost calculation, and failover.
- Build wallet identity, prepaid ledger, top-ups, partner pricing, and settlement ourselves.
- Mirror LiteLLM *patterns* (virtual keys, access groups, request lifecycle) in our schema — do not reuse LiteLLM's Prisma tables or multi-tenant org model.

## MVP request lifecycle

```
Client → Gateway (our FastAPI) → auth key → balance check → rate limit → litellm.Router → provider
                                                                              ↓
                                                         async: meter usage → ledger deduct
```

## Next tasks unlocked

After reviewing and signing off on these docs:

1. **Task 2** — identity layer against `users`, `sessions`, `virtual_keys`
2. **Task 3** — ledger against `wallets`, `ledger_entries`, `balance_holds`
3. **Task 11 / 12** — scaffold repo layout under `services/gateway`, `services/wallet`, `docker-compose`
