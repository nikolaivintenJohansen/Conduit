-- Conduit — Phase 7: Batch settlement & Stripe Connect payouts
-- Extends 001_initial.sql and 002_oauth_and_apps.sql. Apply after 002.
--
-- Money columns stay microdollars (BigInt, $1.00 = 1_000_000).

-- ---------------------------------------------------------------------------
-- Extend ledger_entries to record platform-side settlement (payout) movements
-- ---------------------------------------------------------------------------
ALTER TABLE ledger_entries
    DROP CONSTRAINT IF EXISTS ledger_entries_entry_type_check;

ALTER TABLE ledger_entries
    ADD CONSTRAINT ledger_entries_entry_type_check
    CHECK (entry_type IN (
        'credit', 'debit', 'hold', 'hold_release',
        'refund', 'adjustment', 'settlement'
    ));

-- ---------------------------------------------------------------------------
-- Settlement batches (one payout record per partner per period)
-- ---------------------------------------------------------------------------
CREATE TABLE settlement_batches (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_account_id          UUID NOT NULL REFERENCES partner_accounts(id) ON DELETE RESTRICT,
    period_start                TIMESTAMPTZ NOT NULL,
    period_end                  TIMESTAMPTZ NOT NULL,
    gross_usage_microdollars    BIGINT NOT NULL CHECK (gross_usage_microdollars >= 0),
    platform_fee_microdollars   BIGINT NOT NULL CHECK (platform_fee_microdollars >= 0),
    partner_payout_microdollars BIGINT NOT NULL CHECK (partner_payout_microdollars >= 0),
    provider_cost_microdollars  BIGINT NOT NULL CHECK (provider_cost_microdollars >= 0),
    partner_margin_microdollars BIGINT NOT NULL CHECK (partner_margin_microdollars >= 0),
    event_count                 INTEGER NOT NULL CHECK (event_count >= 0),
    reserved_event_ids          UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    status                      TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'cleared', 'failed')),
    stripe_transfer_id          TEXT UNIQUE,
    idempotency_key             TEXT NOT NULL UNIQUE,
    ledger_entry_id             UUID REFERENCES ledger_entries(id),
    error_message               TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    cleared_at                  TIMESTAMPTZ,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX settlement_batches_partner_status_idx
    ON settlement_batches (partner_account_id, status, created_at DESC);

-- ---------------------------------------------------------------------------
-- Track per-event settlement state so payouts never claim an event twice
-- ---------------------------------------------------------------------------
ALTER TABLE usage_events
    ADD COLUMN IF NOT EXISTS settlement_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (settlement_status IN ('pending', 'reserved', 'cleared', 'failed')),
    ADD COLUMN IF NOT EXISTS settlement_batch_id UUID
        REFERENCES settlement_batches(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS usage_events_settlement_idx
    ON usage_events (partner_account_id, settlement_status, created_at);

-- ---------------------------------------------------------------------------
-- Stripe Connect capabilities (Phase 7.1 partner onboarding)
-- ---------------------------------------------------------------------------
ALTER TABLE partner_accounts
    ADD COLUMN IF NOT EXISTS stripe_capabilities JSONB NOT NULL DEFAULT '{}';
