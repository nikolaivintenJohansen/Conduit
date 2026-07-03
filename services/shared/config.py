from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql://conduit:conduit@localhost:5432/conduit",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    jwt_secret: str = Field(default="change-me-in-production", alias="JWT_SECRET")
    jwt_expiry_seconds: int = Field(default=3600, alias="JWT_EXPIRY_SECONDS")
    key_hash_pepper: str = Field(default="change-me-in-production", alias="KEY_HASH_PEPPER")

    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_checkout_success_url: str = Field(
        default="http://localhost:8000/wallet/topup/success",
        alias="STRIPE_CHECKOUT_SUCCESS_URL",
    )
    stripe_checkout_cancel_url: str = Field(
        default="http://localhost:8000/wallet/topup/cancel",
        alias="STRIPE_CHECKOUT_CANCEL_URL",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # OAuth2 / OIDC (Phase 3)
    oidc_issuer: str = Field(default="http://localhost:8000", alias="OIDC_ISSUER")
    oauth_code_expiry_seconds: int = Field(default=120, alias="OAUTH_CODE_EXPIRY_SECONDS")
    oauth_access_token_expiry_seconds: int = Field(
        default=3600, alias="OAUTH_ACCESS_TOKEN_EXPIRY_SECONDS"
    )
    oauth_refresh_token_expiry_seconds: int = Field(
        default=30 * 24 * 3600, alias="OAUTH_REFRESH_TOKEN_EXPIRY_SECONDS"
    )
    oauth_default_scopes: str = Field(
        default="wallet:charge profile:read", alias="OAUTH_DEFAULT_SCOPES"
    )

    # Google login (wallet signup/in)
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_oauth_redirect_url: str = Field(
        default="http://localhost:8000/wallet/v1/auth/oauth/google/callback",
        alias="GOOGLE_OAUTH_REDIRECT_URL",
    )

    default_rpm_limit: int = Field(default=60, alias="DEFAULT_RPM_LIMIT")
    default_tpm_limit: int = Field(default=100_000, alias="DEFAULT_TPM_LIMIT")
    hold_expiry_seconds: int = Field(default=300, alias="HOLD_EXPIRY_SECONDS")
    partner_admin_secret: str = Field(
        default="change-me-partner-admin",
        alias="PARTNER_ADMIN_SECRET",
    )

    # Phase 4 — ingestion engine (Redis fast path + durable stream)
    usage_stream_name: str = Field(default="conduit:usage:events", alias="USAGE_STREAM_NAME")
    usage_consumer_group: str = Field(default="billing", alias="USAGE_CONSUMER_GROUP")
    usage_consumer_name: str = Field(default="worker-1", alias="USAGE_CONSUMER_NAME")
    usage_idempotency_ttl_seconds: int = Field(
        default=86_400, alias="USAGE_IDEMPOTENCY_TTL_SECONDS"
    )
    worker_enabled: bool = Field(default=False, alias="WORKER_ENABLED")
    worker_poll_ms: int = Field(default=1000, alias="WORKER_POLL_MS")
    worker_max_batch: int = Field(default=50, alias="WORKER_MAX_BATCH")

    # Phase 5 hardening — balance-cache revalidation + worker DLQ
    balance_cache_ttl_seconds: int = Field(default=3600, alias="BALANCE_CACHE_TTL_SECONDS")
    balance_cache_stale_seconds: int = Field(default=60, alias="BALANCE_CACHE_STALE_SECONDS")
    balance_cache_revalidate_interval_ms: int = Field(
        default=30_000, alias="BALANCE_CACHE_REVALIDATE_INTERVAL_MS"
    )
    worker_max_delivery_attempts: int = Field(default=5, alias="WORKER_MAX_DELIVERY_ATTEMPTS")
    worker_claim_idle_ms: int = Field(default=60_000, alias="WORKER_CLAIM_IDLE_MS")
    usage_dlq_stream_name: str = Field(default="conduit:usage:dlq", alias="USAGE_DLQ_STREAM_NAME")

    # Phase 7 — batch settlement (Stripe Connect payouts)
    settlement_enabled: bool = Field(default=False, alias="SETTLEMENT_ENABLED")
    settlement_cron: str = Field(default="0 0 * * *", alias="SETTLEMENT_CRON")
    settlement_min_payout_microdollars: int = Field(
        default=1_000_000, alias="SETTLEMENT_MIN_PAYOUT_MICRODOLLARS"
    )
    settlement_lookback_days: int = Field(default=0, alias="SETTLEMENT_LOOKBACK_DAYS")
    settlement_platform_wallet_id: str | None = Field(
        default=None, alias="SETTLEMENT_PLATFORM_WALLET_ID"
    )
    settlement_poll_interval_seconds: float = Field(
        default=3600.0, alias="SETTLEMENT_POLL_INTERVAL_SECONDS"
    )

    # CORS — comma-separated list of origins allowed to call the API from a browser
    # (e.g. the Conduit-website frontend). Default covers local dev only.
    cors_allowed_origins: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"),
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def database_url_async(self) -> str:
        url = self.database_url
        if "+psycopg" in url:
            return url.replace("+psycopg", "+asyncpg", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "staging"}

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
