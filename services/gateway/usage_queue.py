"""Durable usage-event queue (Phase 4).

The ingestion endpoint (``POST /v1/usage``) accepts batched usage events from
the SDK and fire-and-forgets them onto a Redis Stream so the request thread is
never blocked by billing. The billing worker (``services/gateway/worker.py``)
drains the stream with a consumer group and writes immutable ledger rows on the
slow path.

  * Stream:  ``conduit:usage:events`` (configurable via ``USAGE_STREAM_NAME``)
  * Group:   ``billing``         (configurable via ``USAGE_CONSUMER_GROUP``)

When Redis is unavailable we fall back to an in-memory deque with a simple
pending list so the same code path works in tests and degraded environments,
mirroring ``rate_limit.py`` / ``allowance_cache.py`` / ``balance_cache.py``.

Phase 5 hardening adds bounded retries + a dead-letter queue: the billing worker
increments a per-entry attempt counter (``conduit:usage:attempts``) each time it picks
up an entry; after ``worker_max_delivery_attempts`` the entry is moved to the
``conduit:usage:dlq`` stream (XADD + XACK + XDEL) for audit/manual replay instead of
being retried forever. ``claim_stale`` reclaims pending entries stranded by a
dead consumer via ``XCLAIM``. In-memory fallback re-delivers un-acked entries
from ``read_batch`` so retry/DLQ behavior is exercisable in tests.
"""

from __future__ import annotations

import time
import uuid
from collections import deque

import redis

from services.shared.config import get_settings

_redis_client: redis.Redis | None = None
_mem_stream: deque[tuple[str, dict]] = deque()
_mem_pending: dict[str, list[tuple[str, dict]]] = {}
_mem_counter: int = 0
_mem_attempts: dict[str, int] = {}
_mem_dlq: deque[tuple[str, dict]] = deque()


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


def _stream() -> str:
    return get_settings().usage_stream_name


def _group() -> str:
    return get_settings().usage_consumer_group


def ensure_consumer_group() -> None:
    """Create the consumer group if missing. Idempotent."""
    client = _get_redis()
    if client is None:
        _mem_pending.setdefault(_group(), [])
        return
    try:
        client.xgroup_create(_stream(), _group(), id="0", mkstream=True)
    except redis.ResponseError as exc:
        # "BUSYGROUP" → already exists; safe to ignore.
        if "BUSYGROUP" not in str(exc):
            raise


def enqueue_event(event: dict) -> str:
    """XADD a usage event; returns the stream id."""
    fields = {k: _to_str(v) for k, v in event.items() if v is not None}
    client = _get_redis()
    if client is not None:
        return str(client.xadd(_stream(), fields))
    global _mem_counter
    _mem_counter += 1
    stream_id = f"{int(time.time() * 1000)}-{_mem_counter}"
    _mem_stream.append((stream_id, dict(fields)))
    return stream_id


def read_batch(
    consumer: str | None = None,
    count: int | None = None,
    block_ms: int | None = None,
) -> list[tuple[str, dict]]:
    """Read a batch of pending events for the consumer group (XREADGROUP '>')."""
    settings = get_settings()
    consumer = consumer or settings.usage_consumer_name
    count = count or settings.worker_max_batch
    block_ms = 0 if block_ms is None else block_ms

    client = _get_redis()
    if client is not None:
        # Redis semantics: BLOCK 0 == block forever. Treat 0/None as non-blocking.
        effective_block = block_ms if (block_ms and block_ms > 0) else None
        response = client.xreadgroup(
            groupname=_group(),
            consumername=consumer,
            streams={_stream(): ">"},
            count=count,
            block=effective_block,
        )
        if not response:
            return []
        _stream_name, entries = response[0]
        return [(entry_id, dict(fields)) for entry_id, fields in entries]

    # In-memory fallback: re-deliver any un-acked pending entries first (so
    # retries work without a real XCLAIM path), then drain new events.
    pending = _mem_pending.setdefault(_group(), [])
    batch: list[tuple[str, dict]] = []
    for entry in list(pending):
        if len(batch) >= count:
            break
        batch.append(entry)
    while _mem_stream and len(batch) < count:
        entry = _mem_stream.popleft()
        pending.append(entry)
        batch.append(entry)
    return batch


def ack_event(entry_id: str) -> None:
    client = _get_redis()
    if client is not None:
        client.xack(_stream(), _group(), entry_id)
        return
    pending = _mem_pending.get(_group(), [])
    _mem_pending[_group()] = [e for e in pending if e[0] != entry_id]


def delete_event(entry_id: str) -> None:
    """Remove a settled entry from the stream so it doesn't grow unbounded."""
    client = _get_redis()
    if client is not None:
        client.xdel(_stream(), entry_id)


def pending_count() -> int:
    client = _get_redis()
    if client is not None:
        info = client.xpending(_stream(), _group())
        return int(info.get("pending", 0)) if isinstance(info, dict) else 0
    return len(_mem_pending.get(_group(), []))


def stream_length() -> int:
    client = _get_redis()
    if client is not None:
        return int(client.xlen(_stream()))
    return len(_mem_stream) + len(_mem_pending.get(_group(), []))


# --- Phase 5 hardening: bounded retries + dead-letter queue -----------------


def _dlq_stream() -> str:
    return get_settings().usage_dlq_stream_name


