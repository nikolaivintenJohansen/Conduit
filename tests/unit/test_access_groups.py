from services.gateway.access import AccessDeniedError, enforce_model_access, is_model_allowed
from services.shared.models import VirtualKey


def test_allow_all_when_no_access_group(db_session, sandbox_user, model_catalog):
    vkey = VirtualKey(user_id=sandbox_user.id, key_prefix="sk-conduit-test", key_hash="abc")
    db_session.add(vkey)
    db_session.flush()

    assert is_model_allowed(db_session, None, model_catalog.slug)
    enforce_model_access(db_session, vkey, model_catalog.slug)


def test_access_group_allows_member_model(
    db_session, sandbox_user, restricted_access_group, model_catalog
):
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        access_group_id=restricted_access_group.id,
        key_prefix="sk-conduit-test",
        key_hash="abc",
    )
    db_session.add(vkey)
    db_session.flush()

    assert is_model_allowed(db_session, restricted_access_group.id, model_catalog.slug)
    enforce_model_access(db_session, vkey, model_catalog.slug)


def test_access_group_denies_other_models(db_session, sandbox_user, restricted_access_group):
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        access_group_id=restricted_access_group.id,
        key_prefix="sk-conduit-test",
        key_hash="abc",
    )
    db_session.add(vkey)
    db_session.flush()

    assert not is_model_allowed(db_session, restricted_access_group.id, "gpt-4o")

    try:
        enforce_model_access(db_session, vkey, "gpt-4o")
        raised = False
    except AccessDeniedError:
        raised = True

    assert raised
