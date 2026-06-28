"""Redis-backed wallet balance projection and fast-path holds (Phase 4 + Phase 5 hardening).

The `/v1/authorize` fast path must decide in under ~5ms whether a request fits
the user's available balance, so it reads balance state from Redis and places a
micro-hold there — never touching PostgreSQL on the hot path. PostgreSQL stays
the source of truth; this cache is a hot read-side projection that is:

  * populated on demand from the DB on a miss (``load_balance_from_db``)
  * refreshed when deposits credit the wallet (``apply_credit``)
  * mutated atomically by the billing worker after settle (``release_hold``,
    ``incr_monthly_spent``)

State model:

  * ``uaw:walletbal:{wallet_id}``  HASH  -> balance_microdollars, held_microdollars,
    spend_limit_microdollars, monthly_spent_microdollars, spend_period, as_of_ms
  * ``uaw:hold:{request_id}``      HASH  -> wallet_id, estimated_max_microdollars,
    model, app_install_id, ... (TTL = hold_expiry_seconds)

``place_hold`` uses a Lua script so the check-and-increment is atomic across
concurrent authorizes. The script also enforces the **wallet monthly spend
limit** (Phase 5 hardening): it returns ``1`` on success, ``0`` when available
balance is insufficient, and ``2`` when ``monthly_spent + estimated`` exceeds
``spend_limit_microdollars``. Callers use ``place_hold_checked`` to distinguish
the two rejection reasons (``InsufficientBalanceError`` vs
``SpendLimitExceededError``).

The billing worker keeps ``monthly_spent_microdollars`` in sync via
``incr_monthly_spent`` after each settle; month rollover is handled atomically
inside the increment Lua (reset to the new charge when ``spend_period`` changes).

Revalidation / eviction (Phase 5 hardening): the balance hash carries an
``as_of_ms`` timestamp and a TTL of ``balance_cache_ttl_seconds`` so an idle
wallet self-evicts. ``get_balance_state`` is a plain read; callers that need
fresh data use ``get_balance_state_revalidating`` which treats entries older
than ``balance_cache_stale_seconds`` as a soft miss and reloads from the DB
**while preserving the live ``held_microdollars`` projection** so in-flight
holds are never lost. ``revalidate_wallet`` is the explicit refresh entry point
used by the periodic sweep and after admin/refund changes.

When Redis is unavailable we fall back to an in-memory dict, mirroring
``services/gateway/rate_limit.py`` and ``allowance_cache.py`` — this keeps the
fast path functional in tests and degraded environments.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import redis
from sqlalchemy.orm import Session

from services.shared.config import get_settings
from services.shared.models import Wallet

_redis_client: redis.Redis | None = None
_mem_balance: dict[str, dict] = {}
_mem_holds: dict[str, dict] = {}

# KEYS[1] = balance hash, KEYS[2] = hold hash
# ARGV[1] = request_id, ARGV[2] = estimated, ARGV[3] = ttl_seconds
# returns 1 success, 0 insufficient balance, 2 monthly spend limit exceeded
_PLACE_HOLD_LUA = """
local bal = tonumber(redis.call('HGET', KEYS[1], 'balance_microdollars') or '0')
local held = tonumber(redis.call('HGET', KEYS[1], 'held_microdollars') or '0')
local estimated = tonumber(ARGV[2])
if (bal - held) < estimated then
  return 0
end
local limit = redis.call('HGET', KEYS[1], 'spend_limit_microdollars')
if limit and limit ~= '' and limit ~= 'None' then
  local spent = tonumber(redis.call('HGET', KEYS[1], 'monthly_spent_microdollars') or '0')
  if (spent + estimated) > tonumber(limit) then
    return 2
  end
end
redis.call('HINCRBY', KEYS[1], 'held_microdollars', estimated)
redis.call('HSET', KEYS[2], 'estimated_max_microdollars', estimated)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]))
return 1
"""

# ARGV[1] = charged microdollars, ARGV[2] = current period (YYYY-MM).
# Resets monthly_spent to `charged` when the cached period differs (month rollover).
_INCR_MONTHLY_LUA = """
local cur = redis.call('HGET', KEYS[1], 'spend_period')
local period = ARGV[2]
local charged = tonumber(ARGV[1])
if cur ~= period then
  redis.call('HSET', KEYS[1], 'monthly_spent_microdollars', charged, 'spend_period', period)
else
  redis.call('HINCRBY', KEYS[1], 'monthly_spent_microdollars', charged)
