# Security Model

---

## 1. Threat model (MVP scope)

| Asset | Risk | Control |
|-------|------|---------|
| Virtual API keys | Leak → wallet drain | Hash at rest; rotation; rate limits; spend caps |
| User passwords | Credential stuffing | bcrypt/argon2; rate limit login |
| JWT sessions | Theft | Short TTL; httpOnly cookie option; refresh rotation |
| Wallet balance | Race double-spend | Row locks; idempotent settlement |
| Stripe webhooks | Forged credit | Signature verification; idempotent ledger |
| Provider keys | Exposure | Server-side only; never in client responses |
| PII | Breach | Minimize storage; encrypt backups |

Out of MVP scope: SOC2, HSM, multi-region DR — track in Stage 5.

---

## 2. API key storage

Virtual keys use format `sk-uaw-<random>` (prefix identifies product).

| Stage | Handling |
|-------|----------|
| Creation | Generate 32+ bytes CSPRNG; show plaintext **once** in UI |
| Storage | `key_hash = HMAC-SHA256(pepper, plaintext)` |
| Lookup | Hash incoming Bearer token; compare constant-time |
| Display | `key_prefix` only (first 12 chars) |
| Rotation | Revoke old row; new hash; audit log entry |

**Pepper:** `KEY_HASH_PEPPER` in secrets manager, not in git.

LiteLLM stores keys similarly in `LiteLLM_VerificationToken` — we reimplement, not reuse their table.

---

## 3. Authentication boundaries

```
┌─────────────────────────────────────────────────────────────┐
│  PUBLIC INTERNET                                             │
├──────────────────────────┬──────────────────────────────────┤
│  Gateway                  │  Wallet API                       │
│  Bearer: sk-uaw-*         │  Bearer: JWT (user session)       │
│  → virtual_keys           │  → sessions                       │
│  → wallet balance         │  → users                          │
└──────────────────────────┴──────────────────────────────────┘
│  NEVER accepts JWT on gateway for MVP (keys only)           │
│  NEVER accepts sk-uaw-* on wallet mutating routes except     │
│    key self-management via JWT session                        │
└─────────────────────────────────────────────────────────────┘
```

Stage 3: delegated tokens for partner apps — separate `app_install` scoped tokens, not raw wallet keys.

---

## 4. Payment / PCI boundary

| Data | Stored by us? |
|------|----------------|
| Card number | **Never** |
| CVV | **Never** |
| Stripe Customer ID | Yes |
| Stripe PaymentIntent / Checkout Session ID | Yes |
| Top-up amount, status | Yes |

All card capture via **Stripe Checkout** or **Payment Element** hosted by Stripe. Webhooks credit wallet only after `checkout.session.completed` or `payment_intent.succeeded`.

Webhook handler:

1. Verify `Stripe-Signature`
2. Lookup `payment_intents` by Stripe ID
3. If already `succeeded`, return 200 (idempotent)
4. Else credit wallet with `idempotency_key = stripe_event_id`

---

## 5. Idempotency strategy

| Operation | Key | TTL / scope |
|-----------|-----|-------------|
| Ledger credit (top-up) | `stripe_event_id` | Permanent unique |
| Ledger debit (usage) | `request_id` | Permanent unique |
| Balance hold | `request_id` | Unique; expires 5 min |
| Key creation | `Idempotency-Key` header | 24h Redis |
| Stripe checkout create | `Idempotency-Key` | Per user |

**Pattern:** Insert with unique constraint; on conflict return prior result.

---

## 6. Balance concurrency

Settlement path (simplified):

```sql
-- Hold (sync, before provider call)
BEGIN;
SELECT balance_microdollars, held_microdollars FROM wallets WHERE id = $1 FOR UPDATE;
-- check available >= estimate
UPDATE wallets SET held_microdollars = held_microdollars + $estimate WHERE id = $1;
INSERT INTO balance_holds ...;
COMMIT;

-- Settle (async, after response)
BEGIN;
-- compute actual_charge from usage
UPDATE wallets SET
  balance_microdollars = balance_microdollars - actual,
  held_microdollars = held_microdollars - hold_estimate;
INSERT INTO ledger_entries (entry_type = 'debit', idempotency_key = request_id);
UPDATE balance_holds SET status = 'settled';
INSERT INTO usage_events ...;
COMMIT;
```

Over-estimated hold → `hold_release` credit difference.

---

## 7. Audit logging

Write to `audit_log` for:

- Login success/failure (no password in metadata)
- Key create / rotate / revoke
- Top-up completed
- Admin balance adjustment
- App install / revoke (Stage 3)
- Spend limit changes

Retain 90 days minimum; export for compliance in Stage 5.

---

## 8. Rate limiting & abuse

| Layer | Limit |
|-------|-------|
| Login | 10/min per IP |
| Gateway per key | `rpm_limit`, `tpm_limit` from `virtual_keys` |
| Gateway global | Configurable server ceiling |
| Wallet API | 100/min per user |

Redis sliding window; 429 with `Retry-After`.

---

## 9. Secrets management

| Secret | Location |
|--------|----------|
| `DATABASE_URL` | Env / vault |
| `REDIS_URL` | Env / vault |
| `JWT_SECRET` | Env / vault |
| `KEY_HASH_PEPPER` | Env / vault |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Env / vault |
| `OPENAI_API_KEY`, provider keys | Env / vault |

`.env` for local dev only; never commit. See `.env.example`.

---

## 10. Security checklist for MVP launch

- [ ] HTTPS everywhere
- [ ] Keys hashed with pepper
- [ ] JWT expiry ≤ 1 hour
- [ ] Stripe webhook signature verified
- [ ] Idempotency on all money movements
- [ ] `FOR UPDATE` on wallet rows during hold/settle
- [ ] No provider keys in logs
- [ ] Structured logs exclude request bodies by default
