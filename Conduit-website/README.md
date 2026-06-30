# Conduit SPA

Frontend-only React + TanStack Start app for the Conduit AI wallet. All data comes from the existing FastAPI backend; no server code in this repo.

## Configuration

Set the API base URL via an env var (optional — defaults to same-origin):

```
VITE_API_BASE_URL=https://api.conduit.example
```

## Backend requirements

Because the SPA lives on a Lovable origin (different from the FastAPI origin), the backend must:

1. **CORS** — allow the Lovable preview origin (e.g. `https://id-preview--<id>.lovable.app`) and the published origin, with credentials/headers including `Authorization`, `Content-Type`, `Idempotency-Key`, and `X-Partner-Admin-Token`.
2. **OAuth consent** — partner `redirect_uri`s point at `/oauth/consent`. This SPA serves that route. The JWT is read from `localStorage.uaw_jwt` and (as a fallback for backend-hosted flows) from a `?token=` query parameter.
3. **Top-up returns** — Stripe Checkout should redirect to `/wallet/topup/success` and `/wallet/topup/cancel` on the SPA origin.

## Conventions

- Money is integer microdollars end-to-end. `formatUsd(micro)` / `toMicro(usd)` in `src/lib/money.ts`.
- All mutating wallet calls send `Idempotency-Key: <uuid>`.
- Cursor pagination (`next_cursor` + `useInfiniteQuery`) — no page numbers.
- 401 → clear `uaw_jwt`, cancel queries, redirect to `/auth?redirect=<from>`.
- Partner admin actions attach `X-Partner-Admin-Token` from `localStorage.uaw_partner_token`.
