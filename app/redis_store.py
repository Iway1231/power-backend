"""Small, failure-tolerant Redis adapter used for shared caching and limits."""

import hashlib
import json
import logging
import time
from typing import Any, Optional

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover - production dependencies include redis
    Redis = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class RedisStore:
    """Keep Redis optional so development still works without a Redis server."""

    def __init__(self, url: Optional[str], prefix: str = "power-backend"):
        self.url = url
        self.prefix = prefix
        self._client = None
        self._retry_after = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.url and Redis is not None)

    async def _client_or_none(self):
        if not self.enabled or time.monotonic() < self._retry_after:
            return None
        if self._client is None:
            self._client = Redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
        return self._client

    async def _run(self, operation):
        client = await self._client_or_none()
        if client is None:
            return None
        try:
            return await operation(client)
        except Exception as exc:
            logger.warning("Redis operation unavailable: %s", exc)
            self._retry_after = time.monotonic() + 30
            if self._client is not None:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
            self._client = None
            return None

    def key(self, value: str) -> str:
        return f"{self.prefix}:{value}"

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self._run(lambda client: client.get(self.key(key)))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            logger.warning("Ignoring invalid JSON in Redis key %s", key)
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> bool:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        result = await self._run(
            lambda client: client.set(self.key(key), encoded, ex=max(1, ttl_seconds))
        )
        return bool(result)

    async def increment_with_window(
        self,
        key: str,
        window_seconds: int,
    ) -> Optional[tuple[int, int]]:
        """Atomically increment a fixed-window counter and return count and TTL."""

        async def operation(client):
            redis_key = self.key(key)
            count = await client.incr(redis_key)
            if count == 1:
                await client.expire(redis_key, max(1, window_seconds))
            ttl = await client.ttl(redis_key)
            return int(count), max(1, int(ttl))

        return await self._run(operation)


def stable_key(namespace: str, value: str) -> str:
    """Produce short keys without putting user-provided text into Redis key names."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{namespace}:{digest}"
