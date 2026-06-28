import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped["Wallet"] = relationship(back_populates="user", uselist=False)
    virtual_keys: Mapped[list["VirtualKey"]] = relationship(back_populates="user")


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_sub"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_sub: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    balance_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    held_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    spend_limit_microdollars: Mapped[int | None] = mapped_column(BigInteger)
    low_balance_threshold_microdollars: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1_000_000
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="wallet")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="wallet")
    balance_holds: Mapped[list["BalanceHold"]] = relationship(back_populates="wallet")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("wallet_id", "idempotency_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    amount_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped[Wallet] = relationship(back_populates="ledger_entries")


class BalanceHold(Base):
    __tablename__ = "balance_holds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    estimated_max_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    wallet: Mapped[Wallet] = relationship(back_populates="balance_holds")


class AccessGroup(Base):
    __tablename__ = "access_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    models: Mapped[list["AccessGroupModel"]] = relationship(
        back_populates="access_group", cascade="all, delete-orphan"
    )


class ModelCatalog(Base):
    __tablename__ = "model_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    litellm_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessGroupModel(Base):
    __tablename__ = "access_group_models"

    access_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("access_groups.id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_catalog.id", ondelete="CASCADE"), primary_key=True
    )

    access_group: Mapped[AccessGroup] = relationship(back_populates="models")
    model: Mapped[ModelCatalog] = relationship()


class VirtualKey(Base):
    __tablename__ = "virtual_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    partner_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_accounts.id", ondelete="SET NULL")
    )
    access_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("access_groups.id"))
    name: Mapped[str | None] = mapped_column(Text)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    rpm_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    tpm_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100_000)
    budget_microdollars: Mapped[int | None] = mapped_column(BigInteger)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="virtual_keys")
    partner_account: Mapped["PartnerAccount | None"] = relationship()
    access_group: Mapped[AccessGroup | None] = relationship()


class PartnerAccount(Base):
    __tablename__ = "partner_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    default_platform_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    stripe_connect_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceRule(Base):
    __tablename__ = "price_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_accounts.id"), nullable=False
    )
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_catalog.id"), nullable=False)
    markup_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_per_m_input_microdollars: Mapped[int | None] = mapped_column(BigInteger)
    price_per_m_output_microdollars: Mapped[int | None] = mapped_column(BigInteger)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(Text, unique=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(Text, unique=True)
    amount_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ledger_entries.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    virtual_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("virtual_keys.id"))
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_cost_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    charged_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    platform_fee_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    partner_margin_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    partner_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("partner_accounts.id"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppRegistration(Base):
    __tablename__ = "app_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_accounts.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    client_secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=["wallet:charge", "profile:read"]
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    logo_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppInstall(Base):
    __tablename__ = "app_installs"
    __table_args__ = (UniqueConstraint("user_id", "app_registration_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    app_registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_registrations.id"), nullable=False
    )
    spend_limit_microdollars: Mapped[int | None] = mapped_column(BigInteger)
    allowance_spent_microdollars: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    allowance_reset_period: Mapped[str] = mapped_column(String, nullable=False, default="monthly")
    last_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    app_registration: Mapped[AppRegistration] = relationship()


class OAuthAuthorizationCode(Base):
    __tablename__ = "oauth_authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    app_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_registrations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    app_install_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_installs.id", ondelete="SET NULL")
    )
    code_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=["wallet:charge", "profile:read"]
    )
    pkce_code_challenge: Mapped[str | None] = mapped_column(Text)
    pkce_code_challenge_method: Mapped[str] = mapped_column(String, nullable=False, default="S256")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthRefreshToken(Base):
    __tablename__ = "oauth_refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    app_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_registrations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    app_install_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_installs.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=["wallet:charge", "profile:read"]
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("oauth_refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
