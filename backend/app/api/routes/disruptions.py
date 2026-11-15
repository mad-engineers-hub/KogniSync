"""
backend/app/api/routes/disruptions.py

Real-Time Journey Disruption Intelligence and Recovery endpoints (Milestone M3.7).
Provides provider discovery, active disruption querying, deterministic impact assessment,
and Pareto-ranked recovery recommendations.
"""
import asyncio
from collections import OrderedDict, deque
import hashlib
import math
import threading
import time
from typing import Any, Optional
import weakref
from fastapi import APIRouter, Depends, HTTPException, Query, status
try:
    import redis as sync_redis
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    sync_redis = None
    aioredis = None
from app.core.config import settings
from app.core.logging import logger
from app.core.security import TransitPollPrincipal, verify_transit_poll_access
from app.services.disruption.schemas import (
    DisruptionAssessRequest,
    DisruptionEvent,
    DisruptionProviderCapability,
    DisruptionRecoverRequest,
    DisruptionRecoveryResponse,
    GTFSFeedListResponse,
    GTFSFeedStatus,
    JourneyDisruptionAssessment,
)
from app.services.disruption.service import disruption_service
from app.services.disruption.providers.gtfs_registry import gtfs_feed_registry

router = APIRouter(prefix="/api/v1/disruptions", tags=["Disruption Intelligence"])


@router.get(
    "/health",
    summary="Health and operational status of the disruption intelligence service",
)
async def get_disruption_health():
    capabilities = disruption_service.get_provider_capabilities()
    feed_statuses = gtfs_feed_registry.get_feed_statuses()
    has_live = any(c.is_available and c.provenance_source == "provider_live" for c in capabilities)
    has_live_transit = any(s.connectivity_status == "available" for s in feed_statuses)
    return {
        "status": "healthy",
        "service": "Real-Time Disruption Intelligence & Recovery Service",
        "providers_registered": len(capabilities),
        "live_provider_connected": has_live,
        "live_transit_connected": has_live_transit,
        "gtfs_feeds_registered": len(feed_statuses),
        "gtfs_feeds_operational": sum(1 for s in feed_statuses if s.connectivity_status == "available"),
        "simulation_active": any(c.name == "simulation_engine" for c in capabilities),
        "rate_limit_backend": poll_rate_limiter.enforcement_mode,
        "liveVerificationStatus": "PASS" if has_live else "BLOCKED — credentials unavailable",
    }


@router.get(
    "/providers",
    response_model=list[DisruptionProviderCapability],
    summary="Discover registered disruption providers and capabilities",
)
async def get_disruption_providers() -> list[DisruptionProviderCapability]:
    """Returns capabilities, supported transport modes, and availability status of all disruption adapters."""
    return disruption_service.get_provider_capabilities()


def _build_gtfs_feed_list_response() -> GTFSFeedListResponse:
    statuses = gtfs_feed_registry.get_feed_statuses()
    operational_count = sum(1 for s in statuses if s.connectivity_status == "available")
    configured_count = sum(1 for s in statuses if s.enabled and s.connectivity_status != "unconfigured")
    pending_count = sum(1 for s in statuses if s.authorization_status == "pending_credentials")

    if operational_count > 0:
        notice = f"Verified {operational_count} operational transit feed(s)."
    elif pending_count > 0:
        notice = (
            f"No live GTFS Realtime feeds are currently verified and operational "
            f"({pending_count} registered feed(s) awaiting agency credentials)."
        )
    else:
        notice = "No live GTFS Realtime feeds are currently verified and operational."

    return GTFSFeedListResponse(
        feeds=statuses,
        total_configured=configured_count,
        total_operational=operational_count,
        notice=notice,
    )


@router.get(
    "/providers/feeds",
    response_model=GTFSFeedListResponse,
    summary="Inspect sanitized operational status of all registered GTFS Realtime feeds",
)
async def get_registered_gtfs_feeds() -> GTFSFeedListResponse:
    """
    Returns sanitized operational status and diagnostics for registered public-transit GTFS/IUDX feeds.
    Strictly masks server-side tokens and sensitive endpoint query parameters.
    """
    return _build_gtfs_feed_list_response()


