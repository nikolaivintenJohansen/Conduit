-- Universal AI Wallet — Phase 3: OAuth2/OIDC + app installs (Task 2 / Stage 3)
-- Extends 001_initial.sql. Apply after 001_initial.sql with your migration tool.
--
-- Money columns stay microdollars (BigInt, $1.00 = 1_000_000) to match the
-- existing ledger; do NOT introduce a parallel microcents namespace.

-- ---------------------------------------------------------------------------
-- Extend app_registrations
-- ---------------------------------------------------------------------------
ALTER TABLE app_registrations
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS logo_url TEXT;

-- ---------------------------------------------------------------------------
-- Extend app_installs with allowance accounting
-- ---------------------------------------------------------------------------
ALTER TABLE app_installs
    ADD COLUMN IF NOT EXISTS allowance_spent_microdollars BIGINT NOT NULL DEFAULT 0
        CHECK (allowance_spent_microdollars >= 0),
    ADD COLUMN IF NOT EXISTS allowance_reset_period TEXT NOT NULL DEFAULT 'monthly'
        CHECK (allowance_reset_period IN ('monthly', 'lifetime')),
    ADD COLUMN IF NOT EXISTS last_reset_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS display_name TEXT;

CREATE INDEX IF NOT EXISTS app_installs_user_active_idx
    ON app_installs (user_id)
    WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------------
-- OAuth2 authorization codes (Authorization Code + PKCE flow)
-- ---------------------------------------------------------------------------
CREATE TABLE oauth_authorization_codes (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id                   TEXT NOT NULL,  -- app_registrations.client_id (no FK: tolerant of rotation)
    app_registration_id         UUID REFERENCES app_registrations(id) ON DELETE CASCADE,
    user_id                     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_install_id              UUID REFERENCES app_installs(id) ON DELETE SET NULL,
    code_hash                   TEXT NOT NULL UNIQUE,
    redirect_uri                TEXT NOT NULL,
    scopes                      TEXT[] NOT NULL DEFAULT ARRAY['wallet:charge', 'profile:read'],
    pkce_code_challenge         TEXT,
    pkce_code_challenge_method  TEXT NOT NULL DEFAULT 'S256'
                                CHECK (pkce_code_challenge_method IN ('S256', 'plain')),
    expires_at                  TIMESTAMPTZ NOT NULL,
    used_at                     TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX oauth_codes_client_idx ON oauth_authorization_codes (client_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- OAuth2 refresh tokens (rotating, revocable)
-- ---------------------------------------------------------------------------
CREATE TABLE oauth_refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       TEXT NOT NULL,
    app_registration_id UUID REFERENCES app_registrations(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_install_id  UUID REFERENCES app_installs(id) ON DELETE SET NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    scopes          TEXT[] NOT NULL DEFAULT ARRAY['wallet:charge', 'profile:read'],
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    replaced_by_id  UUID REFERENCES oauth_refresh_tokens(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX oauth_refresh_install_idx
    ON oauth_refresh_tokens (app_install_id)
    WHERE revoked_at IS NULL;

CREATE INDEX oauth_refresh_user_idx
    ON oauth_refresh_tokens (user_id, created_at DESC);
