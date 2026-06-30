# Conduit — Stripe-modeled SPA for the AI Wallet

Frontend-only React + TanStack Start SPA in Conduit blues (#0061D5 / #0084FF). All data comes from the existing FastAPI backend at `VITE_API_BASE_URL` (default same-origin). No backend code, no Lovable Cloud.

## Design system (`src/styles.css` + primitives)

- Tailwind v4 `@theme` tokens: `--color-brand-primary #0061D5`, `--color-brand-secondary #0084FF`, `--color-ink #0A2540`, `--color-muted` cool gray, `--color-surface #FFFFFF`, `--color-surface-alt #F6F9FC`, `--color-hairline` cool light gray, `--color-ink-dark #0A1F3D` for dark code surfaces.
- Gradient/glow utilities blending the two blues for hero halo blobs + button sheens; soft shadow + hairline border tokens for cards.
- Inter via `<link>` in `__root.tsx`; JetBrains Mono for money/keys/IDs.
- `RingMark` inline SVG: two interlocked rings (outer #0061D5, inner #0084FF, semi-transparent over-under). Used as nav logo, favicon (SVG), auth/empty-state corner mark. Wordmark = Inter semibold "Conduit" sitting next to it — single-component swap when the HK Modular vector arrives.
- Shared primitives: `Button` (primary/secondary/ghost/dark pill), `Card` (hairline + soft shadow + hover-lift), `Field` (floating label), `Table` (tight, striped-on-hover, right-aligned monospace numbers), `Badge`, `CopyButton`, `DarkCodeBlock` (high-contrast for one-time key reveal), `HaloBackground`, `StickyNav` (blurs on scroll), `Sonner` toaster, `MoneyCell` (formats microdollars).

## Routes (file-based)

**Public marketing** (each route owns its own `head()` — title, description, og:title, og:description; og:image only at leaves with a hero)
- `/` — hero ("One wallet. Every AI app."), Fund→Connect→Use, alternating product mockup sections, big stat callouts, trusted-by logo wall, dual CTAs.
- `/developers` — partner pitch with dark code snippets.
- `/pricing`, `/security`, `/docs` landing stubs.

**Auth**
- `/auth` — login/register tabs → `POST /wallet/v1/auth/{login,register}`; "Continue with Google" → `GET /wallet/v1/auth/oauth/google`; OAuth callback handler at `/auth/google/callback` → `POST /wallet/v1/auth/oauth/google/callback`. Stores JWT in `localStorage.uaw_jwt`, redirects to `?redirect=` or `/dashboard`. Maps `email_taken` (409) and `invalid_credentials` (401) to inline form errors.

**Authed dashboard** (`_authenticated/` layout — sidebar: Overview · Usage · Transactions · API Keys · Access Groups · Connected Apps · Settings; topbar with user email + Sign out; `beforeLoad` redirects to `/auth?redirect=...` when no JWT; root data from `GET /wallet/v1/me`)
- `/dashboard` — balance hero card (big formatted USD, available/held sub-line, monthly spend + cap progress, low-balance banner), top-up card (amount input + $5/$10/$25/$50/$100 chips → `POST /wallet/v1/topups/checkout` with `Idempotency-Key`, `window.location = checkout_url`), spend controls card (`PATCH /wallet/v1/wallet/settings`), usage-by-model summary derived from recent usage.
- `/dashboard/usage` — `useInfiniteQuery` on `GET /wallet/v1/usage?limit=20&cursor=...`, Time · Model · Tokens (in/out) · Cost, "Load more".
- `/dashboard/transactions` — `useInfiniteQuery` on `GET /wallet/v1/wallet/transactions`, entry-type color coding (DEPOSIT/USAGE/REFUND/SETTLEMENT), Time · Type · Amount · Balance after.
- `/dashboard/keys` — list/create/rotate/revoke; new/rotated plaintext key shown once in a dark reveal modal with `CopyButton` + warning; list shows only `key_prefix`; `PATCH` to change access group.
- `/dashboard/access-groups` — CRUD over `/wallet/v1/access-groups`; model picker fed by `GET /wallet/v1/models`.
- `/dashboard/apps` — Connected apps from `GET /wallet/v1/apps`: name, cap, allowance progress bar, reset period; `PATCH` cap; `DELETE` revoke.
- `/dashboard/settings` — profile + "Partner mode" panel: paste `X-Partner-Admin-Token` → `localStorage.uaw_partner_token`, plus partner_slug input. Cleared on logout.

**OAuth consent (standalone, no dashboard chrome — same path the backend uses so partner redirect URIs keep working)**
- `/oauth/consent` — reads `client_id`, `redirect_uri`, `response_type`, `state`, `scope`, `code_challenge`, `code_challenge_method` from search params; reads JWT from `localStorage.uaw_jwt` (falling back to `?token=` query for the backend-hosted-origin case); calls `GET /oauth/authorize` for descriptor; renders "Connect {app_name} to AI Wallet" with scope list (`wallet:charge`, `profile:read`), USD spend cap input, reset period (Monthly/Lifetime); on Approve `POST /oauth/authorize/consent` with `Idempotency-Key` then `window.location = redirect_uri`. If unauthenticated, redirects to `/auth?redirect=<current_consent_url>`.

**Partner area** (gated by stored partner-admin-token + partner_slug)
- `/partner` — register/list/detail/update OAuth clients via `/wallet/v1/partner/{slug}/apps`, rotate-secret modal (one-time reveal), deactivate, plus payout/settlement status views driven by existing settlement endpoints.

**Top-up returns**
- `/wallet/topup/success` — confirmation + link to dashboard, invalidates wallet queries.
- `/wallet/topup/cancel` — retry CTA.

## Shared infrastructure

- `src/lib/api.ts` — fetch wrapper:
  - Base = `import.meta.env.VITE_API_BASE_URL ?? ""`.
  - Attaches `Authorization: Bearer ${uaw_jwt}` when present.
  - Adds `Idempotency-Key: crypto.randomUUID()` on mutating wallet endpoints (`POST /keys`, `POST /keys/{id}/rotate`, `POST /topups/checkout`, `POST /access-groups`, `POST /oauth/authorize/consent`, partner `POST /apps`, `POST /apps/{id}/rotate-secret`).
  - Attaches `X-Partner-Admin-Token` on `/wallet/v1/partner/*` calls.
  - Parses `detail.error.{code,message,request_id}`; maps 401 → clear `uaw_jwt`, cancel queries, redirect to `/auth?redirect=<from>`; 402 (`insufficient_balance`/`allowance_exceeded`), 403 (`model_not_allowed`), 404 (`*_not_found`), 409 (`email_taken`/`app_not_active`), 429 (`rate_limit_exceeded`), 503 (`payments_unavailable`/`google_not_configured`) → friendly Sonner toasts.
- `src/lib/money.ts` — `formatUsd(microdollars: number)` and `toMicro(usd: number) = Math.round(usd * 1_000_000)`. Integers end-to-end; floats only at the input edge.
- `src/lib/auth.ts` — JWT load/save/clear, `useSession()`, logout helper (cancel queries → clear cache → remove `uaw_jwt` + `uaw_partner_token` → navigate to `/auth`).
- TanStack Query in router context (already wired). All reads via `useQuery`/`useInfiniteQuery`; mutations invalidate wallet/usage/transactions keys.

## Technical details

- Stack: TanStack Start + React 19 + Tailwind v4. Pure SPA — no server functions, no Supabase, no Lovable Cloud.
- All money is integer microdollars in state; `MoneyCell` formats at render.
- Cursor pagination everywhere (`next_cursor`); no page numbers.
- Skipping `design--create_directions` — visual direction is fully specified (Stripe-modeled, exact tokens, component patterns).
- README will call out: backend CORS must allow the Lovable preview + published origins; OAuth consent reads JWT from `localStorage.uaw_jwt` and falls back to `?token=` query; all `/oauth/*` calls go through `VITE_API_BASE_URL` with bearer attached.

## Build order

1. Tokens + primitives + `RingMark` + SVG favicon + root sticky-nav/footer layout.
2. Marketing `/`, `/developers`, supporting public routes with per-route meta.
3. API client + session + `_authenticated/` gate + `/auth` (+ Google callback).
4. Dashboard shell + Overview (balance, top-up, spend controls).
5. Usage, Transactions, Keys (with dark one-time reveal), Access Groups, Connected Apps, Settings (+ Partner mode).
6. Top-up success/cancel.
7. Standalone `/oauth/consent`.
8. `/partner` area.