_POLL_RATE_LIMIT_LUA = """
local principal_key = KEYS[1]
local global_key = KEYS[2]
local force_key = KEYS[3]
local seq_key = KEYS[4]

local window_ms = tonumber(ARGV[1])
local max_requests = tonumber(ARGV[2])
local global_max = tonumber(ARGV[3])
local is_force = tonumber(ARGV[4])
local force_min_ms = tonumber(ARGV[5])
local ttl_ms = tonumber(ARGV[6])

local t = redis.call("TIME")
local now_ms = (tonumber(t[1]) * 1000) + math.floor(tonumber(t[2]) / 1000)

if is_force == 1 and force_min_ms > 0 then
    local last_force_raw = redis.call("GET", force_key)
    if last_force_raw then
        local elapsed_ms = now_ms - tonumber(last_force_raw)
        if elapsed_ms < force_min_ms then
            return {0, "force_cooldown", force_min_ms - elapsed_ms}
        end
    end
end

local cutoff = now_ms - window_ms
redis.call("ZREMRANGEBYSCORE", principal_key, "-inf", cutoff)
redis.call("ZREMRANGEBYSCORE", global_key, "-inf", cutoff)

local p_count = redis.call("ZCARD", principal_key)
local g_count = redis.call("ZCARD", global_key)
if p_count >= max_requests or g_count >= global_max then
    local oldest_arr = redis.call("ZRANGE", principal_key, 0, 0, "WITHSCORES")
    if #oldest_arr == 0 then
        oldest_arr = redis.call("ZRANGE", global_key, 0, 0, "WITHSCORES")
    end
    local oldest_ms = tonumber(oldest_arr[2] or now_ms)
    local retry_ms = math.max(1000, window_ms - (now_ms - oldest_ms))
    return {0, "rate_limit", retry_ms}
end

local seq = redis.call("INCR", seq_key)
local seq_ttl_sec = math.max(60, math.ceil(ttl_ms / 1000) + 60)
redis.call("EXPIRE", seq_key, seq_ttl_sec)

local member = tostring(now_ms) .. ":" .. tostring(seq)
redis.call("ZADD", principal_key, now_ms, member)
redis.call("PEXPIRE", principal_key, ttl_ms)
redis.call("ZADD", global_key, now_ms, member)
redis.call("PEXPIRE", global_key, ttl_ms)

if is_force == 1 then
    local force_ttl_ms = math.max(1000, math.ceil(force_min_ms) + 5000)
    redis.call("SET", force_key, tostring(now_ms), "PX", force_ttl_ms)
end

return {1, "ok", 0}
"""


