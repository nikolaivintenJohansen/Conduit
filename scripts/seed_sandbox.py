#!/usr/bin/env python3
"""Seed sandbox demo user, wallet, and API key for local development."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from services.shared.db_sync import session_scope
from services.shared.models import AccessGroup, User, VirtualKey, Wallet
from services.wallet.auth import create_user, hash_password
from services.wallet.keys import hash_key

SANDBOX_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SANDBOX_WALLET_ID = UUID("22222222-2222-4222-8222-222222222222")
SANDBOX_KEY_ID = UUID("77777777-7777-4777-8777-777777777777")
SANDBOX_ACCESS_GROUP_ID = UUID("33333333-3333-4333-8333-333333333333")

SANDBOX_EMAIL = "sandbox@example.com"
SANDBOX_PASSWORD = "sandbox123"
SANDBOX_API_KEY = "sk-uaw-sandbox00000000000000000000000001"


def _ensure_access_group(session) -> None:
    group = session.get(AccessGroup, SANDBOX_ACCESS_GROUP_ID)
    if group is None:
        session.add(
            AccessGroup(
                id=SANDBOX_ACCESS_GROUP_ID,
                name="sandbox-basic",
                description="Allows gpt-4o-mini only",
            )
        )
        session.flush()


def seed() -> None:
    with session_scope() as session:
        _ensure_access_group(session)

        user = session.get(User, SANDBOX_USER_ID)
        if user is None:
            user = User(
                id=SANDBOX_USER_ID,
                email=SANDBOX_EMAIL,
                password_hash=hash_password(SANDBOX_PASSWORD),
                display_name="Sandbox User",
            )
            session.add(user)
            session.flush()
        else:
            user.password_hash = hash_password(SANDBOX_PASSWORD)

        wallet = session.get(Wallet, SANDBOX_WALLET_ID)
        if wallet is None:
            wallet = Wallet(
                id=SANDBOX_WALLET_ID,
                user_id=user.id,
                balance_microdollars=10_000_000,
            )
            session.add(wallet)
        else:
            wallet.balance_microdollars = 10_000_000

        vkey = session.get(VirtualKey, SANDBOX_KEY_ID)
        key_hash = hash_key(SANDBOX_API_KEY)
        if vkey is None:
            session.add(
                VirtualKey(
                    id=SANDBOX_KEY_ID,
                    user_id=user.id,
                    access_group_id=SANDBOX_ACCESS_GROUP_ID,
                    name="Sandbox Demo Key",
                    key_prefix=SANDBOX_API_KEY[:12],
                    key_hash=key_hash,
                )
            )
        else:
            vkey.key_hash = key_hash
            vkey.revoked_at = None

        existing_email = session.scalar(select(User).where(User.email == SANDBOX_EMAIL))
        if existing_email and existing_email.id != user.id:
            raise RuntimeError("sandbox email already used by another user")

    print("Sandbox seed complete.")
    print(f"  Email:   {SANDBOX_EMAIL}")
    print(f"  Password: {SANDBOX_PASSWORD}")
    print(f"  API key: {SANDBOX_API_KEY}")
    print("  Balance: $10.00")


if __name__ == "__main__":
    seed()
