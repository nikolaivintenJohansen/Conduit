import redis.asyncio as redis


async def check_redis(redis_url: str) -> bool:
    client = redis.from_url(redis_url, decode_responses=True)
    try:
        return bool(await client.ping())
    finally:
        await client.aclose()
