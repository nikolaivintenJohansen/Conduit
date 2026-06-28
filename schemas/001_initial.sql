-- Universal AI Wallet — initial schema (Task 1)
-- Apply with your migration tool of choice (Alembic, dbmate, etc.)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Users & identity
-- ---------------------------------------------------------------------------

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    password_hash   TEXT,
    display_name    TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'deleted')),
    email_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE TABLE oauth_identities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    provider_sub    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT oauth_identities_provider_unique UNIQUE (provider, provider_sub)
);

CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);

-- ---------------------------------------------------------------------------
-- Wallets & ledger
-- ---------------------------------------------------------------------------

CREATE TABLE wallets (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    balance_microdollars              BIGINT NOT NULL DEFAULT 0 CHECK (balance_microdollars >= 0),
    held_microdollars               BIGINT NOT NULL DEFAULT 0 CHECK (held_microdollars >= 0),
    spend_limit_microdollars          BIGINT,
    low_balance_threshold_microdollars BIGINT NOT NULL DEFAULT 1000000, -- $1.00
    currency                        CHAR(3) NOT NULL DEFAULT 'USD',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT wallets_user_unique UNIQUE (user_id)
);

CREATE TABLE ledger_entries (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_id               UUID NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
    entry_type              TEXT NOT NULL
                            CHECK (entry_type IN (
                                'credit', 'debit', 'hold', 'hold_release',
                                'refund', 'adjustment'
                            )),
    amount_microdollars     BIGINT NOT NULL CHECK (amount_microdollars > 0),
    -- Signed effect on balance is implied by entry_type
    balance_after_microdollars BIGINT NOT NULL,
    idempotency_key         TEXT NOT NULL,
    reference_type          TEXT,  -- e.g. usage_event, payment_intent, admin
    reference_id            UUID,
    metadata                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ledger_idempotency_unique UNIQUE (wallet_id, idempotency_key)
);

CREATE INDEX ledger_wallet_created_idx ON ledger_entries (wallet_id, created_at DESC);

CREATE TABLE balance_holds (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_id                   UUID NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
    request_id                  TEXT NOT NULL,
    estimated_max_microdollars  BIGINT NOT NULL CHECK (estimated_max_microdollars > 0),
    status                      TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'settled', 'released', 'expired')),
    expires_at                  TIMESTAMPTZ NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled_at                  TIMESTAMPTZ,
    CONSTRAINT balance_holds_request_unique UNIQUE (request_id)
);

CREATE INDEX balance_holds_wallet_active_idx
    ON balance_holds (wallet_id)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- Virtual keys & access control
-- ---------------------------------------------------------------------------

CREATE TABLE access_groups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE model_catalog (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                TEXT NOT NULL UNIQUE,
    display_name        TEXT NOT NULL,
    provider            TEXT NOT NULL,
    litellm_model_id    TEXT NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE access_group_models (
    access_group_id     UUID NOT NULL REFERENCES access_groups(id) ON DELETE CASCADE,
    model_id            UUID NOT NULL REFERENCES model_catalog(id) ON DELETE CASCADE,
    PRIMARY KEY (access_group_id, model_id)
);

CREATE TABLE virtual_keys (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_group_id     UUID REFERENCES access_groups(id) ON DELETE SET NULL,
    name                TEXT,
    key_prefix          TEXT NOT NULL,
    key_hash            TEXT NOT NULL UNIQUE,
    rpm_limit           INTEGER NOT NULL DEFAULT 60,
    tpm_limit           INTEGER NOT NULL DEFAULT 100000,
    budget_microdollars BIGINT,
    last_used_at        TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX virtual_keys_user_id_idx ON virtual_keys (user_id);

-- ---------------------------------------------------------------------------
-- Usage & metering
-- ---------------------------------------------------------------------------

CREATE TABLE usage_events (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id                  TEXT NOT NULL UNIQUE,
    user_id                     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    virtual_key_id              UUID REFERENCES virtual_keys(id) ON DELETE SET NULL,
    wallet_id                   UUID NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
    model                       TEXT NOT NULL,
    provider                    TEXT,
    input_tokens                INTEGER NOT NULL DEFAULT 0,
    output_tokens               INTEGER NOT NULL DEFAULT 0,
    base_cost_microdollars      BIGINT NOT NULL DEFAULT 0,
    charged_microdollars        BIGINT NOT NULL DEFAULT 0,
    platform_fee_microdollars   BIGINT NOT NULL DEFAULT 0,
    partner_margin_microdollars BIGINT NOT NULL DEFAULT 0,
    partner_account_id          UUID,
    latency_ms                  INTEGER,
    status                      TEXT NOT NULL DEFAULT 'completed'
                                CHECK (status IN ('completed', 'failed', 'blocked')),
    metadata                    JSONB NOT NULL DEFAULT '{}',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX usage_events_user_created_idx ON usage_events (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Partner pricing (Stage 2 — tables present early to avoid migrations)
-- ---------------------------------------------------------------------------

CREATE TABLE partner_accounts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL,
    slug                    TEXT NOT NULL UNIQUE,
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'suspended')),
    default_platform_fee_bps INTEGER NOT NULL DEFAULT 500, -- 5%
    stripe_connect_id       TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE usage_events
    ADD CONSTRAINT usage_events_partner_fk
    FOREIGN KEY (partner_account_id) REFERENCES partner_accounts(id) ON DELETE SET NULL;

CREATE TABLE price_rules (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_account_id              UUID NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
    model_id                        UUID NOT NULL REFERENCES model_catalog(id) ON DELETE CASCADE,
    markup_bps                      INTEGER NOT NULL DEFAULT 0,
    price_per_m_input_microdollars  BIGINT,
    price_per_m_output_microdollars BIGINT,
    effective_from                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to                    TIMESTAMPTZ,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX price_rules_lookup_idx
    ON price_rules (partner_account_id, model_id, effective_from DESC);

ALTER TABLE virtual_keys
    ADD COLUMN partner_account_id UUID REFERENCES partner_accounts(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- Payments (Stripe)
-- ---------------------------------------------------------------------------

CREATE TABLE payment_intents (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wallet_id                   UUID NOT NULL REFERENCES wallets(id) ON DELETE RESTRICT,
    stripe_checkout_session_id  TEXT UNIQUE,
    stripe_payment_intent_id    TEXT UNIQUE,
    amount_microdollars         BIGINT NOT NULL CHECK (amount_microdollars > 0),
    status                      TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'succeeded', 'failed', 'canceled')),
    idempotency_key             TEXT NOT NULL UNIQUE,
    ledger_entry_id             UUID REFERENCES ledger_entries(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- OAuth apps (Stage 3)
-- ---------------------------------------------------------------------------

CREATE TABLE app_registrations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_account_id  UUID NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    client_id           TEXT NOT NULL UNIQUE,
    client_secret_hash  TEXT NOT NULL,
    redirect_uris       TEXT[] NOT NULL,
    scopes              TEXT[] NOT NULL DEFAULT ARRAY['wallet:charge', 'profile:read'],
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app_installs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_registration_id         UUID NOT NULL REFERENCES app_registrations(id) ON DELETE CASCADE,
    spend_limit_microdollars    BIGINT,
    consented_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at                  TIMESTAMPTZ,
    CONSTRAINT app_installs_unique UNIQUE (user_id, app_registration_id)
);

-- ---------------------------------------------------------------------------
-- Audit log
-- ---------------------------------------------------------------------------

CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_id     UUID,
    ip_address      INET,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX audit_log_created_idx ON audit_log (created_at DESC);
