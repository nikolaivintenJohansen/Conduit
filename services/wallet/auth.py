from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import bcrypt
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import OAuthIdentity, User
from services.shared.models import Session as UserSession
from services.wallet.keys import hash_key


@dataclass(frozen=True)
class AuthResult:
    user: User
    session: UserSession
    jwt_token: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.lower()))


def create_user(
    session: Session, email: str, password: str, display_name: str | None = None
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    stmt = select(User).where(User.email == email.lower(), User.status == "active")
    user = session.scalar(stmt)
    if user is None or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_session(session: Session, user: User) -> AuthResult:
    settings = get_settings()
    raw_token = str(uuid4())
    token_hash = hash_key(raw_token, pepper=settings.jwt_secret)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.jwt_expiry_seconds)

    user_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(user_session)
    session.flush()

    jwt_token = jwt.encode(
        {"sub": str(user.id), "sid": str(user_session.id), "exp": expires_at},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return AuthResult(user=user, session=user_session, jwt_token=jwt_token)


def get_valid_session(session: Session, session_id: UUID, user_id: UUID) -> UserSession | None:
    return session.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.expires_at > datetime.now(UTC),
        )
    )


def invalidate_session(session: Session, user_session: UserSession) -> None:
    user_session.expires_at = datetime.now(UTC)
    session.flush()


def get_oauth_identity(session: Session, provider: str, provider_sub: str) -> OAuthIdentity | None:
    return session.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_sub == provider_sub,
        )
    )


def get_or_create_oauth_user(
    session: Session,
    *,
    provider: str,
    provider_sub: str,
    email: str,
    display_name: str | None = None,
) -> User:
    """Find a user by OAuth identity, or create one. Idempotent on (provider, provider_sub)."""
    existing = get_oauth_identity(session, provider, provider_sub)
    if existing is not None:
        return session.get_one(User, existing.user_id)

    # Link to an existing email account if one exists; otherwise create a new user.
    user = get_user_by_email(session, email)
    if user is None:
        user = User(
            email=email.lower(),
            password_hash=None,
            display_name=display_name,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        session.flush()

    identity = OAuthIdentity(
        user_id=user.id,
        provider=provider,
        provider_sub=provider_sub,
    )
    session.add(identity)
    session.flush()
    return user
