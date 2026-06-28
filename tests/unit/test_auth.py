from services.wallet.auth import (
    authenticate_user,
    create_user,
    get_valid_session,
    invalidate_session,
    issue_session,
    verify_password,
)
from services.wallet.keys import (
    create_user_virtual_key,
    list_user_virtual_keys,
    resolve_virtual_key,
    revoke_virtual_key,
    rotate_virtual_key,
    verify_key,
)


def test_create_user_and_authenticate(db_session, settings_env):
    user = create_user(db_session, "auth@example.com", "secure-pass-99")
    db_session.flush()

    assert verify_password("secure-pass-99", user.password_hash)
    assert authenticate_user(db_session, "auth@example.com", "secure-pass-99") == user
    assert authenticate_user(db_session, "auth@example.com", "wrong") is None


def test_issue_session_returns_jwt(db_session, settings_env):
    user = create_user(db_session, "session@example.com", "secure-pass-99")
    result = issue_session(db_session, user)

    assert result.user.id == user.id
    assert result.jwt_token
    assert result.session.user_id == user.id


def test_virtual_key_resolution(db_session, sandbox_key, settings_env):
    vkey, plaintext = sandbox_key

    assert verify_key(plaintext, vkey.key_hash)
    resolved = resolve_virtual_key(db_session, plaintext)
    assert resolved is not None
    assert resolved.id == vkey.id


def test_revoked_key_not_resolved(db_session, sandbox_key):
    vkey, plaintext = sandbox_key
    from datetime import UTC, datetime

    vkey.revoked_at = datetime.now(UTC)
    db_session.flush()

    assert resolve_virtual_key(db_session, plaintext) is None


def test_session_invalidation(db_session, settings_env):
    user = create_user(db_session, "invalidate@example.com", "secure-pass-99")
    result = issue_session(db_session, user)

    assert get_valid_session(db_session, result.session.id, user.id) is not None
    invalidate_session(db_session, result.session)
    assert get_valid_session(db_session, result.session.id, user.id) is None


def test_virtual_key_management(db_session, sandbox_user, settings_env):
    created = create_user_virtual_key(db_session, sandbox_user.id, name="primary")
    assert created.plaintext.startswith("sk-uaw-")
    assert verify_key(created.plaintext, created.record.key_hash)

    keys = list_user_virtual_keys(db_session, sandbox_user.id)
    assert len(keys) == 1

    rotated = rotate_virtual_key(db_session, sandbox_user.id, created.record.id)
    assert rotated is not None
    assert rotated.record.id != created.record.id
    assert resolve_virtual_key(db_session, created.plaintext) is None

    revoked = revoke_virtual_key(db_session, sandbox_user.id, rotated.record.id)
    assert revoked is not None
    assert revoked.revoked_at is not None
