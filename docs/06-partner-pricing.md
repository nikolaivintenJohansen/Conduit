# Partner Pricing Model

How usage cost flows from provider invoice → user charge → revenue split.

---

## 1. Formula

For each completed request:

```
base_cost       = litellm.completion_cost(tokens, model)     # provider cost
partner_markup  = f(price_rules, base_cost, tokens)        # partner margin
platform_fee    = f(platform_fee_bps, base_cost + markup)    # our fee
─────────────────────────────────────────────────────────────
user_charge     = base_cost + partner_markup + platform_fee
```

**MVP simplification:** `partner_markup = 0`, `platform_fee = 0` — user pays `base_cost` only (pass-through pricing). Tables exist from day one so Stage 2 is additive.

---

## 2. Units

| Unit | Storage |
|------|---------|
| Money | Integer **microdollars** (1 USD = 1,000,000) |
| Rates | Basis points (bps); 100 bps = 1% |
| Tokens | Integer counts from provider `usage` |

Per-1M-token list prices in `price_rules`:

```
input_cost  = (input_tokens / 1_000_000) * price_per_m_input_microdollars
output_cost = (output_tokens / 1_000_000) * price_per_m_output_microdollars
```

If `price_per_m_*` is null, fall back to `markup_bps` on top of `base_cost`.

---

## 3. Price rule resolution

```
resolve_price(user, model, at_time):
  1. partner = user.partner_account_id OR platform_default
  2. rule = SELECT FROM price_rules
            WHERE partner_account_id = partner
              AND model_id = model
              AND effective_from <= at_time
              AND (effective_to IS NULL OR effective_to > at_time)
            ORDER BY effective_from DESC
            LIMIT 1
  3. if no rule → use model_catalog default base pricing (0 markup)
```

---

## 4. Revenue allocation (per usage_event)

Stored on `usage_events` for reconciliation:

| Field | Meaning |
|-------|---------|
| `base_cost_microdollars` | What we pay provider (estimated) |
| `partner_margin_microdollars` | Partner keeps |
| `platform_fee_microdollars` | Platform keeps |
| `charged_microdollars` | User paid (sum of above) |

**Invariant:** `charged = base + partner_margin + platform_fee`

---

## 5. Example (Stage 2)

GPT-4o call: 1,000 input + 500 output tokens.

| Component | Calculation | Amount |
|-----------|-------------|--------|
| Base (LiteLLM map) | provider rate | $0.0075 |
| Partner markup | 20% of base | $0.0015 |
| Platform fee | 5% of (base+markup) | $0.00045 |
| **User charged** | | **$0.00945** |

Ledger: user debited $0.00945. Partner payout ledger (Stage 4) accrues $0.0015.

---

## 6. Base cost ingestion

| Source | Frequency |
|--------|-----------|
| LiteLLM `model_cost` map | Bundled with SDK version |
| Override in `model_catalog.metadata` | Admin API |
| Provider invoice reconciliation | Weekly job (Stage 4) |

Sync job: compare LiteLLM map version → update `model_catalog` defaults.

---

## 7. Free / zero-cost models

For on-prem or free models:

- Set `base_cost = 0` explicitly
- `price_rules` may still add partner markup for hosted wrappers
- Gateway must not divide by zero on bps calculations

---

## 8. Rounding

- All intermediate math in microdollars (integers)
- `charged = ceil_to_microdollar(computed)` — round up at microdollar boundary favoring platform (document in ToS)
- Display to user: 2 decimal USD

---

## 9. Stage 4: payout ledger (schema extension)

Future table `partner_payout_entries`:

- `partner_account_id`, `period_start`, `period_end`
- `gross_margin_microdollars`, `platform_fee_microdollars`
- `status`: `accrued`, `paid`, `disputed`

Not implemented in MVP — `usage_events` is sufficient for accrual reporting.
