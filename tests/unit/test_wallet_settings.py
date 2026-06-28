from services.wallet.balance import update_wallet_settings


def test_update_wallet_settings(db_session, sandbox_user):
    summary = update_wallet_settings(
        db_session,
        sandbox_user.id,
        spend_limit_microdollars=2_000_000,
        low_balance_threshold_microdollars=250_000,
    )
    assert summary.spend_limit_microdollars == 2_000_000
    assert summary.low_balance_threshold_microdollars == 250_000


def test_update_wallet_settings_clear_limit(db_session, sandbox_user):
    update_wallet_settings(
        db_session,
        sandbox_user.id,
        spend_limit_microdollars=1_000_000,
    )
    summary = update_wallet_settings(
        db_session,
        sandbox_user.id,
        spend_limit_microdollars=None,
    )
    assert summary.spend_limit_microdollars is None