class PollRateLimiter:
    """
    Bounded sliding-window rate limiter & global force-poll cooldown guard.

    Deployment scope & coordination:
    - Primary mode (`shared_redis`): uses atomic Redis Lua evaluation with hashed
      per-principal sorted-set keys + bounded TTLs and shared force-cooldown/global keys
      across worker processes.
    - Fallback mode (`process_local_fallback`): if Redis is disabled or temporarily unreachable,
      enforces bounded LRU memory tracking (max `TRANSIT_POLL_RATE_LIMIT_MAX_TRACKED_PRINCIPALS`
      principals), automatic inactive-bucket expiry, and non-evictable global ceilings and
      force cooldowns within the current process.
    """

    def __init__(
        self,
        *,
        redis_client: Any = None,
        redis_url: str | None = None,
        key_prefix: str = "kognisync:transit_poll_rl",
        use_redis: bool | None = None,
        redis_backoff_seconds: float = 15.0,
    ) -> None:
        self._lock = threading.Lock()
        self._requests_by_principal: OrderedDict[str, deque[float]] = OrderedDict()
        self._global_requests: deque[float] = deque()
        self._last_force_poll_at: float | None = None
        self._evicted_count: int = 0

        self._injected_redis_client = redis_client
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._use_redis_override = use_redis
        self._redis_backoff_seconds = redis_backoff_seconds
        self._redis_backoff_until: float = 0.0
        self._redis_keys_touched: bool = False
        self._loop_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, aioredis.Redis] = (
            weakref.WeakKeyDictionary()
        )
        self.enforcement_mode: str = "shared_redis" if redis_client is not None else "process_local_fallback"
        self.last_redis_error: str | None = None

    @staticmethod
    def _hash_principal(principal_id: str) -> str:
        return hashlib.sha256((principal_id or "anonymous").encode("utf-8")).hexdigest()[:24]

    def _effective_use_redis(self) -> bool:
        if sync_redis is None or aioredis is None:
            return False
        if self._injected_redis_client is not None:
            return True
        if self._use_redis_override is not None:
            return self._use_redis_override
        return bool(getattr(settings, "TRANSIT_POLL_RATE_LIMIT_USE_REDIS", True))

    def _max_tracked_principals(self) -> int:
        return max(1, int(getattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_TRACKED_PRINCIPALS", 1024)))

    def _prune_inactive_locked(self, now: float, cutoff: float) -> None:
        while self._global_requests and self._global_requests[0] <= cutoff:
            self._global_requests.popleft()

        expired_keys: list[str] = []
        for p_key, dq in self._requests_by_principal.items():
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if not dq:
                expired_keys.append(p_key)
        for p_key in expired_keys:
            self._requests_by_principal.pop(p_key, None)

        force_min_interval = max(0.0, float(settings.TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS))
        if (
            self._last_force_poll_at is not None
            and (now - self._last_force_poll_at) >= max(force_min_interval, float(settings.TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS))
        ):
            self._last_force_poll_at = None

    def get_diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enforcement_mode": self.enforcement_mode,
                "tracked_principals": len(self._requests_by_principal),
                "max_tracked_principals": self._max_tracked_principals(),
                "global_window_entries": len(self._global_requests),
                "evicted_principals": self._evicted_count,
                "last_redis_error": self.last_redis_error,
            }

    def reset(self) -> None:
        with self._lock:
            self._requests_by_principal.clear()
            self._global_requests.clear()
            self._last_force_poll_at = None
            self._evicted_count = 0
            self._redis_backoff_until = 0.0
            self.last_redis_error = None
            touched = self._redis_keys_touched
            self._redis_keys_touched = False

        if touched and self._injected_redis_client is None and self._effective_use_redis():
            url = self._redis_url or settings.REDIS_URL
            try:
                client = sync_redis.from_url(url, socket_connect_timeout=0.25, socket_timeout=0.25)
                try:
                    pattern = f"{self._key_prefix}:*"
                    cursor = 0
                    while True:
                        cursor, keys = client.scan(cursor=cursor, match=pattern, count=200)
                        if keys:
                            client.delete(*keys)
                        if cursor == 0:
                            break
                finally:
                    client.close()
            except Exception as ex:
                logger.debug("PollRateLimiter sync Redis reset skipped: %s", type(ex).__name__)

    async def areset(self) -> None:
        self.reset()
        client = self._get_async_redis_client()
        if client is not None:
            try:
                pattern = f"{self._key_prefix}:*"
                if hasattr(client, "scan"):
                    cursor = 0
                    while True:
                        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
                        if keys:
                            await client.delete(*keys)
                        if cursor == 0:
                            break
                elif hasattr(client, "delete"):
                    await client.delete(
                        f"{self._key_prefix}:global",
                        f"{self._key_prefix}:force",
                        f"{self._key_prefix}:seq",
                    )
            except Exception as ex:
                logger.debug("PollRateLimiter async Redis reset skipped: %s", type(ex).__name__)

    def _get_async_redis_client(self) -> Any:
        if self._injected_redis_client is not None:
            return self._injected_redis_client
        if not self._effective_use_redis():
            return None
        if time.monotonic() < self._redis_backoff_until:
            return None
        url = self._redis_url or getattr(settings, "REDIS_URL", None)
        if not url:
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        client = self._loop_clients.get(loop)
        if client is None:
            client = aioredis.from_url(
                url,
                socket_connect_timeout=0.35,
                socket_timeout=0.35,
                decode_responses=True,
            )
            self._loop_clients[loop] = client
        return client

    def _check_and_record_local(self, principal_id: str, force: bool = False) -> None:
        now = time.monotonic()
        window = max(1, int(settings.TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS))
        max_requests = max(1, int(settings.TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS))
        force_min_interval = max(0.0, float(settings.TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS))
        max_tracked = self._max_tracked_principals()
        p_key = self._hash_principal(principal_id)

        with self._lock:
            cutoff = now - window
            self._prune_inactive_locked(now, cutoff)

            if force and force_min_interval > 0 and self._last_force_poll_at is not None:
                elapsed_since_force = now - self._last_force_poll_at
                if elapsed_since_force < force_min_interval:
                    retry_after = max(1, int(math.ceil(force_min_interval - elapsed_since_force)))
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many forced transit feed poll requests; cooldown floor active.",
                        headers={"Retry-After": str(retry_after)},
                    )

            global_max = max_requests * 2
            if len(self._global_requests) >= global_max:
                oldest_global = self._global_requests[0]
                retry_after = max(1, int(math.ceil(window - (now - oldest_global))))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many transit feed poll requests; rate limit exceeded.",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket = self._requests_by_principal.get(p_key)
            if bucket is not None:
                self._requests_by_principal.move_to_end(p_key)
                if len(bucket) >= max_requests:
                    retry_after = max(1, int(math.ceil(window - (now - bucket[0]))))
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many transit feed poll requests; rate limit exceeded.",
                        headers={"Retry-After": str(retry_after)},
                    )
            else:
                while len(self._requests_by_principal) >= max_tracked:
                    self._requests_by_principal.popitem(last=False)
                    self._evicted_count += 1
                bucket = deque()
                self._requests_by_principal[p_key] = bucket

            bucket.append(now)
            self._global_requests.append(now)
            if force:
                self._last_force_poll_at = now

    def check_and_record(self, principal_id: str, force: bool = False) -> None:
        self.enforcement_mode = "process_local_fallback"
        self._check_and_record_local(principal_id, force=force)

    async def acheck_and_record(self, principal_id: str, force: bool = False) -> None:
        client = self._get_async_redis_client()
        if client is not None:
            window_ms = max(1, int(settings.TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS)) * 1000
            max_requests = max(1, int(settings.TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS))
            global_max = max_requests * 2
            force_min_ms = int(round(max(0.0, float(settings.TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS)) * 1000))
            ttl_ms = window_ms + 5000
            p_hash = self._hash_principal(principal_id)

            keys = [
                f"{self._key_prefix}:p:{p_hash}",
                f"{self._key_prefix}:global",
                f"{self._key_prefix}:force",
                f"{self._key_prefix}:seq",
            ]
            args = [
                window_ms,
                max_requests,
                global_max,
                1 if force else 0,
                force_min_ms,
                ttl_ms,
            ]
            try:
                res = await client.eval(_POLL_RATE_LIMIT_LUA, len(keys), *keys, *args)
                self._redis_keys_touched = True
                self.enforcement_mode = "shared_redis"
                self.last_redis_error = None
                allowed = int(res[0])
                reason = res[1].decode("utf-8") if isinstance(res[1], bytes) else str(res[1])
                retry_ms = int(res[2]) if len(res) > 2 else 1000
                if allowed == 1:
                    return
                retry_after = max(1, int(math.ceil(retry_ms / 1000.0)))
                if reason == "force_cooldown":
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many forced transit feed poll requests; cooldown floor active.",
                        headers={"Retry-After": str(retry_after)},
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many transit feed poll requests; rate limit exceeded.",
                    headers={"Retry-After": str(retry_after)},
                )
            except HTTPException:
                raise
            except Exception as ex:
                first_failure = self.enforcement_mode != "process_local_fallback"
                self.enforcement_mode = "process_local_fallback"
                self.last_redis_error = type(ex).__name__
                self._redis_backoff_until = time.monotonic() + self._redis_backoff_seconds
                if self._injected_redis_client is None:
                    try:
                        loop = asyncio.get_running_loop()
                        self._loop_clients.pop(loop, None)
                    except RuntimeError:
                        pass
                if first_failure:
                    logger.warning(
                        "PollRateLimiter falling back to process-local bounded state (%s); "
                        "limits apply per worker until Redis recovers.",
                        type(ex).__name__,
                    )

        self.enforcement_mode = "process_local_fallback"
        self._check_and_record_local(principal_id, force=force)