end
return 1
"""


def _wallet_key(wallet_id) -> str:
    return f"uaw:walletbal:{wallet_id}"


def _hold_key(request_id: str) -> str:
    return f"uaw:hold:{request_id}"


def _current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _now_ms() -> int:
    return int(time.time() * 1000)


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


def _coerce(raw: dict) -> dict:
    spend = raw.get("spend_limit_microdollars")
    period = raw.get("spend_period")
    as_of = raw.get("as_of_ms")
    return {
        "balance_microdollars": int(raw.get("balance_microdollars", 0)),
        "held_microdollars": int(raw.get("held_microdollars", 0)),
        "spend_limit_microdollars": int(spend) if spend not in (None, "", "None") else None,
        "monthly_spent_microdollars": int(raw.get("monthly_spent_microdollars", 0) or 0),
        "spend_period": period if period not in (None, "", "None") else None,
        "as_of_ms": int(as_of) if as_of not in (None, "", "None") else 0,
    }


def get_balance_state(wallet_id) -> dict | None:
    """Return balance/held/spend_limit/monthly_spent dict, or None on a cache miss.

    Does not revalidate; use ``get_balance_state_revalidating`` for fresh data.
    """
    key = _wallet_key(wallet_id)
    client = _get_redis()
    if client is not None:
        raw = client.hgetall(key)
        if not raw:
            return None
        return _coerce(raw)
    state = _mem_balance.get(key)
    return _coerce(state) if state else None


def get_balance_state_revalidating(session: Session, wallet_id) -> dict | None:
    """Like ``get_balance_state`` but reloads from DB when the cache is stale.

    A cached entry older than ``balance_cache_stale_seconds`` is treated as a
    soft miss: authoritative balance/spend-limit/monthly-spent are reloaded from
    Postgres, but the live ``held_microdollars`` projection is preserved so
    in-flight Redis holds are never lost. A hard miss (no cache entry) loads
    fresh state via ``load_balance_from_db``.
    """
    state = get_balance_state(wallet_id)
    if state is None:
        return load_balance_from_db(session, wallet_id)

    settings = get_settings()
    stale_ms = settings.balance_cache_stale_seconds * 1000
    if state["as_of_ms"] and (_now_ms() - state["as_of_ms"]) <= stale_ms:
        return state

    # Stale: reload authoritative fields but keep the live held projection.
    revalidated = revalidate_wallet(session, wallet_id, preserve_held=state["held_microdollars"])
    return revalidated or state


def set_balance_state(
    wallet_id,
    *,
    balance_microdollars: int,
    held_microdollars: int,
    spend_limit_microdollars: int | None,
    monthly_spent_microdollars: int = 0,
    spend_period: str | None = None,
    as_of_ms: int | None = None,
) -> None:
    key = _wallet_key(wallet_id)
    spend = "" if spend_limit_microdollars is None else str(spend_limit_microdollars)
    period = spend_period or _current_period()
    now_ms = as_of_ms if as_of_ms is not None else _now_ms()
    fields = {
        "balance_microdollars": str(balance_microdollars),
        "held_microdollars": str(held_microdollars),
        "spend_limit_microdollars": spend,
        "monthly_spent_microdollars": str(monthly_spent_microdollars),
        "spend_period": period,
        "as_of_ms": str(now_ms),
    }
    client = _get_redis()
    if client is not None:
        client.hset(key, mapping=fields)
        ttl = get_settings().balance_cache_ttl_seconds
        if ttl and ttl > 0:
            client.expire(key, ttl)
    else:
        _mem_balance[key] = {
            "balance_microdollars": balance_microdollars,
            "held_microdollars": held_microdollars,
            "spend_limit_microdollars": (
                spend_limit_microdollars if spend_limit_microdollars is not None else ""
            ),
            "monthly_spent_microdollars": monthly_spent_microdollars,
            "spend_period": period,
            "as_of_ms": now_ms,
        }


def load_balance_from_db(session: Session, wallet_id) -> dict | None:
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        return None
    # Local import avoids a circular dependency at module load time.
    from services.wallet.ledger import monthly_spend_microdollars

    state = {
        "balance_microdollars": wallet.balance_microdollars,
        "held_microdollars": wallet.held_microdollars,
        "spend_limit_microdollars": wallet.spend_limit_microdollars,
        "monthly_spent_microdollars": monthly_spend_microdollars(session, wallet.id),
        "spend_period": _current_period(),
        "as_of_ms": _now_ms(),
    }
    set_balance_state(wallet_id, **state)
    return state


def revalidate_wallet(
    session: Session, wallet_id, *, preserve_held: int | None = None
) -> dict | None:
    """Refresh the cache from Postgres. Preserves the live held projection when
    ``preserve_held`` is provided (the sum of non-expired Redis holds), so
    in-flight holds are not lost during a stale reload.
    """
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        return None
    from services.wallet.ledger import monthly_spend_microdollars

    held = wallet.held_microdollars if preserve_held is None else preserve_held
    state = {
        "balance_microdollars": wallet.balance_microdollars,
        "held_microdollars": held,
        "spend_limit_microdollars": wallet.spend_limit_microdollars,
        "monthly_spent_microdollars": monthly_spend_microdollars(session, wallet.id),
        "spend_period": _current_period(),
        "as_of_ms": _now_ms(),
    }
    set_balance_state(wallet_id, **state)
    return state


def apply_credit(wallet_id, amount_microdollars: int) -> None:
    """Bump the cached balance by a credit amount (deposit webhook)."""
    if amount_microdollars == 0:
        return
    key = _wallet_key(wallet_id)
    client = _get_redis()
    if client is not None:
        client.hincrby(key, "balance_microdollars", amount_microdollars)
        ttl = get_settings().balance_cache_ttl_seconds
        if ttl and ttl > 0:
            client.expire(key, ttl)
    elif key in _mem_balance:
        _mem_balance[key]["balance_microdollars"] = int(
            _mem_balance[key].get("balance_microdollars", 0)
        ) + amount_microdollars


def incr_monthly_spent(wallet_id, charged_microdollars: int) -> None:
    """Add ``charged_microdollars`` to the cached monthly spend, resetting on
    month rollover. Called by the billing worker after a successful settle so
    the fast-path Lua sees an up-to-date ``monthly_spent`` without a DB hit.
    """
    if charged_microdollars == 0:
        return
    key = _wallet_key(wallet_id)
    period = _current_period()
    client = _get_redis()
    if client is not None:
        client.register_script(_INCR_MONTHLY_LUA)(keys=[key], args=[charged_microdollars, period])
        return
    state = _mem_balance.setdefault(
        key,
        {
            "balance_microdollars": 0,
            "held_microdollars": 0,
            "spend_limit_microdollars": "",
            "monthly_spent_microdollars": 0,
            "spend_period": period,
            "as_of_ms": _now_ms(),
        },
    )
    cur_period = state.get("spend_period")
    if cur_period != period:
        state["monthly_spent_microdollars"] = charged_microdollars
        state["spend_period"] = period
    else:
        state["monthly_spent_microdollars"] = int(
            state.get("monthly_spent_microdollars", 0)
        ) + charged_microdollars
    state["as_of_ms"] = _now_ms()


def place_hold(
    wallet_id, request_id: str, estimated_microdollars: int, *, context: dict | None = None
) -> tuple[bool, int, int]:
    """Atomically reserve ``estimated_microdollars`` against available balance.

    Returns ``(ok, held_after, available_after)``. On success a hold record is
    written with a TTL. On any rejection (insufficient balance or monthly spend
    limit exceeded) returns ``(False, ..., ...)`` — use ``place_hold_checked``
    to distinguish the rejection reason.
    """
    ok, held, available, _code = place_hold_checked(
        wallet_id, request_id, estimated_microdollars, context=context
    )
    return ok, held, available


def place_hold_checked(
    wallet_id, request_id: str, estimated_microdollars: int, *, context: dict | None = None
) -> tuple[bool, int, int, str]:
    """Atomic check-and-hold that also enforces the monthly spend limit.

    Returns ``(ok, held_after, available_after, code)`` where ``code`` is one of
    ``"ok"``, ``"insufficient_balance"``, ``"spend_limit_exceeded"``.
    """
    settings = get_settings()
    ttl = settings.hold_expiry_seconds
    wkey = _wallet_key(wallet_id)
    hkey = _hold_key(request_id)

    client = _get_redis()
    if client is not None:
        raw = client.register_script(_PLACE_HOLD_LUA)(
            keys=[wkey, hkey],
            args=[request_id, estimated_microdollars, ttl],
        )
        code_int = int(raw)
        if code_int == 1:
            code = "ok"
            if context:
                fields = {k: str(v) if v is not None else "" for k, v in context.items()}
                fields["estimated_max_microdollars"] = str(estimated_microdollars)
                fields["wallet_id"] = str(wallet_id)
                client.hset(hkey, mapping=fields)
                client.expire(hkey, ttl)
        elif code_int == 2:
            code = "spend_limit_exceeded"
        else:
            code = "insufficient_balance"
        state = _coerce(client.hgetall(wkey))
        held = state["held_microdollars"]
        available = state["balance_microdollars"] - held
        return code_int == 1, held, available, code

    # In-memory fallback (tests / degraded).
    state = _mem_balance.setdefault(
        wkey,
        {
            "balance_microdollars": 0,
            "held_microdollars": 0,
            "spend_limit_microdollars": "",
            "monthly_spent_microdollars": 0,
            "spend_period": _current_period(),
            "as_of_ms": _now_ms(),
        },
    )
    available = int(state.get("balance_microdollars", 0)) - int(state.get("held_microdollars", 0))
    if available < estimated_microdollars:
        return False, int(state.get("held_microdollars", 0)), available, "insufficient_balance"

    spend_limit = state.get("spend_limit_microdollars")
    if isinstance(spend_limit, int) and spend_limit > 0:
        spent = int(state.get("monthly_spent_microdollars", 0))
        if spent + estimated_microdollars > spend_limit:
            return (
                False,
                int(state.get("held_microdollars", 0)),
                available,
                "spend_limit_exceeded",
            )

    state["held_microdollars"] = int(state.get("held_microdollars", 0)) + estimated_microdollars
    hold = {
        "wallet_id": str(wallet_id),
        "estimated_max_microdollars": estimated_microdollars,
        **{k: v for k, v in (context or {}).items()},
    }
    _mem_holds[hkey] = hold
    return True, int(state["held_microdollars"]), available, "ok"


def get_hold(request_id: str) -> dict | None:
    hkey = _hold_key(request_id)
    client = _get_redis()
    if client is not None:
        raw = client.hgetall(hkey)
        return raw or None
    hold = _mem_holds.get(hkey)
    return dict(hold) if hold else None


def release_hold(
    wallet_id, request_id: str, estimated_microdollars: int, charged_microdollars: int
) -> None:
    """Settle a hold: release the reserved amount and debit the actual charge."""
    wkey = _wallet_key(wallet_id)
    hkey = _hold_key(request_id)
    client = _get_redis()
    if client is not None:
        client.hincrby(wkey, "held_microdollars", -estimated_microdollars)
        client.hincrby(wkey, "balance_microdollars", -charged_microdollars)
        client.delete(hkey)
        return
    state = _mem_balance.get(wkey)
    if state is not None:
        state["held_microdollars"] = int(state.get("held_microdollars", 0)) - estimated_microdollars
        state["balance_microdollars"] = (
            int(state.get("balance_microdollars", 0)) - charged_microdollars
        )
        state["as_of_ms"] = _now_ms()
    _mem_holds.pop(hkey, None)


def cancel_hold(wallet_id, request_id: str, estimated_microdollars: int) -> None:
    """Release a hold without debiting (e.g. provider error, request aborted)."""
    wkey = _wallet_key(wallet_id)
    hkey = _hold_key(request_id)
    client = _get_redis()
    if client is not None:
        client.hincrby(wkey, "held_microdollars", -estimated_microdollars)
        client.delete(hkey)
        return
    state = _mem_balance.get(wkey)
    if state is not None:
        state["held_microdollars"] = int(state.get("held_microdollars", 0)) - estimated_microdollars
        state["as_of_ms"] = _now_ms()
    _mem_holds.pop(hkey, None)


def _scan_delete(client, pattern: str) -> None:
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            client.delete(*keys)
        if cursor == 0:
            break


def reset_balance_cache() -> None:
    global _redis_client
    _mem_balance.clear()
    _mem_holds.clear()
    if _redis_client is not None:
        try:
            _scan_delete(_redis_client, "uaw:walletbal:*")
            _scan_delete(_redis_client, "uaw:hold:*")
        except Exception:
            pass
        _redis_client.close()
        _redis_client = None


def warm_wallet(session: Session, wallet: Wallet) -> dict:
    """Push the authoritative DB state into the cache (used after top-ups / admin changes)."""
    return load_balance_from_db(session, wallet.id)  # type: ignore[return-value]


def revalidate_sweep(session: Session, *, batch_size: int = 50) -> int:
    """Re-validate up to ``batch_size`` cached wallet balances from Postgres.

    Preserves each wallet's live Redis ``held`` projection so in-flight holds
    are never lost. Used by the billing worker's periodic sweep to correct drift
    (admin refunds, manual adjustments, expired holds) without blocking the hot
    path. Returns the number of wallets revalidated; no-op (0) when Redis is
    unavailable.
    """
    client = _get_redis()
    if client is None:
        return 0
    scanned = 0
    cursor = 0
    while scanned < batch_size:
        cursor, keys = client.scan(cursor=cursor, match="uaw:walletbal:*", count=batch_size)
        for key in keys:
            if scanned >= batch_size:
                break
            wallet_id = key.split(":", 2)[-1]
            raw = client.hgetall(key)
            if not raw:
                continue
            state = _coerce(raw)
            try:
                revalidate_wallet(session, wallet_id, preserve_held=state["held_microdollars"])
            except Exception:
                continue
            scanned += 1
        if cursor == 0:
            break
    return scanned