def claim_stale(consumer: str | None = None, idle_ms: int | None = None) -> list[tuple[str, dict]]:
    """Reclaim pending entries that have been idle for > ``idle_ms`` into this
    consumer via ``XCLAIM`` (recovers entries stuck with a dead consumer).

    Returns ``[(entry_id, fields), ...]``. In-memory fallback is a no-op: a
    single process never leaves entries stranded, and un-acked in-memory entries
    are re-delivered directly by ``read_batch``.
    """
    settings = get_settings()
    consumer = consumer or settings.usage_consumer_name
    idle_ms = idle_ms if idle_ms is not None else settings.worker_claim_idle_ms
    client = _get_redis()
    if client is None:
        return []
    try:
        pending = client.xpending_range(
            _stream(), _group(), min="-", max="+", count=settings.worker_max_batch
        )
    except Exception:
        return []
    message_ids: list[str] = []
    for item in pending:
        idle = item.get("time_since_delivered") or item.get("idle") or 0
        try:
            idle = int(idle)
        except (TypeError, ValueError):
            idle = 0
        if idle >= idle_ms:
            mid = item.get("message_id")
            if mid:
                message_ids.append(mid)
    if not message_ids:
        return []
    try:
        res = client.xclaim(
            _stream(), _group(), consumer, min_idle_time=idle_ms, message_ids=message_ids
        )
    except Exception:
        return []
    return [(eid, dict(fields)) for eid, fields in res]


def incr_attempt(entry_id: str) -> int:
    """Increment and return the delivery-attempt count for ``entry_id``."""
    client = _get_redis()
    if client is not None:
        return int(client.hincrby("conduit:usage:attempts", entry_id, 1))
    _mem_attempts[entry_id] = _mem_attempts.get(entry_id, 0) + 1
    return _mem_attempts[entry_id]


def get_attempt_count(entry_id: str) -> int:
    client = _get_redis()
    if client is not None:
        v = client.hget("conduit:usage:attempts", entry_id)
        return int(v) if v else 0
    return _mem_attempts.get(entry_id, 0)


def clear_attempt(entry_id: str) -> None:
    client = _get_redis()
    if client is not None:
        client.hdel("conduit:usage:attempts", entry_id)
        return
    _mem_attempts.pop(entry_id, None)


def move_to_dlq(entry_id: str, fields: dict, reason: str) -> None:
    """Move a poison entry to the dead-letter stream: XADD the payload + reason,
    then XACK + XDEL the original and clear its attempt counter.

    In-memory fallback appends to ``_mem_dlq`` and removes the entry from pending.
    """
    import time as _time

    dlq_fields = {k: _to_str(v) for k, v in fields.items() if v is not None}
    dlq_fields["reason"] = reason
    dlq_fields["failed_at"] = str(int(_time.time() * 1000))
    dlq_fields["original_entry_id"] = entry_id

    client = _get_redis()
    if client is not None:
        client.xadd(_dlq_stream(), dlq_fields, maxlen=10_000, approximate=True)
        client.xack(_stream(), _group(), entry_id)
        client.xdel(_stream(), entry_id)
        clear_attempt(entry_id)
        return
    _mem_dlq.append((entry_id, dlq_fields))
    pending = _mem_pending.get(_group(), [])
    _mem_pending[_group()] = [e for e in pending if e[0] != entry_id]
    clear_attempt(entry_id)


def dlq_length() -> int:
    client = _get_redis()
    if client is not None:
        return int(client.xlen(_dlq_stream()))
    return len(_mem_dlq)


def read_dlq(count: int = 100) -> list[tuple[str, dict]]:
    """Inspect DLQ entries (audit / manual replay). Returns ``[(entry_id, fields)]``."""
    client = _get_redis()
    if client is not None:
        res = client.xrange(_dlq_stream(), min="-", max="+", count=count)
        return [(eid, dict(fields)) for eid, fields in res]
    return list(_mem_dlq)


def _scan_delete(client, pattern: str) -> None:
    """Delete all keys matching a pattern (used by reset helpers for test isolation)."""
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            client.delete(*keys)
        if cursor == 0:
            break


def reset_usage_queue() -> None:
    global _redis_client, _mem_counter
    _mem_stream.clear()
    _mem_pending.clear()
    _mem_counter = 0
    _mem_seen.clear()
    _mem_attempts.clear()
    _mem_dlq.clear()
    client = _redis_client if _redis_client is not None else _get_redis()
    if client is not None:
        try:
            _scan_delete(client, _stream())
            _scan_delete(client, "conduit:usage:idem:*")
            _scan_delete(client, "conduit:usage:attempts")
            _scan_delete(client, _dlq_stream())
        except Exception:
            pass
        if _redis_client is not None:
            _redis_client.close()
        _redis_client = None


def _to_str(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    return str(value)


_mem_seen: dict[str, float] = {}


def mark_seen(request_id: str, ttl_seconds: int | None = None) -> bool:
    """Ingestion idempotency gate. Returns True if newly seen, False if duplicate."""
    import time as _time

    ttl = ttl_seconds or get_settings().usage_idempotency_ttl_seconds
    key = f"conduit:usage:idem:{request_id}"
    client = _get_redis()
    if client is not None:
        return bool(client.set(key, "1", nx=True, ex=ttl))
    now = _time.time()
    expires = _mem_seen.get(key)
    if expires and expires > now:
        return False
    _mem_seen[key] = now + ttl
    return True


def reset_idempotency() -> None:
    _mem_seen.clear()
