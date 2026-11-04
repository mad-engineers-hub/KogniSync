"""
backend/app/services/redis_hold_support.py

Advisory Redis integration for hold TTL countdowns and expiration acceleration.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Redis is strictly ADVISORY. PostgreSQL remains the sole authority for hold status and inventory.
2. Redis expiration must NEVER independently release or decrement inventory.
3. Outages, connection failures, or missed Redis events must never affect booking consistency
   or inventory correctness. PostgreSQL periodic sweeps recover from any missed event.
4. No distributed Redis locks are used for inventory allocation (PostgreSQL row locks are authoritative).
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger("kognisync.redis")


class RedisHoldSupport:
    """
    Advisory Redis helper for holding TTL timers and real-time countdown caching.
    All methods fail safely: if Redis is unavailable or down, operations return
    graceful fallbacks and never break core booking workflows.
    """

    def __init__(self, redis_url: Optional[str] = None, enabled: bool = True):
        self.redis_url = redis_url or settings.REDIS_URL
        self.enabled = enabled
        self._client: Optional[aioredis.Redis] = None

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Lazy initialization of async Redis client with quick connection timeouts."""
        if not self.enabled:
            return None
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self.redis_url,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    decode_responses=True,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Redis client ({e}). Running in DB-only mode.")
                return None
        return self._client

    async def register_hold_ttl(
        self,
        hold_id: str,
        ttl_seconds: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Record an advisory TTL key in Redis for hold countdown.
        Fails safely if Redis is offline.
        """
        try:
            client = await self.get_client()
            if not client:
                return False

            key = f"kognisync:hold:{hold_id}"
            payload = {
                "hold_id": hold_id,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": ttl_seconds,
                **(metadata or {}),
            }
            # Set key with TTL
            await client.set(key, json.dumps(payload), ex=max(1, ttl_seconds))
            return True
        except Exception as e:
            logger.debug(f"Redis register_hold_ttl failed for {hold_id}: {e} (advisory only; DB is unaffected)")
            return False

    async def remove_hold_ttl(self, hold_id: str) -> bool:
        """
        Remove the advisory TTL key when a hold is confirmed, expired, or released.
        Fails safely if Redis is offline.
        """
        try:
            client = await self.get_client()
            if not client:
                return False

            key = f"kognisync:hold:{hold_id}"
            await client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Redis remove_hold_ttl failed for {hold_id}: {e}")
            return False

    async def get_hold_ttl(self, hold_id: str) -> Optional[int]:
        """
        Retrieve remaining TTL in seconds from Redis.
        Returns None if Redis is unreachable or key does not exist.
        """
        try:
            client = await self.get_client()
            if not client:
                return None

            key = f"kognisync:hold:{hold_id}"
            ttl = await client.ttl(key)
            if ttl is not None and ttl >= 0:
                return ttl
            return None
        except Exception as e:
            logger.debug(f"Redis get_hold_ttl failed for {hold_id}: {e}")
            return None

    async def is_available(self) -> bool:
        """Ping check for Redis availability."""
        try:
            client = await self.get_client()
            if not client:
                return False
            return bool(await client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

