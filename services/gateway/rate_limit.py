import time
from uuid import UUID

import redis

from services.shared.config import get_settings

_redis_client: redis.Redis | None = None
_memory_counters: dict[str, tuple[int, int, float]] = {}


class RateLimitExceededError(Exception):
    pass


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


def _minute_bucket() -> int:
    return int(time.time()) // 60


def check_rate_limits(
    virtual_key_id: UUID,
    *,
    rpm_limit: int,
    tpm_limit: int,
    estimated_tokens: int,
) -> None:
    bucket = _minute_bucket()
    key_id = str(virtual_key_id)

    client = _get_redis()
    if client is None:
        mem_key = f"{key_id}:{bucket}"
        rpm_count, tpm_count, _ = _memory_counters.get(mem_key, (0, 0, float(bucket)))
        rpm_count += 1
        tpm_count += estimated_tokens
        if rpm_count > rpm_limit:
            raise RateLimitExceededError("rpm limit exceeded")
        if tpm_count > tpm_limit:
            raise RateLimitExceededError("tpm limit exceeded")
        _memory_counters[mem_key] = (rpm_count, tpm_count, float(bucket))
        return

    rpm_key = f"ratelimit:{key_id}:rpm:{bucket}"
    tpm_key = f"ratelimit:{key_id}:tpm:{bucket}"

    rpm = client.incr(rpm_key)
    client.expire(rpm_key, 120)
    if rpm > rpm_limit:
        raise RateLimitExceededError("rpm limit exceeded")

    tpm = client.incrby(tpm_key, estimated_tokens)
    client.expire(tpm_key, 120)
    if tpm > tpm_limit:
        raise RateLimitExceededError("tpm limit exceeded")


def reset_rate_limit_state() -> None:
    global _redis_client
    _memory_counters.clear()
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
