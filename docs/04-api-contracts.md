# API Contracts

Two public surfaces:

1. **Gateway API** — OpenAI-compatible; authenticated with virtual keys (`sk-uaw-*`)
2. **Wallet API** — Account, balance, keys, top-ups; authenticated with session JWT

OpenAPI files: [`openapi/gateway.yaml`](../openapi/gateway.yaml), [`openapi/wallet-api.yaml`](../openapi/wallet-api.yaml)

---

## 1. Conventions

| Topic | Rule |
|-------|------|
| Base URL (gateway) | `https://api.example.com/v1` |
| Base URL (wallet) | `https://api.example.com/wallet/v1` |
| Gateway auth | `Authorization: Bearer sk-uaw-...` |
| Wallet auth | `Authorization: Bearer <jwt>` or session cookie |
| Idempotency | Header `Idempotency-Key: <uuid>` on mutating wallet endpoints |
| Request tracing | Header `X-Request-Id` echoed in response; gateway generates if missing |
| Money in JSON | Integer microdollars + `"currency": "USD"` |
| Errors | `{ "error": { "code": "...", "message": "...", "request_id": "..." } }` |

---

## 2. Gateway API (MVP)

### POST /v1/chat/completions

OpenAI-compatible. See OpenAPI for full schema.

**Additional behavior (not in OpenAI spec):**

| Header | Purpose |
|--------|---------|
| `Authorization` | Required virtual key |
| `X-Request-Id` | Settlement idempotency (generated if absent) |

**Additional response headers:**

| Header | Purpose |
|--------|---------|
| `X-Request-Id` | For support / usage lookup |
| `X-UAW-Cost-USD` | Charged amount (microdollars as decimal string) |
| `X-UAW-Balance-Remaining-USD` | Optional; wallet balance after charge |

**Error codes:**

| HTTP | `error.code` | When |
|------|--------------|------|
| 401 | `invalid_api_key` | Unknown or revoked key |
| 402 | `insufficient_balance` | Wallet cannot cover request |
| 403 | `model_not_allowed` | Access group denial |
| 429 | `rate_limit_exceeded` | RPM/TPM |
| 502 | `provider_error` | Upstream failure |

### GET /v1/models

List models from `model_catalog` filtered by caller's access group.

### GET /health

```json
{ "status": "ok", "database": "ok", "redis": "ok" }
```

---

## 3. Wallet API (MVP)

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/wallet/v1/auth/register` | Email + password signup |
| POST | `/wallet/v1/auth/login` | Returns JWT |
| POST | `/wallet/v1/auth/logout` | Invalidate session |
| POST | `/wallet/v1/auth/oauth/{provider}` | OAuth callback (Google, etc.) |

**POST /wallet/v1/auth/login** response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "email": "user@example.com"
  }
}
```

### Wallet & balance

| Method | Path | Description |
|--------|------|-------------|
| GET | `/wallet/v1/me` | Profile + wallet summary |
| GET | `/wallet/v1/wallet` | Balance, held, available, thresholds |
| GET | `/wallet/v1/wallet/transactions` | Paginated ledger |
| GET | `/wallet/v1/usage` | Paginated usage events |

**GET /wallet/v1/wallet** response:

```json
{
  "wallet_id": "uuid",
  "balance_microdollars": 5000000,
  "held_microdollars": 0,
  "available_microdollars": 5000000,
  "currency": "USD",
  "low_balance_threshold_microdollars": 1000000
}
```

### Virtual keys

| Method | Path | Description |
|--------|------|-------------|
| GET | `/wallet/v1/keys` | List keys (prefix only) |
| POST | `/wallet/v1/keys` | Create key — **plaintext returned once** |
| POST | `/wallet/v1/keys/{id}/rotate` | Revoke old, issue new |
| DELETE | `/wallet/v1/keys/{id}` | Revoke |

**POST /wallet/v1/keys** request:

```json
{
  "name": "My laptop",
  "rpm_limit": 60,
  "tpm_limit": 100000
}
```

**POST /wallet/v1/keys** response:

```json
{
  "id": "uuid",
  "name": "My laptop",
  "key": "sk-uaw-abc123...",
  "key_prefix": "sk-uaw-abc1",
  "created_at": "2026-06-26T00:00:00Z"
}
```