poll_rate_limiter = PollRateLimiter()


@router.post(
    "/providers/feeds/poll",
    response_model=GTFSFeedListResponse,
    summary="Trigger controlled polling cycle for enabled authorized transit feeds",
)
async def poll_registered_gtfs_feeds(
    force: bool = Query(False, description="Bypass per-feed polling cooldown interval when true"),
    principal: TransitPollPrincipal = Depends(verify_transit_poll_access),
) -> GTFSFeedListResponse:
    """
    Executes an operationally authorized poll across enabled transit feeds using IP-pinned SSRF transport.
    Requires server-side operational credentials, elevated privilege for `force=true`,
    and enforces strict sliding-window rate limiting to prevent upstream provider abuse.
    """
    if force and not principal.can_force:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: elevated operational privilege required for force polling",
        )
    await poll_rate_limiter.acheck_and_record(principal.principal_id, force=force)
    await gtfs_feed_registry.poll_all_enabled_feeds(force=force)
    return _build_gtfs_feed_list_response()


@router.get(
    "",
    response_model=list[DisruptionEvent],
    summary="Fetch active disruption events",
)
async def get_disruptions(
    corridor: Optional[str] = Query(None, description="Optional corridor filter (e.g. 'NH-75', 'Chennai-Bengaluru')"),
    scenario: Optional[str] = Query(None, description="Optional demonstration scenario (e.g. 'shiradi_ghat', 'silk_board')"),
    include_simulated: bool = Query(True, description="Whether to include simulated demo disruptions"),
    bbox: Optional[str] = Query(None, description="Optional bounding box 'minLon,minLat,maxLon,maxLat'"),
) -> list[DisruptionEvent]:
    """Returns active disruption incidents matching filters, with explicit provenance tagging."""
    parsed_bbox: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) == 4:
                parsed_bbox = (parts[0], parts[1], parts[2], parts[3])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bbox format. Expected 'minLon,minLat,maxLon,maxLat' with valid floats.",
            )

    try:
        events = await disruption_service.get_active_disruptions(
            corridor=corridor,
            scenario=scenario,
            include_simulated=include_simulated,
            bbox=parsed_bbox,
        )
        return events
    except Exception as e:
        logger.error(f"Error fetching disruptions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active disruptions from registered providers.",
        )


