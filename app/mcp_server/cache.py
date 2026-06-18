"""
Cache layer using Redis (Upstash-compatible).
Caches MCP tool results to keep latency under 3 seconds.
"""
import json
import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()
_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _client


async def cache_get(key: str) -> dict | None:
    try:
        r = get_redis()
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def cache_set(key: str, value: dict, ttl: int | None = None) -> None:
    try:
        r = get_redis()
        ttl = ttl or settings.cache_ttl_seconds
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass


async def cached_tool_call(tool_name: str, call_fn, **kwargs) -> dict:
    """Wrap any async tool call with a cache layer."""
    key_parts = [tool_name] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    cache_key = "matchmind:" + ":".join(key_parts)

    cached = await cache_get(cache_key)
    if cached:
        return {**cached, "_cached": True}

    result = await call_fn(**kwargs)
    await cache_set(cache_key, result)
    return result
