from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.db import get_session_factory
from services.shared.models import Session as UserSession
from services.shared.models import User, Wallet
from services.wallet.auth import get_valid_session
from services.wallet.ledger import get_wallet_by_user_id

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _decode_user_id(token: str) -> UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "invalid_token", "message": "Missing subject"}},
            )
        return UUID(sub)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "Invalid or expired token"}},
        ) from exc


def _decode_token_payload(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "Invalid or expired token"}},
        ) from exc


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Bearer token required"}},
        )
    return _decode_user_id(credentials.credentials)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UserSession:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Bearer token required"}},
        )

    payload = _decode_token_payload(credentials.credentials)
    sub = payload.get("sub")
    sid = payload.get("sid")
    if not sub or not sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "Invalid session token"}},
        )

    try:
        user_id = UUID(sub)
        session_id = UUID(sid)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "Invalid session token"}},
        ) from exc

    user_session = get_valid_session(db, session_id, user_id)
    if user_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "Session expired or revoked"}},
        )
    return user_session


def get_current_user(
    user_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(select(User).where(User.id == user_session.user_id, User.status == "active"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_token", "message": "User not found"}},
        )
    return user


def get_current_wallet(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Wallet:
    wallet = get_wallet_by_user_id(db, user.id)
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "wallet_not_found", "message": "Wallet not found"}},
        )
    return wallet
