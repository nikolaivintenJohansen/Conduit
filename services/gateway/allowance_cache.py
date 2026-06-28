"""Redis-backed per-app allowance cache (Phase 3 fast path).

The gateway must decide whether an app-scoped request fits the user's per-app
spend cap in under ~5ms, so it reads allowance state from Redis — never from
PostgreSQL — on the hot path. PostgreSQL remains the source of truth; this
cache is a hot read-side projection that is:

  * populated on install / allowance update / revoke (see services/wallet/apps.py)
  * incremented in-line with the settle transaction (see services/gateway/service.py)
  * re-populated from the DB on a cache miss (see services/gateway/access.py)

State is stored as a Redis HASH so `HINCRBY` on `allowance_spent` is atomic.
When Redis is unavailable we fall back to an in-memory dict, mirroring
services/gateway/rate_limit.py.
"""

from __future__ import annotations

import redis
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import AppInstall

_redis_client: redis.Redis | None = None
_memory: dict[str, dict[str, str]] = {}


def _key(app_install_id) -> str:
    return f"uaw:appallow:{app_install_id}"


def _get_redis() -> redis.Redis | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return client
    except Exception:
        return None


def get_allowance_state(app_install_id) -> dict | None:
    """Return {spend_limit_microdollars, allowance_spent_microdollars, revoked} or None on miss."""
    key = _key(app_install_id)
    client = _get_redis()
    if client is not None:
        raw = client.hgetall(key)
        if not raw:
            return None
        return _coerce(raw)
    state = _memory.get(key)
    return _coerce(state) if state else None


def _coerce(raw: dict) -> dict:
    spend = raw.get("spend_limit_microdollars")
    return {
        "spend_limit_microdollars": int(spend) if spend not in (None, "", "None") else None,
        "allowance_spent_microdollars": int(raw.get("allowance_spent_microdollars", 0)),
        "revoked": raw.get("revoked", "0") == "1",
    }


def set_allowance_state(
    app_install_id,
    *,
    spend_limit_microdollars: int | None,
    allowance_spent_microdollars: int,
    revoked: bool,
) -> None:
    key = _key(app_install_id)
    fields = {
        "spend_limit_microdollars": ""
        if spend_limit_microdollars is None
        else str(spend_limit_microdollars),
        "allowance_spent_microdollars": str(allowance_spent_microdollars),
        "revoked": "1" if revoked else "0",
    }
    client = _get_redis()
    if client is not None:
        client.hset(key, mapping=fields)
    else:
        _memory[key] = fields


def increment_allowance_spent(app_install_id, delta_microdollars: int) -> None:
    if delta_microdollars == 0:
        return
    key = _key(app_install_id)
    client = _get_redis()
    if client is not None:
        client.hincrby(key, "allowance_spent_microdollars", delta_microdollars)
    elif key in _memory:
        _memory[key]["allowance_spent_microdollars"] = str(
            int(_memory[key].get("allowance_spent_microdollars", 0)) + delta_microdollars
        )


def delete_allowance_state(app_install_id) -> None:
    key = _key(app_install_id)
    client = _get_redis()
    if client is not None:
        client.delete(key)
    else:
        _memory.pop(key, None)


def reset_allowance_cache() -> None:
    global _redis_client
    _memory.clear()
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


def load_state_from_db(session: Session, app_install_id) -> dict | None:
    install = session.get(AppInstall, app_install_id)
    if install is None:
        return None
    state = {
        "spend_limit_microdollars": install.spend_limit_microdollars,
        "allowance_spent_microdollars": install.allowance_spent_microdollars,
        "revoked": install.revoked_at is not None,
    }
    set_allowance_state(app_install_id, **state)
    return state
