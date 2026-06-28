-- Sandbox reference data (Task 11) — no secrets; run scripts/seed_sandbox.py for demo keys.

INSERT INTO access_groups (id, name, description)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    'sandbox-basic',
    'Allows gpt-4o-mini only'
) ON CONFLICT DO NOTHING;

INSERT INTO model_catalog (id, slug, display_name, provider, litellm_model_id)
VALUES
    ('44444444-4444-4444-8444-444444444401', 'gpt-4o-mini', 'GPT-4o Mini', 'openai', 'gpt-4o-mini'),
    ('44444444-4444-4444-8444-444444444402', 'gpt-4o', 'GPT-4o', 'openai', 'gpt-4o'),
    ('44444444-4444-4444-8444-444444444403', 'claude-3-5-sonnet', 'Claude 3.5 Sonnet', 'anthropic', 'claude-3-5-sonnet')
ON CONFLICT DO NOTHING;

INSERT INTO access_group_models (access_group_id, model_id)
VALUES ('33333333-3333-4333-8333-333333333333', '44444444-4444-4444-8444-444444444401')
ON CONFLICT DO NOTHING;

INSERT INTO partner_accounts (id, name, slug, default_platform_fee_bps)
VALUES (
    '55555555-5555-4555-8555-555555555555',
    'Sandbox Partner',
    'sandbox-partner',
    500
) ON CONFLICT DO NOTHING;

INSERT INTO price_rules (
    id,
    partner_account_id,
    model_id,
    markup_bps,
    price_per_m_input_microdollars,
    price_per_m_output_microdollars
)
VALUES (
    '66666666-6666-4666-8666-666666666666',
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444401',
    1000,
    200000,
    800000
) ON CONFLICT DO NOTHING;