@router.post(
    "/assess",
    response_model=JourneyDisruptionAssessment,
    summary="Assess disruption impact on a multimodal journey",
)
async def assess_journey(request: DisruptionAssessRequest) -> JourneyDisruptionAssessment:
    """
    Evaluates active disruptions against journey segments.
    Computes delay, arrival time slip, transfer buffer erosion, and connection risk.
    """
    try:
        assessment = await disruption_service.assess_journey_disruptions(
            journey=request.journey,
            include_simulated=request.include_simulated,
            scenario=request.scenario,
        )
        return assessment
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error assessing journey disruptions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Disruption assessment service encountered an unexpected error.",
        )


@router.post(
    "/recover",
    response_model=DisruptionRecoveryResponse,
    summary="Generate Pareto-ranked recovery alternatives for a disrupted journey",
)
async def recover_journey(request: DisruptionRecoverRequest) -> DisruptionRecoveryResponse:
    """
    Generates feasible recovery options (mode shifts, highway detours, schedule advances),
    evaluates hard constraints, and ranks recommendations via the deterministic Pareto engine.
    """
    try:
        response = await disruption_service.recover_journey(
            journey=request.journey,
            budget_max=request.budget_max,
            preferred_arrival_before=request.preferred_arrival_before,
            include_simulated=request.include_simulated,
            scenario=request.scenario,
        )
        return response
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error generating journey recovery recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Journey recovery service encountered an unexpected error.",
        )

