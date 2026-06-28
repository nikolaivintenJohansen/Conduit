from uuid import uuid4

from services.shared.models import UsageEvent
from services.wallet.balance import check_and_hold
from services.wallet.usage import get_usage_event_by_request_id, list_usage_events, settle_usage


def test_settle_usage_records_event_and_debits(
    db_session, sandbox_wallet, sandbox_user, sandbox_key
):
    vkey, _ = sandbox_key
    request_id = f"req-{uuid4()}"
    before = sandbox_wallet.balance_microdollars

    check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id,
        estimated_max_microdollars=1_000_000,
        virtual_key=vkey,
    )

    result = settle_usage(
        db_session,
        request_id=request_id,
        user_id=sandbox_user.id,
        wallet_id=sandbox_wallet.id,
        model="gpt-4o-mini",
        provider="mock",
        input_tokens=10,
        output_tokens=20,
        base_cost_microdollars=100_000,
        charged_microdollars=100_000,
        virtual_key_id=vkey.id,
        virtual_key=vkey,
    )

    assert result.created
    assert result.usage_event.request_id == request_id
    assert result.usage_event.charged_microdollars == 100_000
    assert sandbox_wallet.balance_microdollars == before - 100_000
    assert result.settle_result.debit.entry.reference_type == "usage_event"
    assert result.settle_result.debit.entry.reference_id == result.usage_event.id


def test_settle_usage_idempotent(db_session, sandbox_wallet, sandbox_user, sandbox_key):
    vkey, _ = sandbox_key
    request_id = f"req-{uuid4()}"

    check_and_hold(
        db_session,
        sandbox_wallet.id,
        request_id,
        estimated_max_microdollars=500_000,
        virtual_key=vkey,
    )

    kwargs = dict(
        request_id=request_id,
        user_id=sandbox_user.id,
        wallet_id=sandbox_wallet.id,
        model="gpt-4o-mini",
        provider="mock",
        input_tokens=5,
        output_tokens=5,
        base_cost_microdollars=50_000,
        charged_microdollars=50_000,
        virtual_key_id=vkey.id,
        virtual_key=vkey,
    )

    first = settle_usage(db_session, **kwargs)
    before = sandbox_wallet.balance_microdollars
    second = settle_usage(db_session, **kwargs)

    assert first.created
    assert not second.created
    assert first.usage_event.id == second.usage_event.id
    assert sandbox_wallet.balance_microdollars == before
    assert db_session.query(UsageEvent).filter_by(request_id=request_id).count() == 1


def test_list_usage_events_pagination(db_session, sandbox_wallet, sandbox_user, sandbox_key):
    vkey, _ = sandbox_key

    for index in range(3):
        request_id = f"req-page-{index}"
        check_and_hold(
            db_session,
            sandbox_wallet.id,
            request_id,
            estimated_max_microdollars=200_000,
            virtual_key=vkey,
        )
        settle_usage(
            db_session,
            request_id=request_id,
            user_id=sandbox_user.id,
            wallet_id=sandbox_wallet.id,
            model="gpt-4o-mini",
            provider="mock",
            input_tokens=1,
            output_tokens=1,
            base_cost_microdollars=10_000,
            charged_microdollars=10_000,
            virtual_key_id=vkey.id,
            virtual_key=vkey,
        )

    page = list_usage_events(db_session, sandbox_user.id, limit=2)
    assert len(page.events) == 2
    assert page.next_cursor is not None

    page2 = list_usage_events(db_session, sandbox_user.id, limit=2, cursor=page.next_cursor)
    assert len(page2.events) == 1


def test_get_usage_event_by_request_id(db_session, sandbox_wallet, sandbox_user, sandbox_key):
    vkey, _ = sandbox_key
    request_id = f"req-lookup-{uuid4()}"

    check_and_hold(db_session, sandbox_wallet.id, request_id, 300_000, virtual_key=vkey)
    settle_usage(
        db_session,
        request_id=request_id,
        user_id=sandbox_user.id,
        wallet_id=sandbox_wallet.id,
        model="gpt-4o-mini",
        provider="mock",
        input_tokens=2,
        output_tokens=2,
        base_cost_microdollars=20_000,
        charged_microdollars=20_000,
        virtual_key_id=vkey.id,
        virtual_key=vkey,
    )

    event = get_usage_event_by_request_id(db_session, request_id)
    assert event is not None
    assert event.model == "gpt-4o-mini"
