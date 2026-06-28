"""Shared pytest fixtures for Task 11 test harness."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from services.shared.db_sync import create_sync_engine, init_db
from services.shared.models import (
    AccessGroup,
    AccessGroupModel,
    AppInstall,
    AppRegistration,
    ModelCatalog,
    PartnerAccount,
    PriceRule,
    User,
    VirtualKey,
    Wallet,
)
from services.wallet.app_registrations import create_app_registration
from services.wallet.apps import connect_app
from services.wallet.auth import create_user
from services.wallet.keys import generate_virtual_key
from services.wallet.oauth import create_authorization_code, exchange_code_for_tokens


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://uaw:uaw@localhost:5432/uaw_test",
    )


@pytest.fixture(scope="session")
def db_engine(database_url: str):
    engine = create_sync_engine(database_url)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def sandbox_user(db_session: Session) -> User:
    return create_user(db_session, f"user-{uuid4()}@example.com", "test-password-123")


@pytest.fixture
def sandbox_wallet(db_session: Session, sandbox_user: User) -> Wallet:
    wallet = Wallet(user_id=sandbox_user.id, balance_microdollars=5_000_000)
    db_session.add(wallet)
    db_session.flush()
    return wallet


@pytest.fixture
def sandbox_key(db_session: Session, sandbox_user: User, settings_env) -> tuple[VirtualKey, str]:
    generated = generate_virtual_key()
    vkey = VirtualKey(
        user_id=sandbox_user.id,
        name="test-key",
        key_prefix=generated.prefix,
        key_hash=generated.key_hash,
    )
    db_session.add(vkey)
    db_session.flush()
    return vkey, generated.plaintext


@pytest.fixture
def model_catalog(db_session: Session) -> ModelCatalog:
    model = ModelCatalog(
        slug="gpt-4o-mini",
        display_name="GPT-4o Mini",
        provider="openai",
        litellm_model_id="gpt-4o-mini",
    )
    db_session.add(model)
    db_session.flush()
    return model


@pytest.fixture
def restricted_access_group(db_session: Session, model_catalog: ModelCatalog) -> AccessGroup:
    group = AccessGroup(name="restricted", description="single model group")
    db_session.add(group)
    db_session.flush()
    db_session.add(AccessGroupModel(access_group_id=group.id, model_id=model_catalog.id))
    db_session.flush()
    return group


@pytest.fixture
def partner_with_pricing(db_session: Session, model_catalog: ModelCatalog) -> PartnerAccount:
    partner = PartnerAccount(name="Test Partner", slug=f"partner-{uuid4().hex[:8]}")
    db_session.add(partner)
    db_session.flush()
    db_session.add(
        PriceRule(
            partner_account_id=partner.id,
            model_id=model_catalog.id,
            markup_bps=1000,
            price_per_m_input_microdollars=200_000,
            price_per_m_output_microdollars=800_000,
            effective_from=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.flush()
    return partner


@pytest.fixture
def partner_admin_headers() -> dict[str, str]:
    return {"X-Partner-Admin-Token": "test-partner-admin"}


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch):
    from services.shared.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("KEY_HASH_PEPPER", "test-pepper")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("PARTNER_ADMIN_SECRET", "test-partner-admin")
    yield
    get_settings.cache_clear()


@pytest.fixture
def app_registration(db_session: Session, partner_with_pricing: PartnerAccount) -> AppRegistration:
    created = create_app_registration(
        db_session,
        partner_account_id=partner_with_pricing.id,
        name="DelegatedApp",
        redirect_uris=["https://delegated.example.com/cb"],
    )
    return created.record


@pytest.fixture
def connected_app(
    db_session: Session, sandbox_user: User, app_registration: AppRegistration
) -> AppInstall:
    return connect_app(
        db_session,
        user_id=sandbox_user.id,
        client_id=app_registration.client_id,
        spend_limit_microdollars=5_000_000,
        reset_period="monthly",
    )


@pytest.fixture
def app_access_token(
    db_session: Session,
    sandbox_user: User,
    connected_app: AppInstall,
    app_registration: AppRegistration,
) -> str:
    code = create_authorization_code(
        db_session,
        client_id=app_registration.client_id,
        user_id=sandbox_user.id,
        app_install_id=connected_app.id,
        redirect_uri="https://delegated.example.com/cb",
    )
    tokens = exchange_code_for_tokens(
        db_session,
        code=code.code,
        code_verifier=None,
        client_id=app_registration.client_id,
        client_secret=None,
        redirect_uri="https://delegated.example.com/cb",
    )
    return tokens.access_token