### Top-ups (task 4)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/wallet/v1/topups/checkout` | Create Stripe Checkout session |
| POST | `/wallet/v1/webhooks/stripe` | Stripe webhook (signature verified) |

---

## 4. Internal service API (not public)

Gateway → Wallet module calls (in-process in MVP; HTTP if split later):

| Operation | Input | Output |
|-----------|-------|--------|
| `resolve_virtual_key` | key hash | `user_id`, `wallet_id`, limits, `access_group_id` |
| `check_and_hold` | `wallet_id`, `request_id`, `estimate` | `hold_id` or error |
| `settle_usage` | `request_id`, token counts, costs | `usage_event_id`, `ledger_entry_id` |
| `release_hold` | `request_id` | void |

---

## 5. OAuth2 / OIDC + Connected Apps (Stage 3 — implemented)

Root-mounted (no `/wallet/v1` prefix) per the OIDC spec.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/.well-known/openid-configuration` | OIDC discovery metadata |
| GET | `/oauth/jwks` | JWKS endpoint (HS256 stub for MVP; RS256 in Stage 5) |
| GET | `/oauth/authorize` | Consent descriptor (requires user session) |
| POST | `/oauth/authorize/consent` | Approve spend cap → issue authorization code + redirect URI |
| POST | `/oauth/token` | `grant_type=authorization_code` (PKCE) or `refresh_token` |
| GET | `/oauth/userinfo` | OIDC UserInfo (Bearer app access token) |
| POST | `/oauth/revoke` | Revoke a refresh token (RFC 7009 minimal) |
| GET | `/oauth/consent` | Hosted consent page (`consent.html`) |

**`POST /oauth/token` (authorization_code)** — form-encoded:

```
grant_type=authorization_code
code=<code>&code_verifier=<verifier>&redirect_uri=<uri>
client_id=<uaw_...>&client_secret=<secret>
```

Response:

```json
{
  "access_token": "eyJ...",
  "id_token": "eyJ...",
  "refresh_token": "opaque-rotating",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "wallet:charge profile:read"
}
```

The `access_token` is a HS256 JWT with claims `sub` (user), `app_install_id`, `scope`, `iss`, `aud` (client_id), `exp`, `typ=access`. Refresh tokens are opaque and **rotate on every use** (revoke old + issue new in one transaction).

### Connected apps (user session)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/wallet/v1/apps` | List connected apps |
| POST | `/wallet/v1/apps/{client_id}/connect` | Connect / set spend cap |
| GET | `/wallet/v1/apps/{install_id}` | App detail |
| PATCH | `/wallet/v1/apps/{install_id}` | Update spend cap |
| DELETE | `/wallet/v1/apps/{install_id}` | Revoke app + refresh tokens |

### Partner app registration (partner-admin)

`X-Partner-Admin-Token` guarded, under `/wallet/v1/partner/{partner_slug}/apps`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `` | Register OAuth client — **`client_secret` returned once** |
| GET | `` | List app registrations |
| GET | `/{registration_id}` | Detail |
| PATCH | `/{registration_id}` | Update name / redirect URIs / active |
| POST | `/{registration_id}/rotate-secret` | Rotate client secret |
| DELETE | `/{registration_id}` | Deactivate |

### Google login

| Method | Path | Description |
|--------|------|-------------|
| GET | `/wallet/v1/auth/oauth/google` | Redirect to Google (state cookie) |
| POST | `/wallet/v1/auth/oauth/google/callback` | Exchange code → wallet session (same shape as email/password) |

### Gateway behavior for delegated app tokens

`POST /v1/chat/completions` accepts **either** `sk-uaw-*` virtual keys **or** OAuth app access tokens. App-scoped requests enforce the per-app spend cap on the Redis fast path (`uaw:appallow:{app_install_id}`) before the provider call.

| HTTP | `error.code` | When |
|------|--------------|------|
| 401 | `app_revoked` | App install revoked or refresh token revoked |
| 402 | `allowance_exceeded` | `allowance_spent + estimate > spend_limit` |

Settle atomically debits the wallet, increments `app_installs.allowance_spent_microdollars` (idempotent on `request_id`), and writes the new total back to Redis.

---

## 6. Versioning

- URL prefix `/v1` — breaking changes bump to `/v2`
- Gateway stays OpenAI-compatible; extensions via `X-UAW-*` headers only
